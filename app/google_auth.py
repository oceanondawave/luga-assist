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

from app.config import USER_DATA_DIR, TEMP_DIR
from app.logger import get_logger

logger = get_logger("GoogleAuth")

# Persistent browser profile in USER_DATA_DIR (never in %TEMP%)
GOOGLE_PROFILE_DIR = USER_DATA_DIR / "google_profile"


def get_google_profile_dir(browser_path: Optional[str] = None) -> Path:
    """
    Return isolated profile directory based on browser.
    Ensures Microsoft Edge uses its own dedicated profile (google_profile_edge),
    preventing DPAPI key conflicts or profile lock issues from other browsers (like Brave).
    """
    if not browser_path:
        browser_path = find_chromium_browser()
    if browser_path:
        lower = browser_path.lower()
        if "msedge" in lower or "edge" in lower:
            p = USER_DATA_DIR / "google_profile_edge"
            p.mkdir(parents=True, exist_ok=True)
            return p
        if "chrome" in lower:
            p = USER_DATA_DIR / "google_profile_chrome"
            p.mkdir(parents=True, exist_ok=True)
            return p
    GOOGLE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return GOOGLE_PROFILE_DIR

# Auto-migrate legacy profile if present in TEMP_DIR
legacy_profile = TEMP_DIR / "luga_google_profile"
if legacy_profile.exists() and not GOOGLE_PROFILE_DIR.exists():
    try:
        shutil.move(legacy_profile, GOOGLE_PROFILE_DIR)
    except Exception:
        pass
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
    Find available Chromium-based browser for Google Authentication and Web Spotlight.
    Prioritizes Microsoft Edge (pre-installed natively on Windows 10 & 11) and Google Chrome,
    ensuring 100% reliable Google Account authentication, cross-origin API cookie sharing,
    and uninterrupted image uploads to content-push.googleapis.com.
    """
    if sys.platform.startswith("win"):
        # 1. First Priority: Microsoft Edge (natively integrated on Windows 10 & 11, zero cookie blocking)
        edge_candidates = [
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        for p in edge_candidates:
            if p.exists():
                logger.info(f"🌐 Sử dụng Microsoft Edge cho Google Auth / Spotlight: {p}")
                return str(p)

        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            logger.info(f"🌐 Sử dụng Microsoft Edge từ Registry: {val}")
                            return val
                except Exception:
                    pass
        except Exception:
            pass

        found_edge = shutil.which("msedge.exe") or shutil.which("msedge")
        if found_edge:
            logger.info(f"🌐 Sử dụng Microsoft Edge từ PATH: {found_edge}")
            return found_edge

        # 2. Second Priority: Google Chrome
        chrome_candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        for p in chrome_candidates:
            if p.exists():
                logger.info(f"🌐 Sử dụng Google Chrome: {p}")
                return str(p)

        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            logger.info(f"🌐 Sử dụng Google Chrome từ Registry: {val}")
                            return val
                except Exception:
                    pass
        except Exception:
            pass

        found_chrome = shutil.which("chrome.exe") or shutil.which("chrome")
        if found_chrome:
            logger.info(f"🌐 Sử dụng Google Chrome từ PATH: {found_chrome}")
            return found_chrome

        # 3. Third Priority: User's default browser if it is Chromium-based
        default_browser = get_windows_default_browser()
        if default_browser and is_chromium_browser(default_browser):
            logger.info(f"🌐 Sử dụng trình duyệt mặc định: {default_browser}")
            return default_browser

        # 4. Fallback to other Chromium candidates (Brave, Cốc Cốc, etc.)
        other_candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "CocCoc" / "Browser" / "Application" / "browser.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "CocCoc" / "Browser" / "Application" / "browser.exe",
        ]
        for p in other_candidates:
            if p.exists():
                return str(p)

    # Generic / non-Windows environments
    for name in ("msedge", "microsoft-edge", "chrome", "google-chrome", "chromium"):
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
        profile_dir = get_google_profile_dir(browser_path)

        target_url = login_url
        if not target_url:
            if force_account_picker:
                target_url = "https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app"
            else:
                target_url = "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app"

        if not browser_path:
            import webbrowser
            logger.info(f"Mở Google Gemini qua trình duyệt mặc định: {target_url}")
            webbrowser.open(target_url)
            return {
                "status": "ok",
                "message": "Đã mở trang đăng nhập Google Gemini trên trình duyệt mặc định của bạn."
            }

        self._active_cdp_port = get_available_cdp_port(DEFAULT_CDP_PORT)
        profile_path = str(profile_dir.resolve())

        # Clean up any stale singleton locks from previous sessions
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
            lock_p = profile_dir / lock_name
            if lock_p.exists():
                try:
                    lock_p.unlink(missing_ok=True)
                except Exception:
                    pass
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

        # 3. If full reset requested, clear profile directories
        if clear_browser_profile:
            for p in (USER_DATA_DIR / "google_profile_edge", USER_DATA_DIR / "google_profile_chrome", GOOGLE_PROFILE_DIR):
                try:
                    if p.exists():
                        shutil.rmtree(p, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Error removing profile dir {p}: {e}")

        sound_manager.play_done()
        logger.info("🚪 Đã đăng xuất tài khoản Google Gemini thành công.")
        return {"status": "ok", "message": "Đã đăng xuất tài khoản Google thành công."}

    async def silent_refresh_cookies(self, old_psidts: Optional[str] = None, timeout_sec: float = 16.0) -> bool:
        """
        Silently retrieves fresh Google session cookies using the saved browser profile
        in an off-screen, non-headless Chromium window with ZERO user intervention,
        ZERO visible windows, and BotGuard-safe token renewal.
        """
        if self.is_logging_in:
            return False

        browser_path = find_chromium_browser()
        profile_dir = get_google_profile_dir(browser_path)
        if not browser_path or not profile_dir.exists():
            return False

        # Check if profile has any actual user data
        profile_path = str(profile_dir.resolve())
        default_dir = profile_dir / "Default"
        if not default_dir.exists():
            return False

        # Clean up any stale singleton locks before off-screen launch
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
            lock_p = profile_dir / lock_name
            if lock_p.exists():
                try:
                    lock_p.unlink(missing_ok=True)
                except Exception:
                    pass

        logger.info("🔄 Đang tự động làm mới session Google Gemini ngầm qua Chromium profile...")
        cdp_port = get_available_cdp_port(DEFAULT_CDP_PORT)
        # We run full Chromium engine (not headless to avoid Google BotGuard rejection)
        # positioned far off-screen with hidden window style
        cmd = [
            browser_path,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={profile_path}",
            "--window-position=-32000,-32000",
            "--window-size=300,300",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking=false",
            "--disable-sync",
            "https://gemini.google.com"
        ]

        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            t0 = time.time()
            ws_url = None
            while time.time() - t0 < 8.0:
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/version")
                    with urllib.request.urlopen(req, timeout=0.6) as r:
                        if r.status == 200:
                            data = json.loads(r.read().decode())
                            ws_url = data.get("webSocketDebuggerUrl")
                            if ws_url:
                                break
                except Exception:
                    pass
                await asyncio.sleep(0.4)

            if not ws_url:
                logger.debug("Không thể kết nối CDP của trình duyệt ngầm.")
                return False

            async with websockets.connect(ws_url, max_size=10_000_000) as ws:
                msg_id = 1
                await ws.send(json.dumps({"id": msg_id, "method": "Network.enable"}))

                start_poll = time.time()
                while time.time() - start_poll < timeout_sec:
                    msg_id += 1
                    await ws.send(json.dumps({"id": msg_id, "method": "Storage.getCookies"}))
                    resp_data = None
                    for _ in range(10):
                        raw_resp = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        msg_obj = json.loads(raw_resp)
                        if msg_obj.get("id") == msg_id:
                            resp_data = msg_obj
                            break

                    if resp_data and "result" in resp_data:
                        cookies = resp_data["result"].get("cookies", [])
                        psid = None
                        psidts = None
                        all_google_cookies = {}
                        now = time.time()

                        for c in cookies:
                            c_name = c.get("name")
                            c_domain = c.get("domain", "")
                            c_val = c.get("value", "")
                            c_exp = c.get("expires", 0)
                            if ("google.com" in c_domain or "googleapis.com" in c_domain) and c_name and c_val:
                                all_google_cookies[c_name] = c_val
                                if c_name == "__Secure-1PSID":
                                    psid = c_val
                                elif c_name == "__Secure-1PSIDTS":
                                    is_fresh = (c_exp > now + 60) or (old_psidts and c_val != old_psidts) or (not old_psidts and c_val)
                                    if is_fresh:
                                        psidts = c_val

                        if psid and psidts:
                            logger.info("🎉 Đã lấy được cookies mới từ profile ngầm! Đang kết nối Gemini...")
                            from app.gemini_service import gemini_service
                            ok = await gemini_service.init_session(psid, psidts, all_cookies=all_google_cookies)
                            if ok:
                                logger.info("✅ Phục hồi session Google Gemini ngầm thành công!")
                                await self._close_login_browser(ws)
                                return True

                    await asyncio.sleep(1.0)
        except Exception as e:
            logger.debug(f"Silent cookie refresh exception: {e}")
        finally:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.5)
                    except Exception:
                        proc.kill()
                except Exception:
                    pass

        return False

    async def switch_account(self, hub_broadcast_func: Optional[Callable] = None) -> Dict[str, Any]:
        """Log out current account and immediately launch browser to choose/add another account."""
        await self.logout(clear_browser_profile=False)
        return await self.start_web_login(
            hub_broadcast_func=hub_broadcast_func,
            login_url="https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app"
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
                        all_google_cookies = {}

                        for c in cookies:
                            c_name = c.get("name")
                            c_domain = c.get("domain", "")
                            c_val = c.get("value", "")
                            if ("google.com" in c_domain or "googleapis.com" in c_domain) and c_name and c_val:
                                all_google_cookies[c_name] = c_val
                                if c_name == "__Secure-1PSID":
                                    psid = c_val
                                elif c_name == "__Secure-1PSIDTS":
                                    psidts = c_val

                        # If __Secure-1PSID is detected:
                        if psid:
                            # Google Gemini requires both __Secure-1PSID and __Secure-1PSIDTS for modern auth.
                            # Keep waiting calmly while user signs in and browser completes redirect to Gemini.
                            if not psidts:
                                psid_wait_count += 1
                                if psid_wait_count % 3 == 0:
                                    logger.info(f"Đã bắt được __Secure-1PSID, đang chờ Google hoàn tất xác thực ({psid_wait_count * 1.5:.0f}s)...")
                                await asyncio.sleep(1.5)
                                continue

                            # Both PSID and PSIDTS are present!
                            # Verify if security check token __Secure-1PSIDCC has settled (allow up to 2 cycles)
                            has_cc = "__Secure-1PSIDCC" in all_google_cookies
                            if not has_cc and psid_wait_count < 2:
                                psid_wait_count += 1
                                logger.info(f"Đang chờ token bảo mật __Secure-1PSIDCC hoàn tất ({psid_wait_count})...")
                                await asyncio.sleep(1.5)
                                continue

                            # Check if browser has finished redirecting to gemini.google.com
                            is_on_gemini = False
                            try:
                                msg_id += 1
                                await ws.send(json.dumps({"id": msg_id, "method": "Target.getTargets"}))
                                for _ in range(5):
                                    t_resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                    t_obj = json.loads(t_resp)
                                    if t_obj.get("id") == msg_id:
                                        targets = t_obj.get("result", {}).get("targetInfos", [])
                                        is_on_gemini = any(
                                            t.get("type") == "page" and "gemini.google.com" in t.get("url", "")
                                            for t in targets
                                        )
                                        break
                            except Exception:
                                is_on_gemini = True  # Fallback if getTargets query times out

                            if not is_on_gemini:
                                psid_wait_count += 1
                                if psid_wait_count % 3 == 0:
                                    logger.info(f"Đang chờ trình duyệt chuyển hướng vào Gemini ({psid_wait_count * 1.5:.0f}s)...")
                                await asyncio.sleep(1.5)
                                continue

                            # Verify session and ensure account is genuinely AVAILABLE before closing browser
                            from app.gemini_service import gemini_service
                            from app.sound_effects import sound_manager

                            ok = await gemini_service.init_session(psid, psidts, all_cookies=all_google_cookies)
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
