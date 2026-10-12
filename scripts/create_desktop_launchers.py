"""
Cross-Platform Desktop Launcher & Shortcut Generator for Luga Assist.
Creates 100% GUI single unified application launcher on the user's Desktop
for macOS, Windows, and Linux.

Strictly 1 Single App on Desktop:
- "Luga Assist" -> Starts unified app + Spotlight Chat HUD + Voice & Hotkeys (F7, F8, F9).
- Zero terminal window required.
- Zero browser tabs opened automatically.
- All controls (Stop app, Change mode, Chat, Voice, Web) are accessible right inside
  the Spotlight HUD (F7) and global hotkeys!
"""
import sys
import os
import stat
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_desktop_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    return Path.home()


def main():
    print("Desktop Launcher Generator: Đang thiết lập shortcut Desktop cho Windows...")
    create_windows_launchers()

if __name__ == "__main__":
    main()
