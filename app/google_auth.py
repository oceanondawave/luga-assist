"""
Google Web Authentication Manager for Luga Assist.
Allows users to log in to Google Gemini just like on any normal website,
with ZERO Chrome Extensions, ZERO manual cookie typing, and ZERO API keys.

Uses Chrome DevTools Protocol (CDP) to automatically detect and extract
session cookies (__Secure-1PSID and __Secure-1PSIDTS) as soon as the user logs in.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import websockets

from app.config import TEMP_DIR
from app.logger import get_logger

logger = get_logger("GoogleAuth")

GOOGLE_PROFILE_DIR = TEMP_DIR / "luga_google_profile"
CDP_PORT = 19222


def find_chromium_browser() -> Optional[str]:
    """
    Find any available Chromium-based browser (Google Chrome, Microsoft Edge, Brave)
    across Windows, macOS, and Linux.
    """
    if sys.platform.startswith("win"):
        candidates = [
            # Chrome
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            # Microsoft Edge (Guaranteed on 100% of Windows 10/11 machines)
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            # Brave
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        for name in ("chrome.exe", "msedge.exe", "brave.exe", "chrome", "msedge"):
            found = shutil.which(name)
            if found:
                return found
    elif sys.platform == "darwin":
        mac_candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in mac_candidates:
            if Path(p).exists():
                return p
        for name in ("google-chrome", "chromium", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                return found
    else:
        # Linux
        for name in ("google-chrome-stable", "google-chrome", "microsoft-edge-stable", "microsoft-edge", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                return found

    return None


class GoogleWebAuthManager:
    def __init__(self):
        self.is_logging_in = False
        self._login_process: Optional[subprocess.Popen] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._on_success_callback: Optional[Callable] = None

    def set_on_success_callback(self, cb: Callable):
        self._on_success_callback = cb

    async def start_web_login(
        self,
        hub_broadcast_func: Optional[Callable] = None,
        login_url: Optional[str] = None,
        force_account_picker: bool = False
    ) -> Dict[str, Any]:
        """
        Open a clean browser window to Google Gemini with remote debugging enabled.
        The user logs in with their Google account just like browsing any website.
        """
        if self.is_logging_in and self._login_process and self._login_process.poll() is None:
            return {
                "status": "already_running",
                "message": "Cửa sổ đăng nhập Google đang mở. Vui lòng hoàn tất đăng nhập trên trình duyệt."
            }

        browser_path = find_chromium_browser()
        if not browser_path:
            err = "Không tìm thấy trình duyệt Google Chrome hoặc Microsoft Edge trên máy tính để đăng nhập."
            logger.error(err)
            return {"status": "error", "message": err}

        GOOGLE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        target_url = login_url
        if not target_url:
            if force_account_picker:
                target_url = "https://accounts.google.com/AccountChooser?continue=https://gemini.google.com"
            else:
                target_url = "https://gemini.google.com"

        cmd = [
            browser_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={GOOGLE_PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=860,720",
            target_url
        ]

        logger.info(f"🚀 Mở cửa sổ đăng nhập Google ({target_url}, CDP port {CDP_PORT}): {browser_path}")

        try:
            self._login_process = subprocess.Popen(cmd)
            self.is_logging_in = True
        except Exception as e:
            logger.error(f"Lỗi khi khởi chạy trình duyệt: {e}")
            self.is_logging_in = False
            return {"status": "error", "message": f"Không thể mở trình duyệt: {e}"}

        # Start background polling task for cookies
        self._monitor_task = asyncio.create_task(
            self._monitor_cdp_cookies(hub_broadcast_func)
        )

        return {
            "status": "ok",
            "message": "Đã mở cửa sổ đăng nhập Google. Hãy đăng nhập tài khoản của bạn trên trình duyệt."
        }

    async def logout(self, clear_browser_profile: bool = False) -> Dict[str, Any]:
        """Log out from current Google session, clear saved cookies and in-memory client."""
        self.cancel_login()
        from app.gemini_service import gemini_service, SESSION_FILE
        from app.sound_effects import sound_manager

        # 1. Reset in-memory Gemini service
        gemini_service.is_ready = False
        gemini_service.client = None
        gemini_service.chat_session = None
        gemini_service.conversation_session = None
        gemini_service._current_psid = ""
        gemini_service._current_psidts = ""

        # 2. Delete saved session file
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Error removing session file: {e}")

        # 3. If full reset requested, clear profile directory
        if clear_browser_profile:
            try:
                if GOOGLE_PROFILE_DIR.exists():
                    shutil.rmtree(GOOGLE_PROFILE_DIR, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing google profile dir: {e}")

        sound_manager.play_done()
        logger.info("🚪 Đã đăng xuất tài khoản Google Gemini thành công.")
        return {"status": "ok", "message": "Đã đăng xuất tài khoản Google thành công."}

    async def switch_account(self, hub_broadcast_func: Optional[Callable] = None) -> Dict[str, Any]:
        """Log out current account and immediately launch browser to choose/add another account."""
        await self.logout(clear_browser_profile=False)
        return await self.start_web_login(
            hub_broadcast_func=hub_broadcast_func,
            login_url="https://accounts.google.com/AccountChooser?continue=https://gemini.google.com"
        )

    async def _monitor_cdp_cookies(self, hub_broadcast_func: Optional[Callable] = None):
        """Poll the CDP WebSocket to detect when the user logs in and set the session."""
        logger.info("⏳ Đang lắng nghe session Google Gemini qua CDP...")
        ws_url = None

        # 1. Wait for CDP endpoint to become ready (up to 15 seconds)
        for _ in range(30):
            if not self.is_logging_in or (self._login_process and self._login_process.poll() is not None):
                logger.info("Cửa sổ đăng nhập đã bị người dùng đóng trước khi kết nối CDP.")
                self.is_logging_in = False
                return

            try:
                req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/version")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    data = json.loads(resp.read())
                    ws_url = data.get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not ws_url:
            logger.warning("Không thể kết nối tới Chrome DevTools Protocol sau 15 giây.")
            self.is_logging_in = False
            return

        logger.info(f"✅ Đã kết nối CDP WebSocket: {ws_url}. Đang đợi người dùng đăng nhập...")

        # 2. Connect to CDP WebSocket and poll for __Secure-1PSID (up to 3 minutes)
        max_duration = 180  # 3 minutes
        start_time = time.time()
        msg_id = 100

        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                while time.time() - start_time < max_duration:
                    if not self.is_logging_in or (self._login_process and self._login_process.poll() is not None):
                        logger.info("Người dùng đã đóng cửa sổ trình duyệt đăng nhập.")
                        break

                    msg_id += 1
                    req_payload = {"id": msg_id, "method": "Storage.getCookies"}
                    await ws.send(json.dumps(req_payload))

                    raw_resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    resp_data = json.loads(raw_resp)

                    if resp_data.get("id") == msg_id:
                        cookies = resp_data.get("result", {}).get("cookies", [])
                        psid = None
                        psidts = None

                        for c in cookies:
                            c_name = c.get("name")
                            c_domain = c.get("domain", "")
                            if c_name == "__Secure-1PSID" and "google.com" in c_domain:
                                psid = c.get("value")
                            elif c_name == "__Secure-1PSIDTS" and "google.com" in c_domain:
                                psidts = c.get("value")

                        if psid:
                            logger.info("🎉 ĐÃ BẮT ĐƯỢC COOKIES GOOGLE GEMINI TỪ TRÌNH DUYỆT!")
                            # Initialize background Gemini session
                            from app.gemini_service import gemini_service
                            from app.sound_effects import sound_manager

                            ok = await gemini_service.init_session(psid, psidts)

                            # Close the login browser cleanly
                            try:
                                await ws.send(json.dumps({"id": msg_id + 1, "method": "Browser.close"}))
                            except Exception:
                                pass

                            if self._login_process and self._login_process.poll() is None:
                                try:
                                    self._login_process.terminate()
                                except Exception:
                                    pass

                            self.is_logging_in = False
                            sound_manager.play_done()

                            # Notify web clients
                            if hub_broadcast_func:
                                await hub_broadcast_func({
                                    "type": "GOOGLE_AUTH_SUCCESS",
                                    "gemini_ready": ok,
                                    "message": "Đã đăng nhập Google thành công! Gemini đã sẵn sàng."
                                })

                            if self._on_success_callback:
                                try:
                                    if asyncio.iscoroutinefunction(self._on_success_callback):
                                        await self._on_success_callback()
                                    else:
                                        self._on_success_callback()
                                except Exception as cb_err:
                                    logger.warning(f"Error in on_success_callback: {cb_err}")

                            return

                    await asyncio.sleep(1.5)

        except Exception as e:
            logger.warning(f"Lỗi trong quá trình lắng nghe CDP: {e}")
        finally:
            self.is_logging_in = False
            if self._login_process and self._login_process.poll() is None:
                try:
                    self._login_process.terminate()
                except Exception:
                    pass

    def cancel_login(self):
        """Cancel login and close process."""
        self.is_logging_in = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        if self._login_process and self._login_process.poll() is None:
            try:
                self._login_process.terminate()
            except Exception:
                pass


google_auth_manager = GoogleWebAuthManager()
