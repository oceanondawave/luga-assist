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
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "Luga Assist - Spotlight" in title or "Luga Spotlight" in title:
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


def toggle_spotlight_window_windows() -> bool:
    """
    On Windows: if Spotlight window is in foreground, minimize it.
    If window is in background or minimized, restore and bring to front.
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

        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd == hwnd:
            # Window is currently active in foreground -> minimize it
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE = 6
            logger.info("Spotlight window minimized.")
            return True
        else:
            # Window is minimized or in background -> restore & bring to foreground
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
            user32.SetForegroundWindow(hwnd)
            logger.info("Spotlight window brought to foreground.")
            return True
    except Exception as e:
        logger.debug(f"Could not toggle Spotlight window via Win32: {e}")
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


def launch_or_toggle_web_spotlight():
    """
    Launch or toggle Web Spotlight App Window when user presses F7.
    - If already open: toggles visibility (minimizes if foreground, restores if background).
      NEVER spawns a duplicate process.
    - If not open: launches a single standalone Chromium App window with isolated user profile.
    """
    global _spotlight_proc, _last_launch_time
    with _spotlight_lock:
        now = time.time()
        if now - _last_launch_time < 0.4:
            return  # Debounce quick double-presses
        _last_launch_time = now

        # Case 1: Spotlight is already open -> Toggle visibility, DO NOT launch another process!
        if is_spotlight_window_open():
            logger.info("Spotlight is already open. Toggling window...")
            if sys.platform.startswith("win"):
                toggled = toggle_spotlight_window_windows()
                if toggled:
                    broadcast_spotlight_message({"type": "SPOTLIGHT_FOCUS"})
                    return
            # Non-Windows or Win32 fallback: broadcast toggle event to browser
            broadcast_spotlight_message({"type": "SPOTLIGHT_TOGGLE"})
            return

        # Case 2: Spotlight is NOT open -> Launch cleanly
        spotlight_url = f"http://{HOST}:{PORT}/spotlight"
        browser_path = find_chromium_browser()
        profile_dir = get_spotlight_profile_dir()

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
                return
            except Exception as e:
                logger.warning(f"Lỗi khi chạy browser --app: {e}")

        # Fallback: standard default browser
        logger.info(f"Mở Spotlight qua trình duyệt mặc định: {spotlight_url}")
        webbrowser.open(spotlight_url)
