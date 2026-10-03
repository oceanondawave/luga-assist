"""
Luga Assist - Master FastAPI Server & WebSocket Hub.
Coordinates Voice UI, Screen Capture, Gemini Web Extension, OS Controller, and TTS.
"""
import re
import json
import uuid
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import webbrowser

from app.config import (
    HOST,
    PORT,
    WEB_DIR,
    DEFAULT_TTS_VOICE,
)
from app.screen_capture import screen_capturer
from app.os_controller import os_controller
from app.tts_service import tts_service
from app.prompt_templates import build_gemini_prompt
from app.gemini_service import gemini_service
from app.native_voice import NativeVoiceListener
from app.sound_effects import sound_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Try restoring saved session from disk
    await gemini_service.auto_init_from_disk()

    # 2. Start Global Native Voice & Hotkey Listener (Zero browser needed!)
    loop = asyncio.get_running_loop()

    def handle_native_voice_command(cmd_text: str):
        print(f"\n[Global Handler] Đã nhận lệnh từ Micro: \"{cmd_text}\"")
        asyncio.run_coroutine_threadsafe(
            process_user_command(cmd_text, DEFAULT_TTS_VOICE), loop
        )

    native_voice = NativeVoiceListener(on_command_callback=handle_native_voice_command)
    native_voice.start_global_hotkeys()
    yield

app = FastAPI(title="Luga Assist Local Server", version="1.0.0", lifespan=lifespan)

# Enable CORS for Chrome Extension and local WebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount web static assets
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# Connection Managers
class ConnectionHub:
    def __init__(self):
        self.webui_clients = set()
        self.extension_client: Optional[WebSocket] = None
        self.pending_tasks: Dict[str, asyncio.Future] = {}
        self.chat_turns_count = 0

    async def register_webui(self, ws: WebSocket):
        await ws.accept()
        self.webui_clients.add(ws)
        # Broadcast initial status
        await self.broadcast_status()

    def unregister_webui(self, ws: WebSocket):
        self.webui_clients.discard(ws)

    async def register_extension(self, ws: WebSocket):
        await ws.accept()
        self.extension_client = ws
        print("[ConnectionHub] Chrome Extension connected!")
        await self.broadcast_status()

    async def unregister_extension(self):
        self.extension_client = None
        print("[ConnectionHub] Chrome Extension disconnected!")
        await self.broadcast_status()

    async def broadcast_status(self):
        ext_connected = self.extension_client is not None
        payload = {
            "type": "STATUS_UPDATE",
            "extension_connected": ext_connected,
            "gemini_ready": gemini_service.is_ready or ext_connected,
        }
        dead_clients = []
        for client in self.webui_clients:
            try:
                await client.send_json(payload)
            except Exception:
                dead_clients.append(client)
        for dc in dead_clients:
            self.webui_clients.discard(dc)

    async def broadcast_webui(self, payload: Dict[str, Any]):
        dead_clients = []
        for client in self.webui_clients:
            try:
                await client.send_json(payload)
            except Exception:
                dead_clients.append(client)
        for dc in dead_clients:
            self.webui_clients.discard(dc)

hub = ConnectionHub()


# Session payload from Chrome Extension
class SessionPayload(BaseModel):
    secure_1psid: str
    secure_1psidts: Optional[str] = ""


# Root and Health Endpoints
@app.get("/")
async def serve_index():
    return FileResponse(str(WEB_DIR / "index.html"))

@app.get("/style.css")
async def serve_css():
    return FileResponse(str(WEB_DIR / "style.css"))

@app.get("/app.js")
async def serve_js():
    return FileResponse(str(WEB_DIR / "app.js"))

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "gemini_ready": gemini_service.is_ready or (hub.extension_client is not None),
        "gemini_background_mode": gemini_service.is_ready,
        "extension_connected": hub.extension_client is not None,
        "screen_size": os_controller.get_screen_size(),
    }

@app.post("/api/set_session")
async def set_session(payload: SessionPayload):
    """Receive Google Gemini session cookies from Chrome Extension."""
    ok = await gemini_service.init_session(payload.secure_1psid, payload.secure_1psidts)
    await hub.broadcast_status()
    return {"status": "ok" if ok else "error", "ready": gemini_service.is_ready}


# Helper: Extract clean JSON from Gemini's response
def extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON extractor: scans text using json.JSONDecoder to find all valid JSON objects,
    resilient against markdown truncation, multiple blocks, or conversational preambles.
    """
    if not text:
        return None

    decoder = json.JSONDecoder()
    pos = 0
    candidates = []

    while pos < len(text):
        idx = text.find("{", pos)
        if idx == -1:
            break
        try:
            obj, end_pos = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                candidates.append(obj)
            pos = end_pos
        except Exception:
            pos = idx + 1

    # Prioritize candidates that contain "actions" or "action", preferring the last one (final decided answer)
    for cand in reversed(candidates):
        if "actions" in cand or "action" in cand:
            return cand

    if candidates:
        return candidates[-1]

    return None


# WebUI WebSocket Endpoint
@app.websocket("/ws/webui")
async def websocket_webui(ws: WebSocket):
    await hub.register_webui(ws)
    try:
        while True:
            msg_str = await ws.receive_text()
            data = json.loads(msg_str)
            msg_type = data.get("type")

            if msg_type == "VOICE_COMMAND":
                command = data.get("command", "").strip()
                voice = data.get("voice", DEFAULT_TTS_VOICE)
                if command:
                    # Run command processing asynchronously
                    asyncio.create_task(process_user_command(command, voice))

            elif msg_type == "STOP_SPEECH":
                tts_service.stop_speaking()

    except WebSocketDisconnect:
        hub.unregister_webui(ws)
    except Exception as e:
        print(f"[WebUI WS] Error: {e}")
        hub.unregister_webui(ws)


# Chrome Extension WebSocket Endpoint
@app.websocket("/ws/extension")
async def websocket_extension(ws: WebSocket):
    await hub.register_extension(ws)
    try:
        while True:
            msg_str = await ws.receive_text()
            data = json.loads(msg_str)
            msg_type = data.get("type")

            if msg_type == "COMMAND_RESULT":
                task_id = data.get("id")
                if task_id in hub.pending_tasks:
                    future = hub.pending_tasks.pop(task_id)
                    if not future.done():
                        future.set_result(data)

    except WebSocketDisconnect:
        await hub.unregister_extension()
    except Exception as e:
        print(f"[Extension WS] Error: {e}")
        await hub.unregister_extension()


# Master Pipeline Execution: Autonomous Multi-Step Goal Loop
MAX_AUTONOMOUS_STEPS = 5

async def process_user_command(user_command: str, voice: str):
    print(f"\n[Pipeline] 🎯 Nhận mục tiêu mới: '{user_command}'")
    # Start pulsing audio feedback for the user
    sound_manager.start_pulsing()

    # Step 1: Check Connection (Gemini Background Service or Extension)
    is_gemini_ready = gemini_service.is_ready or (hub.extension_client is not None)
    if not is_gemini_ready:
        sound_manager.play_error()
        error_msg = (
            "Chưa nhận được session Google Gemini! "
            "Vui lòng đảm bảo Chrome đã bật Extension Luga Assist và bạn đã đăng nhập tài khoản Google."
        )
        await hub.broadcast_webui({
            "type": "ERROR",
            "message": error_msg,
            "user_command": user_command,
        })
        await tts_service.speak(error_msg)
        return

    step = 0
    while step < MAX_AUTONOMOUS_STEPS:
        step += 1
        is_first_step = (step == 1)
        print(f"\n[Pipeline] 🔄 --- BƯỚC {step}/{MAX_AUTONOMOUS_STEPS} cho mục tiêu: '{user_command}' ---")

        await hub.broadcast_webui({
            "type": "ACTION_PROGRESS",
            "message": f"Đang chụp màn hình và phân tích (Bước {step})...",
            "step": step,
        })

        # Step 2: Screen Capture with Grid Overlay
        screenshot_b64, screen_size = screen_capturer.capture(with_grid=True)

        if is_first_step:
            prompt = build_gemini_prompt(user_command)
        else:
            prompt = (
                f"Màn hình đã được cập nhật sau bước trước.\n"
                f"Mục tiêu ban đầu của người dùng: \"{user_command}\".\n"
                f"Hãy quan sát màn hình mới này và thực hiện hành động tiếp theo để hoàn thành mục tiêu.\n"
                f"Nếu yêu cầu của người dùng ĐÃ ĐƯỢC HOÀN TẤT 100%, hãy đặt \"done\": true.\n"
                f"Nếu vẫn còn bước tiếp theo (ví dụ: cần điền tiếp hoặc gửi), hãy đặt \"done\": false.\n"
                f"Chỉ xuất duy nhất một khối JSON hợp lệ theo đúng định dạng:"
            )

        raw_response = ""

        # Step 3: Execute via Background Service (Priority 1) or Extension (Priority 2)
        if gemini_service.is_ready:
            print(f"[Pipeline] [Bước {step}] Gửi tới Background Gemini Service...")
            try:
                raw_response = await gemini_service.send_prompt(
                    prompt=prompt,
                    image_path=screen_capturer.screenshot_path
                )
            except Exception as e:
                sound_manager.play_error()
                print(f"[Pipeline] Lỗi khi gọi gemini_service: {e}")
                err_text = f"Lỗi khi xử lý với Gemini: {e}"
                await hub.broadcast_webui({"type": "ERROR", "message": err_text, "user_command": user_command})
                await tts_service.speak("Có lỗi xảy ra khi kết nối tới Gemini, vui lòng thử lại.")
                return

        elif hub.extension_client is not None:
            print(f"[Pipeline] [Bước {step}] Gửi qua Extension WebSocket...")
            task_id = str(uuid.uuid4())
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            hub.pending_tasks[task_id] = future
            await hub.extension_client.send_json({
                "type": "EXECUTE_COMMAND",
                "id": task_id,
                "prompt": prompt,
                "imageBase64": screenshot_b64,
            })

            try:
                result_payload = await asyncio.wait_for(future, timeout=45.0)
                raw_response = result_payload.get("raw_text", "")
            except asyncio.TimeoutError:
                sound_manager.play_error()
                hub.pending_tasks.pop(task_id, None)
                timeout_msg = "Quá thời gian chờ phản hồi từ Gemini. Vui lòng thử lại câu lệnh."
                await hub.broadcast_webui({"type": "ERROR", "message": timeout_msg, "user_command": user_command})
                await tts_service.speak(timeout_msg)
                return

        print(f"[Pipeline] [Bước {step}] Phản hồi từ Gemini:\n{raw_response}")

        # Step 4: Robust JSON Parse
        action_data = extract_json_payload(raw_response)
        if not action_data:
            speech_text = raw_response.strip() or "Đã nhận lệnh nhưng chưa xác định được hành động tiếp theo."
            action_data = {"speech": speech_text, "actions": [{"action": "none"}], "done": True}

        speech_to_say = action_data.get("speech", "Đang thực hiện.")

        # Extract sequence of actions
        actions_list = action_data.get("actions", [])
        if not actions_list and "action" in action_data:
            actions_list = [action_data]

        is_done = action_data.get("done", True)

        # Smart heuristic: If step 1 only launched an app, but command requested actions afterwards
        # e.g. "mở Outlook và gửi email..." -> opening the app is just step 1!
        if is_first_step and len(actions_list) == 1 and actions_list[0].get("action") == "launch_app":
            lower_cmd = user_command.lower()
            if any(k in lower_cmd for k in [" và ", " rồi ", " sau đó ", " gửi ", " tìm ", " viết ", " soạn ", " nhập "]):
                print("[Pipeline] 💡 Phát hiện lệnh liên hoàn sau khi mở app, tiếp tục chuỗi tự hành...")
                is_done = False

        # Step 5: Annotate Screenshot for Visual Verification
        annotated_b64 = screen_capturer.annotate_actions(actions_list)

        # Step 6: Speak Spoken Response to User Concurrently
        speak_task = asyncio.create_task(tts_service.speak(speech_to_say))

        # Step 7: Execute Action Sequence on OS
        try:
            if len(actions_list) > 1:
                print(f"[Pipeline] ⚡ [Bước {step}] Đang thực thi chuỗi {len(actions_list)} hành động liên hoàn...")
                action_result = os_controller.execute_action_sequence(actions_list)
            elif len(actions_list) == 1:
                action_result = os_controller.execute_action(actions_list[0])
            else:
                action_result = {"success": True, "action": "none", "details": "No action needed"}
        except Exception as e:
            sound_manager.play_error()
            print(f"[Pipeline] Lỗi khi thực thi hành động: {e}")
            action_result = {"success": False, "action": "error", "details": str(e)}
            await speak_task
            break

        print(f"[Pipeline] [Bước {step}] Kết quả: {action_result}")

        # Step 8: Broadcast Step or Final Result to WebUI
        await hub.broadcast_webui({
            "type": "ACTION_COMPLETED" if is_done else "ACTION_STEP",
            "user_command": user_command,
            "speech": speech_to_say,
            "action_result": action_result,
            "annotated_image": annotated_b64,
            "step": step,
            "done": is_done,
        })

        # Wait for spoken audio to finish
        await speak_task

        # Check termination condition
        if is_done or not actions_list or all(a.get("action") in ("none", "read_screen") for a in actions_list):
            print(f"[Pipeline] ✅ Hoàn tất toàn bộ mục tiêu của người dùng sau {step} bước!")
            break

        # If more steps needed, wait briefly for new window/dialog to render
        delay = 1.2 if any(a.get("action") == "launch_app" for a in actions_list) else 0.8
        print(f"[Pipeline] ⏳ Đang tạm dừng {delay}s chờ giao diện mới mở ra để chụp màn hình tiếp theo...")
        await asyncio.sleep(delay)

    # All steps completed! Play completion chime
    sound_manager.play_done()
    print(f"\n[Pipeline] 🎉 HOÀN THÀNH TOÀN BỘ CHUỖI MỤC TIÊU!")




def start():
    """Entry point for running server."""
    print("=" * 60)
    print("      LUGA ASSIST - AI AGENT CHO NGƯỜI KHIẾM THỊ")
    print(f"      Giao diện Web:   http://{HOST}:{PORT}")
    print("      Trạng thái:      Sẵn sàng kết nối Extension")
    print("=" * 60)
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False, log_level="info")

if __name__ == "__main__":
    start()
