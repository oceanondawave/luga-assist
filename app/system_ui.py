"""
Cross-platform Desktop UI, Notifications, and System Lifecycle Controller.
Provides zero-terminal desktop dialogs, notifications, and graceful shutdown/restart
for macOS, Windows, and Linux.
"""
import sys
import os
import time
import signal
import subprocess
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

from app.logger import get_logger
from app.config import PID_FILE, PORT, HOST
from app.sound_effects import sound_manager
from app.tts_service import tts_service

logger = get_logger("SystemUI")


def show_desktop_notification(title: str, message: str, subtitle: str = "") -> bool:
    """
    Display a native desktop notification without any third-party GUI library.
    Works on macOS (osascript), Windows (PowerShell Toast / Balloon), and Linux (notify-send).
    """
    logger.info(f"Desktop Notification: [{title}] {message}")
    try:
        if sys.platform == "darwin":
            # Sanitize double quotes
            safe_title = title.replace('"', '\\"')
            safe_msg = message.replace('"', '\\"')
            safe_sub = subtitle.replace('"', '\\"')
            if safe_sub:
                script = f'display notification "{safe_msg}" with title "{safe_title}" subtitle "{safe_sub}"'
            else:
                script = f'display notification "{safe_msg}" with title "{safe_title}"'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
            return True

        elif sys.platform.startswith("win"):
            # PowerShell Balloon / Toast notification
            ps_script = f"""
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");
$notify = New-Object System.Windows.Forms.NotifyIcon;
$notify.Icon = [System.Drawing.SystemIcons]::Information;
$notify.BalloonTipTitle = "{title.replace('"', '`"')}";
$notify.BalloonTipText = "{message.replace('"', '`"')}";
$notify.Visible = $True;
$notify.ShowBalloonTip(3000);
"""
            flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                check=False,
                capture_output=True,
                creationflags=flags
            )
            return True

        elif sys.platform.startswith("linux"):
            subprocess.run(["notify-send", title, message], check=False, capture_output=True)
            return True

    except Exception as e:
        logger.error(f"Error displaying desktop notification: {e}")
    return False


def show_desktop_dialog(title: str, message: str) -> None:
    """
    Display a native modal dialog box (alert) on the desktop.
    """
    try:
        if sys.platform == "darwin":
            safe_msg = message.replace('"', '\\"').replace('\n', '\\n')
            safe_title = title.replace('"', '\\"')
            script = f'display dialog "{safe_msg}" with title "{safe_title}" buttons {{"OK"}} default button "OK"'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
        elif sys.platform.startswith("win"):
            ps_script = f"""
[void] [System.Windows.Forms.MessageBox]::Show("{message.replace('"', '`"')}", "{title.replace('"', '`"')}", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information);
"""
            flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                check=False,
                capture_output=True,
                creationflags=flags
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(["zenity", "--info", f"--title={title}", f"--text={message}"], check=False, capture_output=True)
    except Exception as e:
        logger.error(f"Error displaying desktop dialog: {e}")


async def trigger_graceful_shutdown(delay: float = 1.0, speak: bool = True, goodbye_text: Optional[str] = None) -> None:
    """
    Gracefully shuts down the Luga Assist server and background daemon.
    1. Plays done audio chime.
    2. Announces goodbye via TTS (if speak=True).
    3. Shows native desktop notification.
    4. Cleans up PID file.
    5. Terminates process after brief delay so HTTP/WebSocket clients receive response.
    """
    msg = goodbye_text or "Đang tắt Luga Assist. Tạm biệt bạn!"
    logger.info(f"Initiating graceful system shutdown: {msg}")

    # Audio feedback
    sound_manager.play_done()

    # Desktop notification
    show_desktop_notification(
        title="Luga Assist",
        message="Hệ thống đang tắt. Tạm biệt bạn!",
        subtitle="Đã dừng hoạt động"
    )

    if speak:
        try:
            await tts_service.speak(msg)
        except Exception as e:
            logger.warn(f"Shutdown TTS failed: {e}")

    # Clean up PID file
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

    # Schedule process exit
    async def _delayed_kill():
        await asyncio.sleep(delay)
        logger.info("Process terminating now...")
        my_pid = os.getpid()
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            os.kill(my_pid, signal.SIGTERM)
        else:
            sys.exit(0)

    asyncio.create_task(_delayed_kill())


async def trigger_graceful_restart(delay: float = 1.0) -> None:
    """
    Restart the background service cleanly.
    """
    logger.info("Initiating graceful system restart...")
    sound_manager.play_done()
    show_desktop_notification(
        title="Luga Assist",
        message="Hệ thống đang khởi động lại...",
        subtitle="Khởi động lại"
    )
    await tts_service.speak("Luga Assist đang khởi động lại. Vui lòng chờ giây lát.")

    async def _delayed_restart():
        await asyncio.sleep(delay)
        if getattr(sys, "frozen", False):
            os.execl(sys.executable, sys.executable)
        else:
            python = sys.executable
            os.execl(python, python, "-m", "app.main")

    asyncio.create_task(_delayed_restart())
