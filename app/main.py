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
from app.prompt_templates import build_gemini_prompt, build_verification_prompt
from app.gemini_service import gemini_service
from app.native_voice import NativeVoiceListener
from app.sound_effects import sound_manager
from app.accessibility import accessibility_manager

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
def strip_citations(text: str) -> str:
    """Strip all [cite: ...] markers and citation badges returned by Gemini."""
    if not text:
        return text
    # Remove all [cite: ...] badges (e.g. [cite: 1], [cite: 1, 2], [cite: url], etc.)
    cleaned = re.sub(r"\[\s*cite[^\]]*\]", "", text, flags=re.IGNORECASE)
    # Collapse multiple spaces or tabs
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    # Fix space before punctuation: "tóm tắt ." -> "tóm tắt."
    cleaned = re.sub(r"\s+([,.:;?!])", r"\1", cleaned)
    return cleaned.strip()

def clean_text_for_speech(text: str) -> str:
    """Clean markdown artifacts, headers, bullets, and file badges so TTS speaks naturally."""
    if not text:
        return text
    cleaned = strip_citations(text)
    cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    # Replace bullet marks (- or * or • or o ) with a clean natural pause
    cleaned = re.sub(r"^\s*[-*•oO]\s+", ". ", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[(JPG|PNG|JPEG|GIF|SVG|IMG)\]", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bJPG\b|\bPNG\b", "", cleaned)
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n. ", cleaned)
    cleaned = strip_citations(cleaned)
    return cleaned.strip()

def extract_payload_and_narrative(text: str) -> tuple[Optional[Dict[str, Any]], str]:
    """
    Robust JSON & Narrative extractor:
    Scans text using json.JSONDecoder to find valid JSON objects,
    and captures any surrounding markdown/narrative text (e.g. summaries, descriptions, answers)
    written before or after the JSON block.
    """
    if not text:
        return None, ""

    text = strip_citations(text)
    decoder = json.JSONDecoder()
    pos = 0
    candidates = []
    json_spans = []

    while pos < len(text):
        idx = text.find("{", pos)
        if idx == -1:
            break
        try:
            obj, end_pos = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                candidates.append(obj)
                json_spans.append((idx, end_pos))
            pos = end_pos
        except Exception:
            pos = idx + 1

    # Prioritize candidates that contain "actions" or "action", preferring the last one (final decided answer)
    chosen_payload = None
    for cand in reversed(candidates):
        if "actions" in cand or "action" in cand:
            chosen_payload = cand
            break

    if not chosen_payload and candidates:
        chosen_payload = candidates[-1]

    # Extract narrative (text outside the JSON block)
    narrative = ""
    if json_spans:
        first_start = json_spans[0][0]
        last_end = json_spans[-1][1]
        before = text[:first_start]
        after = text[last_end:]
        before = re.sub(r"```(?:json)?", "", before).strip()
        after = re.sub(r"```(?:json)?", "", after).strip()
        parts = [p for p in (before, after) if p]
        narrative = "\n\n".join(parts).strip()
    else:
        narrative = text.strip()

    return chosen_payload, strip_citations(narrative)

# Helper: Extract clean JSON from Gemini's response (backwards compatible)
def extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    payload, _ = extract_payload_and_narrative(text)
    return payload


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

    user_cmd_lower = user_command.lower().strip()
    # Direct fast-path: voice control for processing sound
    if any(k in user_cmd_lower for k in ("tắt tiếng processing", "ngắt tiếng processing", "tắt âm thanh xử lý", "tắt tiếng bíp", "tắt pulsing", "tắt tiếng nhịp tim")):
        sound_manager.set_pulse_enabled(False)
        sound_manager.play_done()
        msg = "Đã tắt âm thanh khi xử lý cho bạn."
        await tts_service.speak(msg)
        return

    if any(k in user_cmd_lower for k in ("bật tiếng processing", "bật âm thanh xử lý", "bật pulsing", "bật tiếng nhịp tim")):
        sound_manager.set_pulse_enabled(True)
        sound_manager.play_done()
        msg = "Đã bật lại âm thanh khi xử lý cho bạn."
        await tts_service.speak(msg)
        return

    # Start pulsing audio feedback for the user (only if enabled)
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
    last_actions_summary = ""
    is_goal_verified_completed = False

    while step < MAX_AUTONOMOUS_STEPS:
        step += 1
        is_first_step = (step == 1)
        print(f"\n[Pipeline] 🔄 --- BƯỚC {step}/{MAX_AUTONOMOUS_STEPS} cho mục tiêu: '{user_command}' ---")

        await hub.broadcast_webui({
            "type": "ACTION_PROGRESS",
            "message": f"Đang chụp màn hình và phân tích (Bước {step})...",
            "step": step,
        })

        # Step 2: Screen Capture with Dual-Tier Grid Overlay & UI Elements
        screenshot_b64, screen_size = screen_capturer.capture(with_grid=True)
        ui_context = accessibility_manager.get_ui_grounding_context()

        if is_first_step:
            prompt = build_gemini_prompt(user_command, ui_context=ui_context)
        else:
            # Verification Prompt: inspect screen after previous action
            prompt = build_verification_prompt(
                user_command=user_command,
                step=step,
                previous_actions_desc=last_actions_summary,
                ui_context=ui_context
            )

        raw_response = ""

        # Step 3: Execute via Background Service (Priority 1) or Extension (Priority 2)
        raw_response = ""
        used_background = False

        if gemini_service.is_ready:
            print(f"[Pipeline] [Bước {step}] Gửi tới Background Gemini Service...")
            try:
                raw_response = await gemini_service.send_prompt(
                    prompt=prompt,
                    image_path=screen_capturer.screenshot_path
                )
                used_background = True
            except Exception as e:
                print(f"[Pipeline] ⚠️ Background Gemini Service không khả dụng ({e})")
                gemini_service.is_ready = False
                # Notify extension to sync fresh cookies in background
                if hub.extension_client is not None:
                    try:
                        await hub.extension_client.send_json({"type": "SYNC_COOKIES"})
                    except Exception:
                        pass

        if not used_background:
            if hub.extension_client is not None:
                print(f"[Pipeline] 🔄 [Bước {step}] Tự động chuyển tiếp qua Chrome Extension...")
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
            else:
                sound_manager.play_error()
                err_text = (
                    "Session Google đã hết hạn và Chrome Extension chưa kết nối. "
                    "Vui lòng đảm bảo Chrome đã mở và bạn đã đăng nhập tài khoản Google."
                )
                await hub.broadcast_webui({"type": "ERROR", "message": err_text, "user_command": user_command})
                await tts_service.speak(err_text)
                return

        raw_response = strip_citations(raw_response)
        print(f"[Pipeline] [Bước {step}] Phản hồi từ Gemini:\n{raw_response}")
        # Stop pulsing audio cue immediately as soon as AI response has been received
        sound_manager.stop_pulsing()

        # Step 4: Robust JSON Parse & Narrative Extraction
        action_data, narrative_text = extract_payload_and_narrative(raw_response)
        if not action_data:
            speech_text = narrative_text.strip() or "Đang kiểm tra kết quả màn hình."
            action_data = {"speech": speech_text, "actions": [{"action": "none"}], "done": True}

        # Check for summary or description fields inside JSON
        summary_inside = (
            action_data.get("description")
            or action_data.get("summary")
            or action_data.get("answer")
            or action_data.get("content")
        )

        speech_to_say = action_data.get("speech", "Đang thực hiện.")

        # Extract sequence of actions
        actions_list = action_data.get("actions", [])
        if not actions_list and "action" in action_data:
            actions_list = [action_data]

        active_actions = [
            a for a in actions_list
            if isinstance(a, dict) and a.get("action", "").lower() not in ("none", "read_screen", "wait")
        ]
        is_passive_only = len(active_actions) == 0
        claimed_done = bool(action_data.get("done", False))

        # SPECIAL HANDLING FOR SUMMARY / SCREEN DESCRIPTION / INFORMATIONAL REQUESTS:
        if is_passive_only:
            # Detect placeholder starters in speech_to_say (e.g. 'Đang tóm tắt...', 'Đang miêu tả...')
            placeholder_starters = (
                "đang tóm tắt", "đang miêu tả", "đang mô tả", "đang đọc", 
                "tôi đang xem", "đang kiểm tra", "đang nhìn", "dưới đây là", "sau đây là",
                "đang trả lời", "tôi đang tóm tắt"
            )
            is_placeholder = (
                any(speech_to_say.lower().strip().startswith(p) for p in placeholder_starters)
                or len(speech_to_say.split()) <= 12
            )

            # If narrative text outside JSON exists and has substance (e.g. YouTube summary outside JSON):
            if narrative_text and len(narrative_text.strip()) > 30:
                print(f"[Pipeline] 📝 Phát hiện nội dung tóm tắt/miêu tả ngoài JSON ({len(narrative_text)} ký tự).")
                speech_to_say = narrative_text.strip()
            elif summary_inside and len(summary_inside.strip()) > len(speech_to_say):
                speech_to_say = summary_inside.strip()

        # Clean speech text from citations and markdown artifacts for natural TTS audio
        speech_to_say = strip_citations(speech_to_say)
        speech_for_tts = clean_text_for_speech(speech_to_say)

        # ANTI-HALLUCINATION / OUTCOME VERIFICATION LOGIC:
        if is_passive_only:
            if is_first_step:
                # User asked a question or asked to read screen: no physical action needed
                is_goal_verified_completed = True
            else:
                # This was a verification turn! If Gemini inspected the screen and confirms completion:
                if claimed_done:
                    # EXTRA GUARD FOR EMAIL: Verify compose window is genuinely closed
                    user_cmd_lower = user_command.lower()
                    is_email_intent = any(k in user_cmd_lower for k in ("gửi email", "gửi thư", "send email", "soạn thư", "gửi mail"))
                    if is_email_intent and accessibility_manager.is_compose_window_active():
                        print("[Pipeline] ⚠️ CẢNH BÁO KIỂM CHỨNG: Gemini báo hoàn thành nhưng cửa sổ/khung soạn thư vẫn còn mở trên màn hình!")
                        is_goal_verified_completed = False
                        speech_to_say = "Thư chưa gửi đi được, đang thực hiện gửi lại."
                        speech_for_tts = speech_to_say
                        actions_list = [{"action": "click", "target": "send"}, {"action": "press", "key": "cmd+return"}]
                        active_actions = actions_list
                    else:
                        is_goal_verified_completed = True
                        print(f"[Pipeline] 🎯 ĐÃ XÁC MINH HOÀN TẤT MỤC TIÊU 100% (Outcome Verified) tại bước {step}!")
                else:
                    is_goal_verified_completed = False
        else:
            # Active manipulation actions exist (click, type, press, launch_app, focus, send_email, system_control).
            # CHECK FOR IMMEDIATE COMPLETION:
            # System controls (sleep, mute, unmute, volume, lock) or simple instant actions do NOT need
            # a secondary screenshot verification loop.
            all_system = all(
                isinstance(a, dict) and a.get("action", "").lower() in (
                    "system_control", "system", "sleep", "mute", "unmute", "volume_up", "volume_down", "lock",
                    "terminal_command", "terminal", "run_terminal", "bash", "cmd", "powershell", "powershell_command",
                    "find_files", "find_file", "search_file", "search_files", "open_file", "open", "open_folder",
                    "list_files", "list_dir", "dir", "ls", "read_file", "cat", "view_file",
                    "create_file", "write_file", "new_file", "delete_file", "remove_file", "trash_file"
                )
                for a in active_actions
            )
            is_complex_form = any(
                isinstance(a, dict) and (
                    a.get("action", "").lower() in ("send_email", "compose_email")
                    or (a.get("action", "").lower() == "type" and a.get("target") in ("to", "recipients", "subject"))
                )
                for a in active_actions
            )

            if all_system or (claimed_done and not is_complex_form):
                is_goal_verified_completed = True
                print(f"[Pipeline] ⚡ Thao tác tức thì hoàn tất tại bước {step} (không cần chụp ảnh thẩm định lại): {speech_to_say}")
            else:
                is_goal_verified_completed = False

        # Step 5: Annotate Screenshot for Visual Feedback
        annotated_b64 = screen_capturer.annotate_actions(actions_list)

        # Step 6: Speak Spoken Response to User Concurrently
        speak_task = asyncio.create_task(tts_service.speak(speech_for_tts))

        # Step 7: Execute Action Sequence on OS (if active actions exist)
        action_result = {"success": True, "action": "none", "details": "Verified state"}
        if active_actions:
            try:
                if len(actions_list) > 1:
                    print(f"[Pipeline] ⚡ [Bước {step}] Đang thực thi chuỗi {len(actions_list)} hành động liên hoàn...")
                    action_result = os_controller.execute_action_sequence(actions_list)
                elif len(actions_list) == 1:
                    action_result = os_controller.execute_action(actions_list[0])
            except Exception as e:
                sound_manager.play_error()
                print(f"[Pipeline] Lỗi khi thực thi hành động: {e}")
                action_result = {"success": False, "action": "error", "details": str(e)}
                await speak_task
                break

            # Build readable summary of what was executed to feed into next verification step
            last_actions_summary = "; ".join([
                f"{a.get('action')}" + (f" vào '{a.get('target')}'" if a.get('target') else "") +
                (f" text='{a.get('text')}'" if a.get('text') else "") +
                (f" key='{a.get('key')}'" if a.get('key') else "") +
                (f" query='{a.get('query')}'" if a.get('query') else "") +
                (f" path='{a.get('path')}'" if a.get('path') else "") +
                (f" cmd='{a.get('command')}'" if a.get('command') else "")
                for a in active_actions
            ])
            if action_result.get("details"):
                last_actions_summary += f" | Kết quả: {action_result.get('details')[:250]}"
            print(f"[Pipeline] [Bước {step}] Đã thực thi xong: {last_actions_summary}")

        # Step 8: Broadcast Step or Verified Final Result to WebUI
        await hub.broadcast_webui({
            "type": "ACTION_COMPLETED" if is_goal_verified_completed else "ACTION_STEP",
            "user_command": user_command,
            "speech": speech_to_say,
            "action_result": action_result,
            "annotated_image": annotated_b64,
            "step": step,
            "done": is_goal_verified_completed,
        })

        # Wait for spoken audio to finish
        await speak_task

        # If action returned dynamic speech result (e.g. search results, terminal output, read file), speak it!
        dynamic_speech = action_result.get("speech_result")
        if dynamic_speech and dynamic_speech != speech_to_say:
            print(f"[Pipeline] 🗣️ Báo cáo kết quả trực tiếp: \"{dynamic_speech}\"")
            await tts_service.speak(dynamic_speech)

        # Check termination condition
        if is_goal_verified_completed:
            print(f"[Pipeline] ✅ Hoàn tất và ĐÃ XÁC MINH mục tiêu sau {step} bước!")
            break

        # If more steps needed, wait briefly for new window/dialog/state to settle
        delay = 1.0 if any(a.get("action") == "launch_app" for a in actions_list) else 0.7
        print(f"[Pipeline] ⏳ Đang tạm dừng {delay}s chờ giao diện cập nhật để chụp ảnh thẩm định kết quả...")
        await asyncio.sleep(delay)

    # Completion handling
    if is_goal_verified_completed:
        sound_manager.play_done()
        print(f"\n[Pipeline] 🎉 HOÀN THÀNH VÀ ĐÃ XÁC MINH TOÀN BỘ MỤC TIÊU!")
    else:
        sound_manager.play_error()
        print(f"\n[Pipeline] ⚠️ Đã dừng sau {MAX_AUTONOMOUS_STEPS} bước mà chưa xác minh được kết quả hoàn tất.")
        await tts_service.speak("Chưa thể xác nhận hoàn tất thao tác. Bạn vui lòng kiểm tra lại màn hình.")




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
