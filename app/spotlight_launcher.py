"""
Web Spotlight Launcher for Luga Assist.
Replaces legacy Tkinter UI with a modern, NVDA-accessible Chromium App Window (F7).
Zero browser tabs or URL bars - opens as a standalone native-like window.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Optional

from app.config import HOST, PORT
from app.google_auth import find_chromium_browser
from app.logger import get_logger

logger = get_logger("SpotlightLauncher")

_spotlight_proc: Optional[subprocess.Popen] = None
_last_launch_time: float = 0.0


def is_spotlight_window_open() -> bool:
    """Check if Spotlight App process is still alive."""
    global _spotlight_proc
    if _spotlight_proc is not None:
        return _spotlight_proc.poll() is None
    return False


def bring_spotlight_to_front_windows():
    """Bring existing Spotlight window to foreground on Windows."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32

        def enum_windows_callback(hwnd, extra):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "Luga Assist - Spotlight" in title or "Luga Spotlight" in title:
                    # SW_RESTORE = 9, SW_SHOW = 5
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return True
    except Exception as e:
        logger.debug(f"Could not focus Spotlight window via Win32: {e}")
        return False


def launch_or_toggle_web_spotlight():
    """
    Launch or toggle Web Spotlight App Window when user presses F7.
    Uses Chromium App mode (--app) for 100% NVDA screen reader compatibility.
    """
    global _spotlight_proc, _last_launch_time
    now = time.time()
    if now - _last_launch_time < 0.5:
        return  # Debounce quick double-presses
    _last_launch_time = now

    spotlight_url = f"http://{HOST}:{PORT}/spotlight"

    # If already running on Windows, try bringing to front
    if is_spotlight_window_open():
        logger.info("Spotlight window is already open. Bringing to front...")
        if bring_spotlight_to_front_windows():
            return
        # Broadcast toggle over server
        try:
            from app.main import hub, server_async_loop
            import asyncio
            if server_async_loop and server_async_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    hub.broadcast_webui({"type": "SPOTLIGHT_TOGGLE"}),
                    server_async_loop
                )
        except Exception:
            pass
        return

    browser_path = find_chromium_browser()
    if browser_path:
        # App mode opens a sleek standalone window without address bar or tabs
        cmd = [
            browser_path,
            f"--app={spotlight_url}",
            "--window-size=680,360",
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
