"""
Luga Assist - Master FastAPI Server & WebSocket Hub.
Coordinates Voice UI, Screen Capture, Gemini Vision Reasoning, OS Controller, and TTS.
"""
import re
import os
import sys
import io
from pathlib import Path

# Guard against PyInstaller windowless mode (console=False) setting stdout/stderr to None
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stdout = io.StringIO()

if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        sys.stderr = io.StringIO()

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


import json
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import threading
import uvicorn
import webbrowser

from app.config import (
    BASE_DIR,
    HOST,
    PORT,
    WEB_DIR,
    DEFAULT_TTS_VOICE,
    DEFAULT_THINKING_LEVEL,
    PID_FILE,
)
from app.logger import setup_logging, get_logger, read_recent_logs, clear_logs

# Initialize persistent logging and stdout teeing BEFORE importing other app services
setup_logging()

from app.browser_helper import ensure_background_browser
from app.screen_capture import screen_capturer
from app.os_controller import os_controller
from app.tts_service import tts_service
from app.prompt_templates import build_gemini_prompt, build_verification_prompt
from app.gemini_service import gemini_service
from gemini_webapi.exceptions import AuthError
from app.native_voice import NativeVoiceListener
from app.sound_effects import sound_manager
from app.accessibility import accessibility_manager
from app.system_ui import (
    show_desktop_notification,
    trigger_graceful_shutdown,
    trigger_graceful_restart,
)

spotlight_process: Optional[subprocess.Popen] = None
spotlight_clients: set = set()
spotlight_clients_lock = threading.Lock()
server_async_loop: Optional[asyncio.AbstractEventLoop] = None

async def broadcast_to_spotlight(payload: dict):
    with spotlight_clients_lock:
        clients = list(spotlight_clients)
    for ws in clients:
        try:
            await ws.send_json(payload)
        except Exception:
            pass

def send_spotlight_action_sync(action: str, **kwargs):
    """Safely send command to connected Spotlight HUD from sync threads or hotkey callbacks."""
    global server_async_loop
    payload = {"action": action, **kwargs}
    if server_async_loop and server_async_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_to_spotlight(payload), server_async_loop)

def launch_spotlight_hud() -> Optional[subprocess.Popen]:
    """Launch native Spotlight Floating Chat HUD in background."""
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR)
        env["LUGA_SPAWNED_BY_MAIN"] = "1"
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--spotlight-ui"]
        else:
            cmd = [sys.executable, "-m", "app.spotlight_ui"]
        
        log_file = BASE_DIR / "logs" / "spotlight_ui.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fp = open(log_file, "a", encoding="utf-8")
        
        flags = 0x08000000 if sys.platform.startswith("win") else 0
        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=fp,
            stderr=fp,
            creationflags=flags
        )
        print(f"[Lifespan] 🚀 Đã khởi động Cửa sổ Chat Nổi Spotlight HUD (PID: {proc.pid})")
        return proc
    except Exception as e:
        print(f"[Lifespan] ⚠️ Không thể khởi động Spotlight HUD: {e}")
        return None

native_voice_instance: Optional[NativeVoiceListener] = None
voice_status_lock = threading.Lock()
current_voice_status = {
    "state": "idle",
    "text": "",
    "message": "",
    "timestamp": time.time(),
}

def update_global_voice_status(state: str, text_or_msg: str):
    global current_voice_status
    with voice_status_lock:
        current_voice_status = {
            "state": state,
            "text": text_or_msg if state == "transcribed" else "",
            "message": text_or_msg if state != "transcribed" else f'"{text_or_msg}"',
            "timestamp": time.time(),
        }

pipeline_abort_event = threading.Event()

def cancel_active_pipeline():
    """Cancel any active pipeline execution, TTS speech, and sound cues."""
    print("\n[Pipeline] ⏹️ Kích hoạt ngắt khẩn cấp (Emergency Cancel Active Pipeline)!")
    pipeline_abort_event.set()
    tts_service.stop_speaking()
    sound_manager.stop_pulsing()
    sound_manager.play_error()
    update_global_voice_status("idle", "⏹️ Đã ngắt tác vụ đang xử lý!")
    send_spotlight_action_sync("cancel")
    show_desktop_notification("Luga Assist", "⏹️ Đã ngắt tác vụ đang xử lý!")
    # Cancel any pending extension futures
    for task_id, fut in list(hub.pending_tasks.items()):
        if not fut.done():
            fut.cancel()
    if server_async_loop and server_async_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            hub.broadcast_webui({
                "type": "ACTION_CANCELLED",
                "message": "Đã ngắt tác vụ đang xử lý theo lệnh người dùng."
            }),
            server_async_loop
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    global native_voice_instance, server_async_loop
    loop = asyncio.get_running_loop()
    server_async_loop = loop
    # 1. Start Global Native Voice & Hotkey Listener IMMEDIATELY (Zero delay for F7/F8/F9/F10!)

    def handle_native_voice_command(cmd_text: str):
        print(f"\n[Global Handler] Đã nhận lệnh từ Micro: \"{cmd_text}\"")
        asyncio.run_coroutine_threadsafe(
            process_user_command(cmd_text, DEFAULT_TTS_VOICE, thinking_level=current_thinking_level), loop
        )

    def handle_native_mode_toggle():
        print("\n[Global Handler] Đã nhận tín hiệu chuyển đổi chế độ từ phím F9!")
        asyncio.run_coroutine_threadsafe(toggle_mode(), loop)

    def handle_native_spotlight_toggle():
        print("\n[Global Handler] Đã nhận tín hiệu F7 -> Bật/Tắt Cửa sổ Web Spotlight!")
        from app.spotlight_launcher import launch_or_toggle_web_spotlight
        launch_or_toggle_web_spotlight()

    native_voice_instance = NativeVoiceListener(
        on_command_callback=handle_native_voice_command,
        on_mode_toggle_callback=handle_native_mode_toggle,
        on_spotlight_toggle_callback=handle_native_spotlight_toggle,
        on_cancel_callback=cancel_active_pipeline,
        on_status_callback=update_global_voice_status,
    )
    native_voice_instance.start_global_hotkeys()

    # 2. Initialize background Gemini session asynchronously (never block server startup)
    async def _init_gemini_bg():
        try:
            print("[Lifespan] 🔄 Đang tự động khôi phục session Google Gemini từ phiên trước...")
            ok = await gemini_service.auto_init_from_disk()
            if ok or gemini_service.is_ready:
                print("[Lifespan] ✅ Session Google Gemini đã sẵn sàng từ phiên lưu trước.")
                await hub.broadcast_status()
                await hub.broadcast_webui({
                    "type": "STATUS_UPDATE",
                    "gemini_ready": True,
                    "message": "Session Google Gemini đã sẵn sàng."
                })
            else:
                print("[Lifespan] ℹ️ Chưa có session Google Gemini hoặc cookie hết hạn.")
                await hub.broadcast_status()
                await hub.broadcast_webui({
                    "type": "STATUS_UPDATE",
                    "gemini_ready": False
                })
        except Exception as e:
            print(f"[Lifespan] Background session init: {e}")
            await hub.broadcast_status()

    asyncio.create_task(_init_gemini_bg())

    # 3. Auto-launch Web Spotlight popup immediately on startup (zero Alt-Tab required)
    def _auto_show_spotlight_on_startup():
        time.sleep(0.8)
        try:
            from app.spotlight_launcher import launch_or_toggle_web_spotlight
            print("[Lifespan] 🚀 Tự động mở cửa sổ Web Spotlight (F7) trên màn hình...")
            launch_or_toggle_web_spotlight(force_show=True)
        except Exception as e:
            print(f"[Lifespan] Lỗi mở Web Spotlight lúc khởi động: {e}")

    threading.Thread(target=_auto_show_spotlight_on_startup, daemon=True).start()

    yield

    # Clean up and persist rotated cookies on shutdown
    try:
        gemini_service._sync_cookies_to_disk()
    except Exception:
        pass

    # Clean up Spotlight HUD on server shutdown
    if spotlight_process:
        try:
            spotlight_process.terminate()
            spotlight_process.wait(timeout=1.0)
        except Exception:
            pass

    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

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
        self.spotlight_clients = set()
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
        self.spotlight_clients.discard(ws)

    def register_spotlight(self, ws: WebSocket):
        self.spotlight_clients.add(ws)

    def unregister_spotlight(self, ws: WebSocket):
        self.spotlight_clients.discard(ws)

    def is_spotlight_open(self) -> bool:
        return len(self.spotlight_clients) > 0

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
            "restoring_session": getattr(gemini_service, "is_restoring", False),
            "mode": current_mode,
            "thinking_level": current_thinking_level,
        }
        dead_clients = []
        for client in list(self.webui_clients):
            try:
                await client.send_json(payload)
            except Exception:
                dead_clients.append(client)
        for dc in dead_clients:
            self.webui_clients.discard(dc)
            self.spotlight_clients.discard(dc)

    async def broadcast_webui(self, payload: Dict[str, Any]):
        dead_clients = []
        for client in list(self.webui_clients):
            try:
                await client.send_json(payload)
            except Exception:
                dead_clients.append(client)
        for dc in dead_clients:
            self.webui_clients.discard(dc)
            self.spotlight_clients.discard(dc)

# Operating Mode: "control" (Computer Control) or "chat" (AI Conversational Mode)
current_mode: str = "control"

hub = ConnectionHub()

# Mode Payloads
class SetModePayload(BaseModel):
    mode: str
    announce: Optional[bool] = True

class ChatPayload(BaseModel):
    message: str
    voice: Optional[str] = DEFAULT_TTS_VOICE
    speak: Optional[bool] = True

async def set_mode(mode: str, announce: bool = True) -> str:
    global current_mode
    cleaned = (mode or "").strip().lower()
    if cleaned not in ("control", "chat"):
        cleaned = "control"
    current_mode = cleaned
    print(f"\n[Mode] 🔄 Đã chuyển sang chế độ: {current_mode.upper()}")
    sound_manager.play_done()
    await hub.broadcast_webui({
        "type": "MODE_CHANGED",
        "mode": current_mode,
    })
    if announce:
        if current_mode == "chat":
            speech = "Đã chuyển sang chế độ trò chuyện AI. Bạn có thể hỏi đáp tự nhiên mà không cần thao tác màn hình."
        else:
            speech = "Đã chuyển sang chế độ điều khiển máy tính."
        await tts_service.speak(speech)
    return current_mode

async def toggle_mode(announce: bool = True) -> str:
    global current_mode
    new_mode = "chat" if current_mode == "control" else "control"
    return await set_mode(new_mode, announce=announce)


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

@app.get("/popup")
async def serve_popup():
    return FileResponse(str(WEB_DIR / "popup.html"))

@app.get("/popup.js")
async def serve_popup_js():
    return FileResponse(str(WEB_DIR / "popup.js"))

@app.get("/spotlight")
async def serve_spotlight():
    return FileResponse(str(WEB_DIR / "spotlight.html"))

@app.get("/spotlight.js")
async def serve_spotlight_js():
    return FileResponse(str(WEB_DIR / "spotlight.js"))

@app.post("/api/auth/google/start")
async def api_auth_google_start():
    from app.google_auth import google_auth_manager
    res = await google_auth_manager.start_web_login(hub.broadcast_webui)
    return res

@app.get("/api/auth/google/status")
async def api_auth_google_status():
    from app.google_auth import google_auth_manager
    return {
        "status": "ok",
        "gemini_ready": gemini_service.is_ready,
        "restoring_session": getattr(gemini_service, "is_restoring", False),
        "is_logging_in": google_auth_manager.is_logging_in,
    }

@app.post("/api/auth/google/cancel")
async def api_auth_google_cancel():
    from app.google_auth import google_auth_manager
    google_auth_manager.cancel_login()
    return {"status": "ok", "message": "Đã hủy tiến trình đăng nhập Google"}

@app.post("/api/auth/google/logout")
async def api_auth_google_logout():
    from app.google_auth import google_auth_manager
    res = await google_auth_manager.logout(clear_browser_profile=False)
    await hub.broadcast_status()
    await hub.broadcast_webui({
        "type": "GOOGLE_AUTH_LOGGED_OUT",
        "gemini_ready": False,
        "message": "Đã đăng xuất tài khoản Google."
    })
    return res

@app.post("/api/auth/google/switch")
async def api_auth_google_switch():
    from app.google_auth import google_auth_manager
    res = await google_auth_manager.switch_account(hub.broadcast_webui)
    await hub.broadcast_status()
    return res

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "gemini_ready": gemini_service.is_ready or (hub.extension_client is not None),
        "restoring_session": getattr(gemini_service, "is_restoring", False),
        "gemini_background_mode": gemini_service.is_ready,
        "extension_connected": hub.extension_client is not None,
        "mode": current_mode,
        "screen_size": os_controller.get_screen_size(),
    }

@app.get("/api/mode")
async def get_current_mode():
    return {"status": "ok", "mode": current_mode}

@app.post("/api/set_mode")
async def api_set_mode(payload: SetModePayload):
    mode = await set_mode(payload.mode, announce=payload.announce if payload.announce is not None else True)
    return {"status": "ok", "mode": mode}

current_thinking_level: str = DEFAULT_THINKING_LEVEL

class ThinkingLevelPayload(BaseModel):
    thinking_level: str

@app.get("/api/thinking_level")
async def api_get_thinking_level():
    return {"status": "ok", "thinking_level": current_thinking_level}

@app.post("/api/thinking_level")
async def api_set_thinking_level(payload: ThinkingLevelPayload):
    global current_thinking_level
    lvl = (payload.thinking_level or "").strip().lower()
    if lvl not in ("low", "medium", "high"):
        lvl = "medium"
    current_thinking_level = lvl
    gemini_service.set_thinking_level(lvl)
    await hub.broadcast_webui({
        "type": "THINKING_LEVEL_CHANGED",
        "thinking_level": current_thinking_level
    })
    return {"status": "ok", "thinking_level": current_thinking_level}

class CommandPayload(BaseModel):
    command: str
    voice: Optional[str] = DEFAULT_TTS_VOICE
    speak: Optional[bool] = True
    thinking_level: Optional[str] = None

@app.post("/api/command")
async def api_command(payload: CommandPayload):
    """Execute a text command to control the computer or query the system."""
    cmd = (payload.command or "").strip()
    if not cmd:
        return {"status": "error", "message": "Command cannot be empty"}
    try:
        res = await process_user_command(
            cmd,
            voice=payload.voice or DEFAULT_TTS_VOICE,
            speak=payload.speak if payload.speak is not None else True,
            thinking_level=payload.thinking_level or current_thinking_level
        )
        return {"status": "ok", **res}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "success": False,
            "speech": f"Lỗi xử lý câu lệnh: {e}",
            "action_result": {"success": False, "error": str(e)}
        }

class ChatPayload(BaseModel):
    message: str
    voice: Optional[str] = DEFAULT_TTS_VOICE
    speak: Optional[bool] = True
    thinking_level: Optional[str] = None

@app.post("/api/chat")
async def api_chat(payload: ChatPayload):
    """Chat endpoint to instruct the system via text and receive action/answer."""
    cmd = (payload.message or "").strip()
    if not cmd:
        return {"status": "error", "response": ""}
    try:
        res = await process_user_command(
            cmd,
            voice=payload.voice or DEFAULT_TTS_VOICE,
            speak=payload.speak if payload.speak is not None else True,
            thinking_level=payload.thinking_level or current_thinking_level
        )
        if not isinstance(res, dict):
            res = {"success": False, "speech": "Không nhận được phản hồi từ hệ thống."}
        speech = res.get("speech", "")
        dyn = res.get("action_result", {}).get("speech_result")
        if dyn and dyn != speech:
            speech = f"{speech}\n{dyn}"
        return {"status": "ok", "response": speech, **res}
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = f"Lỗi xử lý câu lệnh: {e}"
        return {
            "status": "error",
            "response": err_msg,
            "speech": err_msg,
            "success": False,
            "action_result": {"success": False, "error": str(e)}
        }

@app.post("/api/chat/clear")
async def api_chat_clear():
    gemini_service.reset_conversation()
    await hub.broadcast_webui({"type": "CHAT_CLEARED"})
    return {"status": "ok"}

@app.post("/api/cancel")
async def api_cancel():
    """Emergency stop/cancel currently active task, voice recording, or speech."""
    if native_voice_instance:
        native_voice_instance.cancel_all()
    else:
        cancel_active_pipeline()
    return {"status": "ok", "message": "Đã ngắt tác vụ đang xử lý"}

@app.post("/api/set_session")
async def set_session(payload: SessionPayload):
    """Receive Google Gemini session cookies from Chrome Extension."""
    ok = await gemini_service.init_session(payload.secure_1psid, payload.secure_1psidts)
    await hub.broadcast_status()
    return {"status": "ok" if ok else "error", "ready": gemini_service.is_ready}

@app.get("/api/debug_status")
def debug_status():
    from app.accessibility import ensure_accessibility_permissions
    is_trusted = ensure_accessibility_permissions(prompt=False)
    l = native_voice_instance._hotkey_listener if native_voice_instance else None
    return {
        "is_trusted": is_trusted,
        "hotkeys_active": native_voice_instance._hotkeys_active if native_voice_instance else False,
        "listener_is_none": l is None,
        "listener_alive": l.is_alive() if l else False,
    }

@app.get("/api/logs")
async def get_system_logs(lines: int = 150):
    """Fetch recent system logs for debugging."""
    return {
        "status": "ok",
        "lines": read_recent_logs(lines)
    }

@app.post("/api/logs/clear")
async def clear_system_logs():
    """Clear debug logs."""
    ok = clear_logs()
    return {"status": "ok" if ok else "error"}

@app.post("/api/ensure_browser")
async def api_ensure_browser():
    """Trigger background Chrome launch if needed."""
    ok = ensure_background_browser(force=True)
    return {"status": "ok" if ok else "error"}


class SystemActionPayload(BaseModel):
    speak: Optional[bool] = True
    delay: Optional[float] = 1.0

@app.post("/api/system/shutdown")
async def api_system_shutdown(payload: Optional[SystemActionPayload] = None):
    """Gracefully shut down Luga Assist with voice feedback and desktop notification."""
    spk = payload.speak if (payload and payload.speak is not None) else True
    dly = payload.delay if (payload and payload.delay is not None) else 1.0
    await trigger_graceful_shutdown(delay=dly, speak=spk)
    return {"status": "ok", "message": "Đang tắt hệ thống Luga Assist..."}

@app.post("/api/system/restart")
async def api_system_restart(payload: Optional[SystemActionPayload] = None):
    """Gracefully restart Luga Assist."""
    dly = payload.delay if (payload and payload.delay is not None) else 1.0
    await trigger_graceful_restart(delay=dly)
    return {"status": "ok", "message": "Đang khởi động lại Luga Assist..."}

@app.get("/api/system/status")
async def api_system_status():
    """Detailed health report for WebUI status dialog and native inspectors."""
    screen_w, screen_h = os_controller.get_screen_size()
    gem_ready = gemini_service.is_ready or (hub.extension_client is not None)
    from app.audio_manager import audio_manager
    active_mic_id, active_mic_name = audio_manager.get_active_device_index()
    return {
        "status": "online",
        "app_name": "Luga Assist",
        "version": "1.0.0",
        "mode": current_mode,
        "mode_label": "Điều khiển máy tính" if current_mode == "control" else "Trò chuyện AI",
        "gemini_ready": gem_ready,
        "extension_connected": hub.extension_client is not None,
        "gemini_background_mode": gemini_service.is_ready,
        "screen_resolution": f"{screen_w}x{screen_h}",
        "screen_width": screen_w,
        "screen_height": screen_h,
        "tts_voice": DEFAULT_TTS_VOICE,
        "active_microphone_id": active_mic_id,
        "active_microphone": active_mic_name,
        "pid": os.getpid(),
    }


class AudioDevicePayload(BaseModel):
    device: Any


class AudioTestPayload(BaseModel):
    device_id: Optional[int] = None
    duration: Optional[float] = 0.5


@app.get("/api/audio/devices")
async def api_audio_devices():
    """List available microphones and get active device."""
    from app.audio_manager import audio_manager
    devices = audio_manager.list_input_devices(force_refresh=True)
    active_id, active_name = audio_manager.get_active_device_index()
    return {
        "status": "ok",
        "devices": devices,
        "active_id": active_id,
        "active_name": active_name
    }


@app.post("/api/audio/device")
async def api_set_audio_device(payload: AudioDevicePayload):
    """Set active microphone by name or id."""
    from app.audio_manager import audio_manager
    res = audio_manager.set_active_device(payload.device)
    active_id, active_name = audio_manager.get_active_device_index()
    return {
        "status": "ok",
        "selected": res,
        "active_id": active_id,
        "active_name": active_name
    }


@app.post("/api/audio/test")
async def api_test_audio(payload: Optional[AudioTestPayload] = None):
    """Test microphone signal level (RMS and peak) non-blockingly."""
    from app.audio_manager import audio_manager
    dev_id = payload.device_id if payload else None
    dur = payload.duration if (payload and payload.duration) else 0.5
    res = await asyncio.to_thread(audio_manager.test_microphone_level, dev_id, dur)
    return {"status": "ok", **res}


@app.post("/api/voice/trigger")
async def api_voice_trigger():
    """Trigger voice listening flow programmatically (e.g. from UI mic button)."""
    if native_voice_instance:
        threading.Thread(target=native_voice_instance.trigger_voice_flow, daemon=True).start()
        return {"status": "ok", "message": "Voice trigger initiated"}
    return {"status": "error", "message": "Native voice listener not available"}


@app.get("/api/voice/status")
async def api_voice_status():
    """Get current voice listening and recognition status for Spotlight HUD."""
    with voice_status_lock:
        return dict(current_voice_status)


@app.websocket("/ws/spotlight")
async def ws_spotlight_endpoint(websocket: WebSocket):
    """Bidirectional WebSocket connection for Spotlight Floating HUD."""
    await websocket.accept()
    with spotlight_clients_lock:
        spotlight_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        with spotlight_clients_lock:
            spotlight_clients.discard(websocket)


@app.get("/api/spotlight/show")
@app.post("/api/spotlight/show")
async def api_spotlight_show():
    from app.spotlight_ui import get_spotlight_hud
    hud = get_spotlight_hud()
    if hud:
        hud.show()
    from app.spotlight_launcher import launch_or_toggle_web_spotlight
    launch_or_toggle_web_spotlight()
    await broadcast_to_spotlight({"action": "show"})
    return {"status": "ok", "visible": True}

@app.get("/api/spotlight/hide")
@app.post("/api/spotlight/hide")
async def api_spotlight_hide():
    from app.spotlight_launcher import minimize_spotlight_window_windows
    minimized = minimize_spotlight_window_windows()
    from app.spotlight_ui import get_spotlight_hud
    hud = get_spotlight_hud()
    if hud:
        hud.hide()
    await broadcast_to_spotlight({"action": "hide"})
    return {"status": "ok", "visible": False, "minimized": minimized}

@app.get("/api/spotlight/toggle")
@app.post("/api/spotlight/toggle")
async def api_spotlight_toggle():
    from app.spotlight_ui import get_spotlight_hud
    hud = get_spotlight_hud()
    if hud:
        hud.toggle()
    from app.spotlight_launcher import launch_or_toggle_web_spotlight
    launch_or_toggle_web_spotlight()
    await broadcast_to_spotlight({"action": "toggle"})
    return {"status": "ok"}

@app.get("/api/spotlight/quit")
@app.post("/api/spotlight/quit")
async def api_spotlight_quit():
    await broadcast_to_spotlight({"action": "quit"})
    await trigger_graceful_shutdown(delay=0.5, speak=True)
    return {"status": "ok"}



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
    is_spotlight = ws.query_params.get("client") == "spotlight"
    await hub.register_webui(ws)
    if is_spotlight:
        hub.register_spotlight(ws)
    try:
        while True:
            msg_str = await ws.receive_text()
            data = json.loads(msg_str)
            msg_type = data.get("type")

            if msg_type in ("VOICE_COMMAND", "TEXT_COMMAND", "CHAT_MESSAGE", "COMMAND"):
                command = (data.get("command") or data.get("message") or "").strip()
                voice = data.get("voice", DEFAULT_TTS_VOICE)
                speak = data.get("speak", True)
                cmd_thinking_level = data.get("thinking_level") or current_thinking_level
                if command:
                    # Echo command to all WebUI clients so it appears in the chat thread
                    await hub.broadcast_webui({
                        "type": "USER_CHAT_MESSAGE",
                        "command": command,
                    })
                    # Run command processing asynchronously
                    asyncio.create_task(process_user_command(
                        command,
                        voice=voice,
                        speak=speak,
                        thinking_level=cmd_thinking_level
                    ))

            elif msg_type == "SET_THINKING_LEVEL":
                lvl = (data.get("thinking_level") or "").strip().lower()
                if lvl in ("low", "medium", "high"):
                    current_thinking_level = lvl
                    gemini_service.set_thinking_level(lvl)
                    await hub.broadcast_webui({
                        "type": "THINKING_LEVEL_CHANGED",
                        "thinking_level": current_thinking_level
                    })

            elif msg_type == "CLEAR_CHAT":
                gemini_service.reset_conversation()
                await hub.broadcast_webui({"type": "CHAT_CLEARED"})

            elif msg_type == "STOP_SPEECH":
                tts_service.stop_speaking()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebUI WS] Error: {e}")
    finally:
        hub.unregister_webui(ws)
        if is_spotlight:
            hub.unregister_spotlight(ws)


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

# Concurrency Lock: ensures only one autonomous goal runs at any given time
pipeline_lock = asyncio.Lock()

async def process_user_command(
    user_command: str,
    voice: str = DEFAULT_TTS_VOICE,
    speak: bool = True,
    thinking_level: Optional[str] = None
) -> Dict[str, Any]:
    user_cmd_lower = user_command.lower().strip()

    # Direct fast-path: voice control for processing sound
    if any(k in user_cmd_lower for k in ("tắt tiếng processing", "ngắt tiếng processing", "tắt âm thanh xử lý", "tắt tiếng bíp", "tắt pulsing", "tắt tiếng nhịp tim")):
        sound_manager.set_pulse_enabled(False)
        sound_manager.play_done()
        msg = "Đã tắt âm thanh khi xử lý cho bạn."
        if speak:
            await tts_service.speak(msg)
        return {"success": True, "speech": msg, "action_result": {"success": True, "action": "sound_config"}}

    if any(k in user_cmd_lower for k in ("bật tiếng processing", "bật âm thanh xử lý", "bật pulsing", "bật tiếng nhịp tim")):
        sound_manager.set_pulse_enabled(True)
        sound_manager.play_done()
        msg = "Đã bật lại âm thanh khi xử lý cho bạn."
        if speak:
            await tts_service.speak(msg)
        return {"success": True, "speech": msg, "action_result": {"success": True, "action": "sound_config"}}

    # Direct fast-path: Voice intents to switch modes
    chat_mode_intents = (
        "chuyển sang chế độ chat", "chuyển qua chế độ chat", "bật chế độ chat",
        "vào chế độ chat", "mở chế độ chat", "chế độ chat", "sang chế độ chat",
        "chuyển sang chế độ trò chuyện", "chuyển qua chế độ trò chuyện",
        "bật chế độ trò chuyện", "vào chế độ trò chuyện", "chế độ trò chuyện",
        "sang chế độ trò chuyện"
    )
    if any(intent in user_cmd_lower for intent in chat_mode_intents):
        await set_mode("chat", announce=speak)
        return {"success": True, "speech": "Đã chuyển sang chế độ trò chuyện", "action_result": {"success": True, "action": "set_mode"}}

    control_mode_intents = (
        "chuyển sang chế độ điều khiển", "chuyển qua chế độ điều khiển",
        "bật chế độ điều khiển", "vào chế độ điều khiển", "chế độ điều khiển",
        "sang chế độ điều khiển", "chuyển sang chế độ máy tính", "chế độ điều khiển máy tính",
        "bật chế độ điều khiển máy tính", "sang chế độ máy tính"
    )
    if any(intent in user_cmd_lower for intent in control_mode_intents):
        await set_mode("control", announce=speak)
        return {"success": True, "speech": "Đã chuyển sang chế độ điều khiển", "action_result": {"success": True, "action": "set_mode"}}

    toggle_mode_intents = (
        "đổi chế độ", "chuyển chế độ", "đổi trạng thái", "chuyển trạng thái"
    )
    if any(intent in user_cmd_lower for intent in toggle_mode_intents):
        new_mode = await toggle_mode(announce=speak)
        return {
            "success": True,
            "speech": f"Đã chuyển sang chế độ {'trò chuyện AI' if new_mode == 'chat' else 'điều khiển máy tính'}",
            "action_result": {"success": True, "action": "toggle_mode", "mode": new_mode}
        }

    # Direct fast-path: Voice intent to check system status
    status_intents = (
        "kiểm tra trạng thái", "trạng thái hệ thống", "trạng thái máy",
        "tình trạng máy", "trạng thái trợ lý", "tình trạng luga",
        "kiểm tra luga", "luga có đang chạy không", "kiểm tra hoạt động",
        "kiểm tra tình trạng"
    )
    if any(intent in user_cmd_lower for intent in status_intents):
        mode_label = "Điều khiển máy tính" if current_mode == "control" else "Trò chuyện AI"
        gemini_ready = gemini_service.is_ready or (hub.extension_client is not None)
        gemini_text = "đã sẵn sàng" if gemini_ready else "đang chờ kết nối"
        screen_w, screen_h = os_controller.get_screen_size()
        speech = f"Luga Assist đang hoạt động bình thường ở chế độ {mode_label}. Kết nối Gemini {gemini_text}. Màn hình độ phân giải {screen_w} nhân {screen_h}."
        sound_manager.play_done()
        show_desktop_notification(
            title="Luga Assist - Trạng thái",
            message=f"Chế độ: {mode_label} | Gemini: {gemini_text}",
            subtitle="Hệ thống đang hoạt động"
        )
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {
                "success": True,
                "action": "system_status",
                "mode": current_mode,
                "gemini_ready": gemini_ready,
                "screen_size": (screen_w, screen_h),
            }
        }

    # Direct fast-path: Voice intent to explain/open spotlight floating chat
    spotlight_intents = (
        "bật chat nhanh", "mở chat nhanh", "bật spotlight", "mở spotlight",
        "bật popup chat", "mở popup chat", "cửa sổ chat nổi", "bật cửa sổ chat"
    )
    if any(intent in user_cmd_lower for intent in spotlight_intents):
        speech = "Bạn có thể nhấn phím F7 từ bất kỳ đâu trên bàn phím để bật hoặc tắt cửa sổ Chat nổi Luga."
        sound_manager.play_done()
        show_desktop_notification("Luga Assist - Chat Nổi", "Nhấn phím F7 để bật/tắt Chat nổi bất cứ lúc nào.")
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "spotlight_info"}
        }

    # Direct fast-path: Voice intent to shut down / stop system
    shutdown_intents = (
        "tắt trợ lý", "dừng trợ lý", "tắt luga", "dừng luga",
        "tắt app", "tắt ứng dụng", "dừng ứng dụng", "thoát chương trình",
        "thoát luga", "nghỉ ngơi đi", "đóng trợ lý", "tắt hệ thống",
        "dừng chương trình", "tắt chương trình"
    )
    if any(intent in user_cmd_lower for intent in shutdown_intents):
        speech = "Đang tắt Luga Assist. Tạm biệt bạn!"
        await trigger_graceful_shutdown(delay=1.0, speak=speak, goodbye_text=speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {
                "success": True,
                "action": "shutdown",
                "details": "Đang tiến hành tắt hệ thống hoàn toàn"
            }
        }

    # Direct fast-path: Voice intent to restart
    restart_intents = (
        "khởi động lại trợ lý", "khởi động lại luga", "restart luga",
        "khởi động lại hệ thống", "khởi động lại app"
    )
    if any(intent in user_cmd_lower for intent in restart_intents):
        speech = "Luga Assist đang khởi động lại. Vui lòng chờ giây lát."
        await trigger_graceful_restart(delay=1.0)
        return {
            "success": True,
            "speech": speech,
            "action_result": {
                "success": True,
                "action": "restart",
                "details": "Đang khởi động lại hệ thống"
            }
        }

    # Direct fast-path: Voice intents for Google Logout / Switch Account
    google_logout_intents = (
        "đăng xuất google", "đăng xuất tài khoản google", "thoát tài khoản google",
        "đăng xuất gemini", "thoát google", "hủy kết nối google"
    )
    if any(intent in user_cmd_lower for intent in google_logout_intents):
        from app.google_auth import google_auth_manager
        await google_auth_manager.logout()
        await hub.broadcast_status()
        await hub.broadcast_webui({
            "type": "GOOGLE_AUTH_LOGGED_OUT",
            "gemini_ready": False,
            "message": "Đã đăng xuất tài khoản Google."
        })
        speech = "Đã đăng xuất tài khoản Google cho bạn."
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "google_logout"}
        }

    google_switch_intents = (
        "đổi tài khoản google", "chuyển tài khoản google", "đổi tài khoản gemini",
        "chuyển tài khoản gemini", "đổi nick google", "đăng nhập tài khoản google khác"
    )
    if any(intent in user_cmd_lower for intent in google_switch_intents):
        from app.google_auth import google_auth_manager
        await google_auth_manager.switch_account(hub.broadcast_webui)
        speech = "Đang mở trình duyệt để bạn chọn hoặc đăng nhập tài khoản Google khác."
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "google_switch"}
        }

    # Direct fast-path: Voice intent to open Windows Settings & System Panels
    settings_intents = (
        "mở cài đặt", "mở settings", "vào cài đặt", "bật cài đặt",
        "mở setting", "cài đặt máy tính", "mở windows settings",
        "mở phần cài đặt", "cài đặt hệ thống"
    )
    if any(intent == user_cmd_lower or user_cmd_lower.startswith(intent) for intent in settings_intents):
        os_controller._launch_app("Settings")
        speech = "Đang mở Cài đặt Windows."
        sound_manager.play_done()
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "open_settings"}
        }

    bluetooth_intents = ("mở bluetooth", "cài đặt bluetooth", "bật bluetooth", "vào bluetooth")
    if any(intent == user_cmd_lower or user_cmd_lower.startswith(intent) for intent in bluetooth_intents):
        os_controller._launch_app("bluetooth")
        speech = "Đang mở cài đặt Bluetooth."
        sound_manager.play_done()
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "open_bluetooth"}
        }

    wifi_intents = ("mở wifi", "cài đặt wifi", "mở wi-fi", "cài đặt mạng", "vào wifi")
    if any(intent == user_cmd_lower or user_cmd_lower.startswith(intent) for intent in wifi_intents):
        os_controller._launch_app("wifi")
        speech = "Đang mở cài đặt mạng Wi-Fi."
        sound_manager.play_done()
        if speak:
            await tts_service.speak(speech)
        return {
            "success": True,
            "speech": speech,
            "action_result": {"success": True, "action": "open_wifi"}
        }

    if pipeline_lock.locked():
        msg = "Hệ thống đang bận xử lý câu lệnh trước, vui lòng chờ."
        print(f"[Pipeline] ⚠️ {msg}: '{user_command}'")
        return {"success": False, "speech": msg, "action_result": {"success": False, "action": "busy"}}

    async with pipeline_lock:
        return await _execute_pipeline(user_command, voice, speak=speak, thinking_level=thinking_level)

async def _execute_pipeline(
    user_command: str,
    voice: str = DEFAULT_TTS_VOICE,
    speak: bool = True,
    thinking_level: Optional[str] = None
) -> Dict[str, Any]:
    print(f"\n[Pipeline] 🎯 Nhận mục tiêu mới: '{user_command}'")
    # Determine effective thinking level for this pipeline run
    actual_thinking_level = (thinking_level or current_thinking_level or "medium").strip().lower()
    if actual_thinking_level not in ("low", "medium", "high"):
        actual_thinking_level = "medium"
    print(f"[Pipeline] 🧠 Thinking Level: {actual_thinking_level.upper()}")

    # Reset abort event for fresh goal execution
    pipeline_abort_event.clear()
    # Start pulsing audio feedback for the user (only if enabled)
    sound_manager.start_pulsing()

    # Step 1: Check Connection (Gemini Background Service)
    is_gemini_ready = gemini_service.is_ready or (hub.extension_client is not None)
    if not is_gemini_ready:
        print("[Pipeline] 🔄 Đang tự động kết nối lại session Google Gemini...")
        recovered = await gemini_service.auto_init_from_disk()
        if recovered or gemini_service.is_ready:
            is_gemini_ready = True
            await hub.broadcast_status()

    if not is_gemini_ready:
        sound_manager.play_error()
        error_msg = (
            "Chưa kết nối tài khoản Google Gemini! "
            "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối."
        )
        await hub.broadcast_webui({
            "type": "ERROR",
            "message": error_msg,
            "user_command": user_command,
        })
        if speak:
            await tts_service.speak(error_msg)
        return {
            "success": False,
            "speech": error_msg,
            "action_result": {"success": False, "error": error_msg},
            "done": True,
        }

    step = 0
    last_actions_summary = ""
    is_goal_verified_completed = False

    while step < MAX_AUTONOMOUS_STEPS:
        if pipeline_abort_event.is_set():
            print(f"[Pipeline] ⏹️ Đã ngắt tác vụ '{user_command}' trước bước {step + 1}!")
            break

        step += 1
        is_first_step = (step == 1)
        print(f"\n[Pipeline] 🔄 --- BƯỚC {step}/{MAX_AUTONOMOUS_STEPS} cho mục tiêu: '{user_command}' ---")

        await hub.broadcast_webui({
            "type": "ACTION_PROGRESS",
            "message": f"Đang chụp màn hình và phân tích (Bước {step})...",
            "step": step,
        })

        # Step 2: Screen Capture with Dual-Tier Grid Overlay & UI Elements
        # Ensure Spotlight window is minimized/hidden so it NEVER obstructs the screenshot or targets!
        if is_first_step:
            from app.system_ui import dismiss_windows_error_dialog
            dismiss_windows_error_dialog()
            from app.spotlight_launcher import minimize_spotlight_window_windows
            if sys.platform.startswith("win"):
                minimized = minimize_spotlight_window_windows()
                if minimized:
                    print("[Pipeline] 🙈 Đã tự động thu nhỏ cửa sổ Spotlight để chụp ảnh màn hình không bị che khuất!")
                    await asyncio.sleep(0.12)  # 120ms for DWM to repaint uncovered area

        screenshot_b64, screen_size = screen_capturer.capture(with_grid=True)
        ui_context = accessibility_manager.get_ui_grounding_context()

        if is_first_step:
            prompt = build_gemini_prompt(
                user_command,
                ui_context=ui_context,
                thinking_level=actual_thinking_level,
                is_initial=(not gemini_service.has_grounding)
            )
        else:
            # Verification Prompt: inspect screen after previous action
            prompt = build_verification_prompt(
                user_command=user_command,
                step=step,
                previous_actions_desc=last_actions_summary,
                ui_context=ui_context,
                thinking_level=actual_thinking_level
            )

        raw_response = ""
        used_background = False

        if gemini_service.is_ready:
            print(f"[Pipeline] [Bước {step}] Gửi tới Background Gemini Service (mức={actual_thinking_level})...")
            try:
                raw_response = await gemini_service.send_prompt(
                    prompt=prompt,
                    image_path=screen_capturer.screenshot_path,
                    thinking_level=actual_thinking_level
                )
                used_background = True
            except Exception as e:
                err_msg = str(e)
                print(f"[Pipeline] ⚠️ Lỗi Background Gemini Service: {err_msg}")
                err_lower = err_msg.lower()
                is_auth_error = isinstance(e, AuthError) or "401" in err_lower or "unauthenticated" in err_lower
                if is_auth_error:
                    print("[Pipeline] ⚠️ Session Google hết hạn trong khi gọi AI. Đang tự động khôi phục ngầm...")
                    recovered = await gemini_service.auto_init_from_disk()
                    if recovered and gemini_service.is_ready:
                        try:
                            raw_response = await gemini_service.send_prompt(
                                prompt=prompt,
                                image_path=screen_capturer.screenshot_path,
                                thinking_level=actual_thinking_level
                            )
                            used_background = True
                            err_text = None
                        except Exception as retry_e:
                            gemini_service.is_ready = False
                            err_text = (
                                "Phiên đăng nhập Google Gemini đã hết hạn. "
                                "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối lại."
                            )
                    else:
                        gemini_service.is_ready = False
                        err_text = (
                            "Phiên đăng nhập Google Gemini đã hết hạn. "
                            "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối lại."
                        )
                else:
                    err_text = f"Lỗi phản hồi từ Gemini: {err_msg}. Vui lòng thử lại câu lệnh."

                if not used_background:
                    sound_manager.play_error()
                    sound_manager.stop_pulsing()
                    await hub.broadcast_webui({"type": "ERROR", "message": err_text, "user_command": user_command})
                    if speak:
                        await tts_service.speak(err_text)
                    return {
                        "success": False,
                        "speech": err_text,
                        "action_result": {"success": False, "error": err_text},
                        "done": True,
                    }

        if not used_background:
            sound_manager.play_error()
            sound_manager.stop_pulsing()
            err_text = (
                "Chưa kết nối tài khoản Google. "
                "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối."
            )
            await hub.broadcast_webui({"type": "ERROR", "message": err_text, "user_command": user_command})
            if speak:
                await tts_service.speak(err_text)
            return {
                "success": False,
                "speech": err_text,
                "action_result": {"success": False, "error": err_text},
                "done": True,
            }

        raw_response = strip_citations(raw_response)
        print(f"[Pipeline] [Bước {step}] Phản hồi từ Gemini:\n{raw_response}")
        # Stop pulsing audio cue immediately as soon as AI response has been received
        sound_manager.stop_pulsing()

        if pipeline_abort_event.is_set():
            print(f"[Pipeline] ⏹️ Đã ngắt tác vụ '{user_command}' sau phản hồi AI.")
            break

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
            # Only true instant system hardware controls (sleep, mute, unmute, volume, lock)
            # or standalone file information queries do NOT need a secondary screenshot verification loop.
            pure_hardware_controls = all(
                isinstance(a, dict) and a.get("action", "").lower() in (
                    "system_control", "system", "sleep", "mute", "unmute", "volume_up", "volume_down", "lock"
                )
                for a in active_actions
            )
            file_info_actions = all(
                isinstance(a, dict) and a.get("action", "").lower() in (
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

            user_cmd_lower = user_command.lower()
            is_direct_click_request = (
                len(active_actions) == 1
                and active_actions[0].get("action", "").lower() in ("click", "select_element", "press", "launch_app")
                and any(k in user_cmd_lower for k in ("click", "nhấn", "bấm", "chọn", "press", "mở"))
            )

            if pure_hardware_controls:
                is_goal_verified_completed = True
                print(f"[Pipeline] ⚡ Điều khiển phần cứng hoàn tất tại bước {step}: {speech_to_say}")
            elif file_info_actions and (claimed_done or len(active_actions) == 1):
                is_goal_verified_completed = True
                print(f"[Pipeline] ⚡ Thao tác file hoàn tất tại bước {step}: {speech_to_say}")
            elif is_direct_click_request and (claimed_done or step >= 1):
                is_goal_verified_completed = True
                print(f"[Pipeline] ⚡ Thao tác click trực tiếp hoàn tất tại bước {step}: {speech_to_say}")
            elif claimed_done and not is_complex_form and not any(a.get("action") in ("terminal_command", "terminal", "run_terminal") for a in active_actions):
                is_goal_verified_completed = True
                print(f"[Pipeline] ⚡ Thao tác hoàn tất theo xác nhận AI tại bước {step}: {speech_to_say}")
            else:
                is_goal_verified_completed = False

        # Step 5: Annotate Screenshot for Visual Feedback
        annotated_b64 = screen_capturer.annotate_actions(actions_list)

        # Step 6: Speak Spoken Response to User Concurrently (if speak=True)
        if speak:
            speak_task = asyncio.create_task(tts_service.speak(speech_for_tts))
        else:
            speak_task = asyncio.sleep(0)

        # Step 7: Execute Action Sequence on OS (if active actions exist)
        action_result = {"success": True, "action": "none", "details": "Verified state"}
        if active_actions:
            if pipeline_abort_event.is_set():
                print(f"[Pipeline] ⏹️ Đã ngắt tác vụ trước khi thao tác chuột/phím!")
                break
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

            # If action execution failed, force unverified state so next step can recover
            if not action_result.get("success", True):
                is_goal_verified_completed = False
                last_actions_summary += f" | [LƯU Ý THẤT BÀI]: Thao tác bước {step} không thành công ({action_result.get('details', '')[:100]}). Hãy thử lại hoặc dùng chuột vật lý!"
                print(f"[Pipeline] ⚠️ Thao tác tại bước {step} thất bại. Chuyển sang bước tiếp theo để AI kiểm tra và sửa sai.")

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
            if speak:
                await tts_service.speak(dynamic_speech)

        # Check termination condition
        if is_goal_verified_completed:
            print(f"[Pipeline] ✅ Hoàn tất và ĐÃ XÁC MINH mục tiêu sau {step} bước!")
            break

        # If more steps needed, wait briefly for new window/dialog/state to settle
        delay = 1.0 if any(a.get("action") == "launch_app" for a in actions_list) else 0.7
        print(f"[Pipeline] ⏳ Đang tạm dừng {delay}s chờ giao diện cập nhật để chụp ảnh thẩm định kết quả...")
        for _ in range(int(delay * 10)):
            if pipeline_abort_event.is_set():
                break
            await asyncio.sleep(0.1)

    # Completion handling
    if pipeline_abort_event.is_set():
        sound_manager.stop_pulsing()
        sound_manager.play_error()
        tts_service.stop_speaking()
        cancel_msg = "Đã ngắt thao tác theo lệnh người dùng."
        print(f"\n[Pipeline] ⏹️ TÁC VỤ ĐÃ BỊ NGẮT BỞI NGƯỜI DÙNG!")
        return {
            "success": False,
            "speech": cancel_msg,
            "action_result": {"success": False, "action": "cancelled"},
            "annotated_image": annotated_b64 if "annotated_b64" in locals() else "",
            "step": step,
            "cancelled": True,
            "done": True,
        }

    if is_goal_verified_completed:
        sound_manager.play_done()
        print(f"\n[Pipeline] 🎉 HOÀN THÀNH VÀ ĐÃ XÁC MINH TOÀN BỘ MỤC TIÊU!")
    else:
        sound_manager.play_error()
        print(f"\n[Pipeline] ⚠️ Đã dừng sau {MAX_AUTONOMOUS_STEPS} bước mà chưa xác minh được kết quả hoàn tất.")
        if speak:
            await tts_service.speak("Chưa thể xác nhận hoàn tất thao tác. Bạn vui lòng kiểm tra lại màn hình.")

    return {
        "success": is_goal_verified_completed,
        "speech": speech_to_say,
        "action_result": action_result,
        "annotated_image": annotated_b64,
        "step": step,
        "done": is_goal_verified_completed,
    }




def handle_single_instance_or_free_port(host: str = HOST, port: int = PORT) -> bool:
    """
    Ensure robust single-instance behavior:
    1. If an active instance is running, trigger its Spotlight HUD to pop up and exit cleanly.
    2. If port is occupied by a stale/zombie process, terminate it to guarantee Uvicorn binds successfully.
    """
    import urllib.request
    import urllib.error
    import socket
    import signal

    # 1. Check if existing instance is alive and healthy
    try:
        url = f"http://{host}:{port}/api/status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=0.6) as res:
            if res.status == 200:
                # Active instance found! Trigger Spotlight HUD to appear on screen
                try:
                    show_req = urllib.request.Request(f"http://{host}:{port}/api/spotlight/show", data=b"{}", headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(show_req, timeout=0.8)
                except Exception:
                    pass
                print("\n[SingleInstance] ℹ️ Luga Assist đã đang chạy! Đã kích hoạt Cửa sổ Spotlight HUD hiển thị trên màn hình.")
                return False  # Signals to exit cleanly
    except Exception:
        pass

    # 2. Check if port is bound by a stale or lingering process
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_in_use = False
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
    except OSError:
        is_in_use = True

    if is_in_use:
        print(f"[Port] Cổng {port} đang bị giữ bởi tiến trình cũ. Đang giải phóng cổng...")
        try:
            res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    if pid != os.getpid() and pid > 0:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            time.sleep(0.4)
        except Exception as e:
            print(f"[Port] Cảnh báo giải phóng cổng: {e}")

    return True


def start():
    """Entry point for running server and native Spotlight HUD."""
    import threading
    import signal

    # 1. Single-instance check or free lingering port
    should_start = handle_single_instance_or_free_port(HOST, PORT)
    if not should_start:
        sys.exit(0)

    # Terminate any previously recorded PID instance
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid() and old_pid > 0:
                try:
                    os.kill(old_pid, 0)
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(0.3)
                except (OSError, ProcessLookupError):
                    pass
        except Exception:
            pass

    # Save PID so daemon commands / scripts know about this process
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    print("=" * 60)
    print("      LUGA ASSIST - TRỢ LÝ ĐIỀU KHIỂN TOÀN DIỆN")
    print(f"      Cổng API ngầm:   http://{HOST}:{PORT}")
    print("      Phím tắt F7:     Bật / Tắt Cửa sổ Chat Nổi (Spotlight)")
    print("      Phím tắt F8:     Nói trực tiếp qua Micro (Push-to-Talk)")
    print("      Phím tắt F9:     Chuyển đổi Chế độ (Điều khiển OS <-> Chat AI)")
    print("      Phím tắt F10:    Ngắt khẩn cấp / Hủy lệnh ngay lập tức")
    print("=" * 60)

    try:
        uvicorn.run(app, host=HOST, port=PORT, reload=False, log_level="info")
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        sys.exit(0)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    if "--spotlight-ui" in sys.argv:
        from app.spotlight_ui import start_spotlight_process
        start_spotlight_process()
        sys.exit(0)

    start()
