"""
Web Spotlight Launcher for Luga Assist.
Replaces legacy Tkinter UI with a modern, NVDA-accessible Chromium App Window (F7).
Zero browser tabs or URL bars - opens as a standalone native-like window.
Guarantees strict single-instance behavior: never spawns duplicate Edge processes on F7.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from app.config import HOST, PORT
from app.google_auth import find_chromium_browser
from app.logger import get_logger

logger = get_logger("SpotlightLauncher")

_spotlight_proc: Optional[subprocess.Popen] = None
_last_launch_time: float = 0.0
_spotlight_lock = threading.Lock()


def get_spotlight_profile_dir() -> Path:
    """Return an isolated user data directory for the Spotlight Chromium window."""
    profile_dir = Path(tempfile.gettempdir()) / "luga_spotlight_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def is_spotlight_client_connected() -> bool:
    """Check if Spotlight WebUI client is connected via WebSocket."""
    try:
        from app.main import hub
        return hub.is_spotlight_open()
    except Exception:
        return False


def find_spotlight_hwnd_windows() -> Optional[int]:
    """Find HWND of Spotlight window on Windows using Win32 API."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        found_hwnd = []

        def enum_windows_callback(hwnd, extra):
            # 1. Match by child process PID if known
            global _spotlight_proc
            if _spotlight_proc and _spotlight_proc.pid:
                proc_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_pid))
                if proc_pid.value == _spotlight_proc.pid:
                    found_hwnd.append(hwnd)
                    return False

            # 2. Match by window title (case-insensitive)
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.lower()
                if "spotlight" in title:
                    if "visual studio" not in title and "code" not in title and "terminal" not in title:
                        found_hwnd.append(hwnd)
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return found_hwnd[0] if found_hwnd else None
    except Exception as e:
        logger.debug(f"Error finding Spotlight HWND: {e}")
        return None


def is_spotlight_window_open() -> bool:
    """
    Check if Spotlight App is currently open:
    1. Active WebSocket connection from Spotlight client
    2. Alive Chromium child process
    3. Active Win32 window (on Windows)
    """
    global _spotlight_proc
    if is_spotlight_client_connected():
        return True
    if _spotlight_proc is not None and _spotlight_proc.poll() is None:
        return True
    if sys.platform.startswith("win"):
        hwnd = find_spotlight_hwnd_windows()
        if hwnd:
            return True
    return False


def force_foreground_window(hwnd: int) -> bool:
    """
    Forcefully bring a window to the foreground on Windows 10 & 11,
    bypassing Windows Focus-Stealing Prevention without requiring Alt-Tab or manual mouse clicks.
    """
    if not sys.platform.startswith("win") or not hwnd:
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Disable foreground lock timeout so Windows doesn't block focus switch
        SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
        SPIF_SENDCHANGE = 0x02
        try:
            user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE)
            user32.AllowSetForegroundWindow(-1)  # ASFW_ANY = -1
        except Exception:
            pass

        # 2. If minimized (iconic), restore it first
        SW_RESTORE = 9
        SW_SHOW = 5
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd == hwnd:
            user32.SetFocus(hwnd)
            return True

        cur_thread = kernel32.GetCurrentThreadId()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        # Attach to Explorer shell window thread as well to guarantee foreground activation privilege
        shell_hwnd = user32.GetShellWindow()
        shell_thread = user32.GetWindowThreadProcessId(shell_hwnd, None) if shell_hwnd else 0

        attached_fg = False
        attached_shell = False

        if fg_thread and fg_thread != cur_thread:
            attached_fg = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
        if shell_thread and shell_thread != cur_thread:
            attached_shell = bool(user32.AttachThreadInput(cur_thread, shell_thread, True))

        try:
            # 3. Simulate VK_MENU (Alt key) tap to trigger OS input processing right
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            # 4. Bring window to top & punch through z-order
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)

            # 5. Direct internal Windows Alt-Tab switcher call
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
        finally:
            if attached_fg:
                user32.AttachThreadInput(cur_thread, fg_thread, False)
            if attached_shell:
                user32.AttachThreadInput(cur_thread, shell_thread, False)

        return True
    except Exception as e:
        logger.debug(f"Error in force_foreground_window: {e}")
        return False


def bring_spotlight_to_front_windows() -> bool:
    """Bring Spotlight window to foreground on Windows without requiring Alt-Tab."""
    if not sys.platform.startswith("win"):
        return False
    try:
        hwnd = find_spotlight_hwnd_windows()
        if hwnd:
            return force_foreground_window(hwnd)
        return False
    except Exception as e:
        logger.debug(f"Could not bring Spotlight to front: {e}")
        return False


def toggle_spotlight_window_windows(force_show: bool = False) -> bool:
    """
    On Windows: if Spotlight window is active in the foreground, minimize it.
    If window is in background or minimized (or force_show=True), restore and bring to front.
    Returns True if window was found and toggled.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = find_spotlight_hwnd_windows()
        if not hwnd:
            return False

        if force_show:
            force_foreground_window(hwnd)
            return True

        is_iconic = bool(user32.IsIconic(hwnd))
        fg_hwnd = user32.GetForegroundWindow()

        # If Spotlight is the active foreground window and NOT minimized -> minimize it
        if fg_hwnd == hwnd and not is_iconic:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
            logger.info("Spotlight window minimized.")
            return True
        else:
            # Window is minimized or in background -> restore & force to foreground
            force_foreground_window(hwnd)
            logger.info("Spotlight window forced to foreground.")
            return True
    except Exception as e:
        logger.debug(f"Could not toggle Spotlight window via Win32: {e}")
        return False


def minimize_spotlight_window_windows() -> bool:
    """
    Minimize / hide Spotlight window on Windows immediately so that
    it never obstructs screen captures or blocks mouse clicks on underlying applications.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = find_spotlight_hwnd_windows()
        if hwnd:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
            return True
        return False
    except Exception as e:
        logger.debug(f"Could not minimize Spotlight window: {e}")
        return False


def broadcast_spotlight_message(payload: dict):
    """Safely broadcast message to Spotlight client from sync thread."""
    try:
        from app.main import hub, server_async_loop
        import asyncio
        if server_async_loop and server_async_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                hub.broadcast_webui(payload),
                server_async_loop
            )
    except Exception as e:
        logger.debug(f"Error broadcasting to Spotlight: {e}")


def launch_or_toggle_web_spotlight(force_show: bool = False):
    """
    Launch or toggle Web Spotlight App Window when user presses F7 or on app startup.
    - If already open: toggles visibility (minimizes if foreground, forces to front if background).
      NEVER spawns a duplicate process.
    - If not open: launches a single standalone Chromium App window and immediately brings it to front.
    """
    global _spotlight_proc, _last_launch_time
    with _spotlight_lock:
        now = time.time()
        if not force_show and now - _last_launch_time < 0.35:
            return  # Debounce quick double-presses
        _last_launch_time = now

        # Case 1: Spotlight is already open -> Toggle or focus, DO NOT launch another process!
        if is_spotlight_window_open():
            logger.info("Spotlight is already open. Bringing to front...")
            if sys.platform.startswith("win"):
                toggled = toggle_spotlight_window_windows(force_show=force_show)
                if toggled:
                    broadcast_spotlight_message({"type": "SPOTLIGHT_FOCUS"})
                    return
            # Non-Windows or Win32 fallback: broadcast focus event to browser
            broadcast_spotlight_message({"type": "SPOTLIGHT_FOCUS" if force_show else "SPOTLIGHT_TOGGLE"})
            return

        # Case 2: Spotlight is NOT open -> Launch cleanly
        spotlight_url = f"http://{HOST}:{PORT}/spotlight"
        browser_path = find_chromium_browser()
        profile_dir = get_spotlight_profile_dir()

        def _poll_and_focus():
            """Poll for Spotlight window and immediately force it to the foreground with zero Alt-Tab."""
            for _ in range(35):
                time.sleep(0.1)
                hwnd = find_spotlight_hwnd_windows()
                if hwnd:
                    force_foreground_window(hwnd)
                    broadcast_spotlight_message({"type": "SPOTLIGHT_FOCUS"})
                    break

        if browser_path:
            cmd = [
                browser_path,
                f"--app={spotlight_url}",
                f"--user-data-dir={str(profile_dir)}",
                "--window-size=720,440",
                "--window-position=center",
                "--no-first-run",
                "--no-default-browser-check"
            ]
            logger.info(f"🚀 Khởi chạy Web Spotlight App Window (F7): {browser_path}")
            try:
                _spotlight_proc = subprocess.Popen(cmd)
                if sys.platform.startswith("win"):
                    threading.Thread(target=_poll_and_focus, daemon=True).start()
                return
            except Exception as e:
                logger.warning(f"Lỗi khi chạy browser --app: {e}")

        # Fallback: standard default browser
        logger.info(f"Mở Spotlight qua trình duyệt mặc định: {spotlight_url}")
        webbrowser.open(spotlight_url)
        if sys.platform.startswith("win"):
            threading.Thread(target=_poll_and_focus, daemon=True).start()
