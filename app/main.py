"""
Luga Assist - Master FastAPI Server & WebSocket Hub.
Coordinates Voice UI, Screen Capture, Gemini Web Extension, OS Controller, and TTS.
"""
import re
import json
import uuid
import asyncio
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

app = FastAPI(title="Luga Assist Local Server", version="1.0.0")

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
    """Extract JSON object from markdown blocks or raw text."""
    if not text:
        return None

    # Try 1: Code fence ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Try 2: Find outermost curly braces { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

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


# Master Pipeline Execution
async def process_user_command(user_command: str, voice: str):
    print(f"\n[Pipeline] New Voice Command: '{user_command}'")

    # Step 1: Check Connection (Gemini Background Service or Extension)
    is_gemini_ready = gemini_service.is_ready or (hub.extension_client is not None)
    if not is_gemini_ready:
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

    await hub.broadcast_webui({
        "type": "ACTION_PROGRESS",
        "message": "Đang chụp màn hình và phân tích...",
    })

    # Step 2: Screen Capture with Grid Overlay
    screenshot_b64, screen_size = screen_capturer.capture(with_grid=True)
    full_prompt = build_gemini_prompt(user_command)

    raw_response = ""

    # Step 3: Execute via Background Service (Priority 1) or Extension (Priority 2)
    if gemini_service.is_ready:
        print("[Pipeline] Thực thi trực tiếp qua Background Gemini Service...")
        await hub.broadcast_webui({
            "type": "ACTION_PROGRESS",
            "message": "Gemini đang xử lý trực tiếp dưới nền...",
        })
        try:
            raw_response = await gemini_service.send_prompt(
                prompt=full_prompt,
                image_path=screen_capturer.screenshot_path
            )
        except Exception as e:
            print(f"[Pipeline] Lỗi khi gọi gemini_service: {e}")
            err_text = f"Lỗi khi xử lý với Gemini: {e}"
            await hub.broadcast_webui({"type": "ERROR", "message": err_text, "user_command": user_command})
            await tts_service.speak("Có lỗi xảy ra khi kết nối tới Gemini, vui lòng thử lại.")
            return

    elif hub.extension_client is not None:
        print("[Pipeline] Thực thi qua Chrome Extension WebSocket...")
        task_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        hub.pending_tasks[task_id] = future
        await hub.extension_client.send_json({
            "type": "EXECUTE_COMMAND",
            "id": task_id,
            "prompt": full_prompt,
            "imageBase64": screenshot_b64,
        })

        await hub.broadcast_webui({
            "type": "ACTION_PROGRESS",
            "message": "Gemini đang xử lý hình ảnh và câu lệnh...",
        })

        try:
            result_payload = await asyncio.wait_for(future, timeout=45.0)
            raw_response = result_payload.get("raw_text", "")
        except asyncio.TimeoutError:
            hub.pending_tasks.pop(task_id, None)
            timeout_msg = "Quá thời gian chờ phản hồi từ Gemini. Vui lòng thử lại câu lệnh."
            await hub.broadcast_webui({"type": "ERROR", "message": timeout_msg, "user_command": user_command})
            await tts_service.speak(timeout_msg)
            return

    print(f"[Pipeline] Phản hồi từ Gemini:\n{raw_response}")

    # Step 5: Parse JSON Action
    action_data = extract_json_payload(raw_response)
    if not action_data:
        # Fallback: treat whole text as speech if Gemini replied in prose
        speech_text = raw_response.strip() or "Tôi đã nhận được lệnh nhưng chưa xác định được hành động."
        action_data = {"speech": speech_text, "action": "none"}

    speech_to_say = action_data.get("speech", "Đang thực hiện yêu cầu của bạn.")
    action_type = action_data.get("action", "none")
    x_percent = action_data.get("x_percent")
    y_percent = action_data.get("y_percent")

    # Step 6: Annotate Screenshot for Visual Verification
    annotated_b64 = None
    if x_percent is not None and y_percent is not None:
        annotated_b64 = screen_capturer.annotate_action(
            float(x_percent), float(y_percent), action_type
        )

    # Step 7: Speak Spoken Response to Visually Impaired User
    speak_task = asyncio.create_task(tts_service.speak(speech_to_say))

    # Step 8: Execute Mouse/Keyboard Action on OS
    action_result = os_controller.execute_action(action_data)
    print(f"[Pipeline] Action execution result: {action_result}")

    # Await voice completion if needed
    await speak_task

    # Step 9: Broadcast Action Completed to WebUI
    await hub.broadcast_webui({
        "type": "ACTION_COMPLETED",
        "user_command": user_command,
        "speech": speech_to_say,
        "action_result": action_result,
        "annotated_image": annotated_b64,
    })


@app.on_event("startup")
async def on_startup():
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
