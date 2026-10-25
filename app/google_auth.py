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
import socket
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
DEFAULT_CDP_PORT = 19222


def get_available_cdp_port(preferred_port: int = DEFAULT_CDP_PORT) -> int:
    """Find an available port for CDP remote debugging, checking up to 20 ports."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred_port)) != 0:
            return preferred_port
    # Port preferred is taken, check if it's already an active CDP endpoint
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{preferred_port}/json/version")
        with urllib.request.urlopen(req, timeout=0.6):
            return preferred_port
    except Exception:
        pass
    # Find next free port
    for p in range(preferred_port + 1, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return preferred_port


def get_windows_default_browser() -> Optional[str]:
    r"""
    Read Windows Registry to find the user's actual default browser.
    Checks HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice
    and resolves the shell open command to find the executable path.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg
        import re

        prog_id = None
        for proto in ("https", "http"):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    rf"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{proto}\UserChoice"
                ) as key:
                    prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                    if prog_id:
                        break
            except Exception:
                pass

        if not prog_id:
            return None

        # Resolve ProgId to executable command
        cmd_str = None
        for root in (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"{prog_id}\shell\open\command") as key:
                    cmd_str, _ = winreg.QueryValueEx(key, "")
                    if cmd_str:
                        break
            except Exception:
                pass

        if not cmd_str:
            return None

        # Extract executable path from command line string
        # e.g. "C:\Program Files\Google\Chrome\Application\chrome.exe" -- "%1"
        match = re.match(r'^\s*"([^"]+)"', cmd_str) or re.match(r'^\s*([^\s]+)', cmd_str)
        if match:
            exe_path = match.group(1)
            if os.path.exists(exe_path):
                return exe_path
    except Exception as e:
        logger.debug(f"Could not determine Windows default browser: {e}")
    return None


def is_chromium_browser(path: str) -> bool:
    """Check if the given executable is a Chromium-based browser supporting CDP flags."""
    lower = path.lower()
    chromium_names = (
        "chrome", "msedge", "edge", "brave", "coccoc", "coc_coc",
        "browser.exe", "opera", "vivaldi", "chromium"
    )
    return any(name in lower for name in chromium_names)


def find_chromium_browser() -> Optional[str]:
    """
    Find available Chromium-based browser (Google Chrome, Brave, Cốc Cốc, Microsoft Edge)
    specifically optimized for Windows 10 & 11.
    Prioritizes the user's actual default browser whenever it is Chromium-based!
    """
    if sys.platform.startswith("win"):
        # 1. First Priority: The user's actual default browser if it is Chromium-based!
        default_browser = get_windows_default_browser()
        if default_browser and is_chromium_browser(default_browser):
            logger.info(f"🌐 Sử dụng trình duyệt mặc định của hệ thống: {default_browser}")
            return default_browser

        # 2. Check user's preferred browsers in order: Chrome -> Brave -> Cốc Cốc -> Edge
        candidates = [
            # Chrome (%LOCALAPPDATA% first for standard per-user installs, then %PROGRAMFILES%)
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            # Brave
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            # Cốc Cốc
            Path(os.environ.get("LOCALAPPDATA", "")) / "CocCoc" / "Browser" / "Application" / "browser.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "CocCoc" / "Browser" / "Application" / "browser.exe",
            # Microsoft Edge (Guaranteed fallback on Windows 10/11)
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)

        # 3. Check Windows Registry App Paths in order: Chrome, Brave, CocCoc, then Edge
        try:
            import winreg
            for exe_name in ("chrome.exe", "brave.exe", "browser.exe", "msedge.exe"):
                for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    try:
                        k = winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}")
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            return val
                    except Exception:
                        pass
        except Exception:
            pass

        for name in ("chrome.exe", "brave.exe", "chrome", "msedge.exe", "msedge"):
            found = shutil.which(name)
            if found:
                return found

    # Fallback for generic environments / development
    for name in ("chrome", "google-chrome", "msedge", "chromium"):
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
        self._active_cdp_port: int = DEFAULT_CDP_PORT

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
        # If a monitor task is currently running, check if it's genuinely alive
        if self.is_logging_in and self._monitor_task and not self._monitor_task.done():
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self._active_cdp_port}/json/version")
                with urllib.request.urlopen(req, timeout=0.8):
                    return {
                        "status": "already_running",
                        "message": "Cửa sổ đăng nhập Google đang mở. Vui lòng hoàn tất đăng nhập trên trình duyệt."
                    }
            except Exception:
                # CDP is no longer responding; clean up stale state
                self._monitor_task.cancel()
                self.is_logging_in = False

        browser_path = find_chromium_browser()
        GOOGLE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        target_url = login_url
        if not target_url:
            if force_account_picker:
                target_url = "https://accounts.google.com/AccountChooser?continue=https://gemini.google.com"
            else:
                target_url = "https://gemini.google.com"

        if not browser_path:
            import webbrowser
            logger.info(f"Mở Google Gemini qua trình duyệt mặc định: {target_url}")
            webbrowser.open(target_url)
            return {
                "status": "ok",
                "message": "Đã mở trang đăng nhập Google Gemini trên trình duyệt mặc định của bạn."
            }

        self._active_cdp_port = get_available_cdp_port(DEFAULT_CDP_PORT)
        profile_path = str(GOOGLE_PROFILE_DIR.resolve())
        cmd = [
            browser_path,
            f"--remote-debugging-port={self._active_cdp_port}",
            f"--user-data-dir={profile_path}",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=880,740",
            target_url
        ]

        logger.info(f"🚀 Mở cửa sổ đăng nhập Google ({target_url}, CDP port {self._active_cdp_port}): {browser_path}")

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

    async def _close_login_browser(self, ws=None):
        """Close login browser window cleanly across all platforms."""
        # 1. Close via CDP commands
        if ws is not None:
            try:
                # First close all open page targets
                await ws.send(json.dumps({"id": 8991, "method": "Target.getTargets"}))
                resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(resp)
                targets = data.get("result", {}).get("targetInfos", [])
                for t in targets:
                    if t.get("type") == "page":
                        await ws.send(json.dumps({
                            "id": 8992,
                            "method": "Target.closeTarget",
                            "params": {"targetId": t["targetId"]}
                        }))
                        try:
                            await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Error closing targets via CDP: {e}")

            try:
                # Then tell the browser instance to exit cleanly
                await ws.send(json.dumps({"id": 8999, "method": "Browser.close"}))
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
                except Exception:
                    pass
            except Exception as e:
                logger.debug(f"Error closing browser via CDP: {e}")

        # 2. Terminate the subprocess if still alive
        if self._login_process and self._login_process.poll() is None:
            try:
                self._login_process.terminate()
                try:
                    self._login_process.wait(timeout=2.0)
                except Exception:
                    self._login_process.kill()
            except Exception:
                pass

        # 3. Windows-specific fallback: close any lingering Google Login / Gemini windows
        if sys.platform.startswith("win"):
            try:
                import ctypes
                user32 = ctypes.windll.user32
                WM_CLOSE = 0x0010

                def enum_cb(hwnd, extra):
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value.lower()
                        # Avoid touching Spotlight window
                        if "spotlight" in title:
                            return True
                        if ("gemini" in title or "google" in title) and ("edge" in title or "chrome" in title or "đăng nhập" in title or "sign in" in title):
                            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception as e:
                logger.debug(f"Win32 window close fallback notice: {e}")

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
        logger.info(f"⏳ Đang lắng nghe session Google Gemini qua CDP (port {self._active_cdp_port})...")
        ws_url = None

        # 1. Wait for CDP endpoint to become ready (up to 25 seconds)
        for _ in range(50):
            if not self.is_logging_in:
                logger.info("Tiến trình đăng nhập đã bị hủy.")
                return

            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self._active_cdp_port}/json/version")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    data = json.loads(resp.read())
                    ws_url = data.get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                await asyncio.sleep(0.5)

        if not ws_url:
            logger.warning(f"Không thể kết nối tới Chrome DevTools Protocol (port {self._active_cdp_port}) sau 25 giây.")
            self.is_logging_in = False
            return

        logger.info(f"✅ Đã kết nối CDP WebSocket: {ws_url}. Đang đợi người dùng đăng nhập...")

        # 2. Connect to CDP WebSocket and poll for Google Gemini cookies (up to 5 minutes)
        max_duration = 300  # 5 minutes for user to enter credentials and complete 2FA
        start_time = time.time()
        msg_id = 100
        psid_wait_count = 0

        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                while time.time() - start_time < max_duration:
                    if not self.is_logging_in:
                        logger.info("Tiến trình đăng nhập đã bị hủy.")
                        break

                    msg_id += 1
                    req_payload = {"id": msg_id, "method": "Storage.getCookies"}
                    await ws.send(json.dumps(req_payload))

                    # Drain messages until response with matching msg_id is received
                    resp_data = None
                    for _ in range(10):
                        raw_resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        msg_obj = json.loads(raw_resp)
                        if msg_obj.get("id") == msg_id:
                            resp_data = msg_obj
                            break

                    if resp_data and "result" in resp_data:
                        cookies = resp_data["result"].get("cookies", [])
                        psid = None
                        psidts = None
                        psidcc = None

                        for c in cookies:
                            c_name = c.get("name")
                            c_domain = c.get("domain", "")
                            if "google.com" in c_domain:
                                if c_name == "__Secure-1PSID":
                                    psid = c.get("value")
                                elif c_name == "__Secure-1PSIDTS":
                                    psidts = c.get("value")

                        # If __Secure-1PSID is detected:
                        if psid:
                            # Google Gemini requires both __Secure-1PSID and __Secure-1PSIDTS for modern auth.
                            # Keep waiting while browser completes Google Gemini load
                            if not psidts:
                                psid_wait_count += 1
                                if psid_wait_count % 3 == 0:
                                    logger.info(f"Đã bắt được __Secure-1PSID, đang chờ __Secure-1PSIDTS ({psid_wait_count}s)...")
                                    try:
                                        msg_id += 1
                                        await ws.send(json.dumps({
                                            "id": msg_id,
                                            "method": "Target.createTarget",
                                            "params": {"url": "https://gemini.google.com"}
                                        }))
                                    except Exception:
                                        pass
                                await asyncio.sleep(1.5)
                                continue

                            # Both PSID and PSIDTS are present! Verify session BEFORE closing browser
                            logger.info("🎉 Đã bắt được __Secure-1PSID và __Secure-1PSIDTS! Đang kích hoạt kết nối Gemini...")
                            from app.gemini_service import gemini_service
                            from app.sound_effects import sound_manager

                            ok = await gemini_service.init_session(psid, psidts)
                            if ok:
                                logger.info("🎉 KẾT NỐI GOOGLE GEMINI HOÀN TẤT VÀ SẴN SÀNG 100%!")

                                # 1. Close login browser cleanly now that session is verified
                                await self._close_login_browser(ws)
                                self.is_logging_in = False
                                sound_manager.play_done()

                                # 2. Bring Spotlight window to front forcefully
                                from app.spotlight_launcher import bring_spotlight_to_front_windows, broadcast_spotlight_message
                                bring_spotlight_to_front_windows()
                                broadcast_spotlight_message({"type": "SPOTLIGHT_FOCUS"})

                                # 3. Notify all web clients and update server status
                                try:
                                    from app.main import hub
                                    await hub.broadcast_status()
                                    await hub.broadcast_webui({
                                        "type": "GOOGLE_AUTH_SUCCESS",
                                        "gemini_ready": True,
                                        "message": "Đã đăng nhập Google thành công! Gemini đã sẵn sàng."
                                    })
                                except Exception as e:
                                    logger.warning(f"Error broadcasting auth success: {e}")

                                if self._on_success_callback:
                                    try:
                                        if asyncio.iscoroutinefunction(self._on_success_callback):
                                            await self._on_success_callback()
                                        else:
                                            self._on_success_callback()
                                    except Exception as cb_err:
                                        logger.warning(f"Error in on_success_callback: {cb_err}")

                                return
                            else:
                                logger.warning("⚠️ Chưa thể kết nối GeminiClient với cookie hiện tại, tiếp tục theo dõi trình duyệt...")

                    await asyncio.sleep(1.5)

        except websockets.ConnectionClosed:
            logger.info("Cửa sổ trình duyệt đăng nhập đã được đóng bởi người dùng.")
        except Exception as e:
            logger.warning(f"Lỗi trong quá trình lắng nghe CDP: {e}")
        finally:
            self.is_logging_in = False
            # Ensure browser process is cleaned up if finished without cookies
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
