"""
Browser Helper module for Luga Assist.
Allows launching Google Chrome 100% in the background (ZERO windows, ZERO tabs)
on both macOS and Windows, enabling the Chrome Extension to run silently.
"""
import sys
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.logger import get_logger

logger = get_logger("BrowserHelper")

def find_chrome_executable() -> Optional[str]:
    """Find Google Chrome binary path across macOS, Windows, and Linux."""
    if sys.platform == "darwin":
        mac_chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if mac_chrome.exists():
            return str(mac_chrome)
        return shutil.which("google-chrome")

    elif sys.platform.startswith("win"):
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return shutil.which("chrome.exe") or shutil.which("chrome")

    else:  # Linux
        for binary in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(binary)
            if found:
                return found
    return None


def is_chrome_running() -> bool:
    """Check if any Google Chrome process is currently alive."""
    try:
        if sys.platform == "darwin":
            res = subprocess.run(["pgrep", "-f", "Google Chrome"], capture_output=True, text=True)
            return res.returncode == 0
        elif sys.platform.startswith("win"):
            res = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                capture_output=True,
                text=True,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            return "chrome.exe" in res.stdout.lower()
        else:
            res = subprocess.run(["pgrep", "-f", "chrome"], capture_output=True, text=True)
            return res.returncode == 0
    except Exception as e:
        logger.debug(f"Error checking Chrome running state: {e}")
        return False


def launch_background_chrome() -> bool:
    """
    Launch Google Chrome in silent background mode (--no-startup-window).
    This opens ZERO windows and ZERO tabs, while keeping the Extension service worker active.
    """
    chrome_path = find_chrome_executable()
    if not chrome_path:
        logger.warning("Không tìm thấy Google Chrome trên máy tính.")
        return False

    logger.info("🚀 Đang khởi động Google Chrome ngầm (chế độ ẩn --no-startup-window, KHÔNG MỞ CỬA SỔ)...")

    try:
        if sys.platform == "darwin":
            # Use 'open' with -g (background) and -j (hidden) plus --no-startup-window
            subprocess.Popen([
                "open", "-a", "Google Chrome", "-g", "-j",
                "--args", "--no-startup-window"
            ])
            logger.info("✅ Đã kích hoạt Google Chrome ngầm trên macOS thành công.")
            return True

        elif sys.platform.startswith("win"):
            # Windows: launch chrome with --no-startup-window and CREATE_NO_WINDOW
            create_flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.Popen(
                [chrome_path, "--no-startup-window", "--silent-launch"],
                creationflags=create_flags
            )
            logger.info("✅ Đã kích hoạt Google Chrome ngầm trên Windows thành công.")
            return True

        else:  # Linux
            subprocess.Popen(
                [chrome_path, "--no-startup-window"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("✅ Đã kích hoạt Google Chrome ngầm trên Linux thành công.")
            return True

    except Exception as e:
        logger.error(f"Lỗi khi khởi động Chrome ngầm: {e}")
        return False


def ensure_background_browser(force: bool = False) -> bool:
    """
    Ensure the background browser is running if needed to maintain
    the Google Extension bridge without ever showing a browser window.
    """
    if is_chrome_running() and not force:
        logger.debug("Google Chrome đã đang chạy trong hệ thống.")
        return True

    return launch_background_chrome()
