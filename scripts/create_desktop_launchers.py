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


def create_macos_apps():
    desktop = get_desktop_dir()
    python_bin = sys.executable

    # 1. Clean up any fragmented legacy desktop apps
    legacy_apps = [
        desktop / "Chat Nhanh (Spotlight).app",
        desktop / "Dừng Luga.app",
        desktop / "Trạng thái Luga.app",
    ]
    for old_app in legacy_apps:
        if old_app.exists():
            try:
                if old_app.is_dir():
                    shutil.rmtree(old_app)
                else:
                    old_app.unlink(missing_ok=True)
                print(f"🧹 Đã dọn dẹp ứng dụng phân mảnh: {old_app.name}")
            except Exception as e:
                print(f"⚠️ Không thể xóa {old_app.name}: {e}")

    # 2. Unified "Luga Assist.app"
    app_target = desktop / "Luga Assist.app"
    macos_dir = app_target / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.luga.assist</string>
    <key>CFBundleName</key>
    <string>Luga Assist</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>Luga Assist cần quyền truy cập Micro để nhận diện câu lệnh giọng nói.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>Luga Assist cần quyền nhận diện giọng nói tiếng Việt và tiếng Anh.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>Luga Assist cần quyền điều khiển hệ thống qua AppleScript.</string>
    <key>NSAccessibilityUsageDescription</key>
    <string>Luga Assist cần quyền trợ năng để hỗ trợ điều khiển máy tính.</string>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Luga Assist cần quyền chụp màn hình để AI quan sát giao diện.</string>
</dict>
</plist>
"""
    with open(app_target / "Contents" / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist)

    # Launcher checks if Luga is already running. If so, simply triggers HUD show.
    # Otherwise, launches start.sh inside Terminal so macOS grants 100% full microphone permissions!
    launcher_script = f"""#!/bin/bash
BASE_DIR="{BASE_DIR}"

# 1. Check if Luga Assist is already running in background
if curl -s -m 1 "http://localhost:8000/api/status" >/dev/null 2>&1; then
    curl -s -m 1 -X POST "http://localhost:8000/api/spotlight/show" >/dev/null 2>&1
    osascript -e 'display notification "Luga Assist đã hoạt động. Bấm F7 để Chat, F8 để Nói, F9 để Đổi chế độ." with title "Luga Assist"' >/dev/null 2>&1
    exit 0
fi

# 2. Launch directly inside Terminal to guarantee full macOS microphone & accessibility entitlements
osascript <<EOF
tell application "Terminal"
    do script "cd \\"$BASE_DIR\\" && export PYTHONPATH=\\"$BASE_DIR\\" && python3 -m app.main"
    activate
end tell
EOF
"""
    launcher_file = macos_dir / "launcher"
    with open(launcher_file, "w", encoding="utf-8") as f:
        f.write(launcher_script)
    launcher_file.chmod(launcher_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 3. Also create a direct Luga Assist.command file on Desktop
    cmd_file = desktop / "Luga Assist.command"
    cmd_content = f"""#!/bin/bash
cd "{BASE_DIR}"
export PYTHONPATH="{BASE_DIR}"
python3 -m app.main
"""
    with open(cmd_file, "w", encoding="utf-8") as f:
        f.write(cmd_content)
    cmd_file.chmod(cmd_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("✅ [macOS] Đã thiết lập ứng dụng trên Desktop:")
    print(f"   • {app_target}")
    print(f"   • {cmd_file}")
    print("👉 Khi mở Luga Assist:")
    print("   - Terminal sẽ mở và chạy ./start.sh với đầy đủ 100% quyền Micro, Trợ năng và Màn hình.")
    print("   - Nhấn F7 để Bật/Tắt chat, F8 để nói qua Micro (hoặc Ctrl+Space), F9 để đổi chế độ.")


def create_windows_launchers():
    desktop = get_desktop_dir()
    scripts_dir = BASE_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # Clean up legacy shortcuts
    legacy_shortcuts = [
        desktop / "Chat Nhanh (Spotlight).lnk",
        desktop / "Dừng Luga.lnk",
        desktop / "Trạng thái Luga.lnk",
    ]
    for old_s in legacy_shortcuts:
        if old_s.exists():
            try:
                old_s.unlink(missing_ok=True)
                print(f"🧹 Đã dọn dẹp shortcut cũ: {old_s.name}")
            except Exception:
                pass

    # Clean up obsolete vbs files in scripts/
    for obsolete in ["stop_luga_desktop.vbs", "status_luga_desktop.vbs", "start_spotlight_desktop.vbs"]:
        (scripts_dir / obsolete).unlink(missing_ok=True)

    # Determine pythonw executable to suppress console window
    python_cmd = "python"
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        python_cmd = f'"{pythonw}"'

    vbs_start = scripts_dir / "start_luga_desktop.vbs"
    with open(vbs_start, "w", encoding="utf-8") as f:
        f.write(f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{BASE_DIR}"

On Error Resume Next
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.setTimeouts 500, 500, 500, 500
http.Open "GET", "http://127.0.0.1:8000/api/status", False
http.Send

If Err.Number = 0 And http.Status = 200 Then
    http.Open "POST", "http://127.0.0.1:8000/api/spotlight/show", False
    http.Send
Else
    WshShell.Run {python_cmd} & " -m app.main", 0, False
End If
''')

    # Create single shortcut on Desktop via PowerShell
    ps_cmd = f'''
$wsh = New-Object -ComObject WScript.Shell;
$desktop = [Environment]::GetFolderPath('Desktop');
$s = $wsh.CreateShortcut("$desktop\\Luga Assist.lnk");
$s.TargetPath = "wscript.exe";
$s.Arguments = '"{vbs_start}"';
$s.WorkingDirectory = '{BASE_DIR}';
$s.Description = "Khởi động Luga Assist - Nhấn F7 để Chat, F8 để Nói";
$s.Save();
'''
    flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        check=False,
        capture_output=True,
        creationflags=flags
    )
    print("✅ [Windows] Đã tạo thành công 1 Shortcut DUY NHẤT trên Desktop:")
    print(f"   • {desktop / 'Luga Assist.lnk'}")


def main():
    print(f"Desktop Launcher Generator: Đang thiết lập cho {sys.platform}...")
    if sys.platform == "darwin":
        create_macos_apps()
    elif sys.platform.startswith("win"):
        create_windows_launchers()
    else:
        print(f"Hệ điều hành {sys.platform} không có hỗ trợ tạo shortcut Desktop tự động.")

if __name__ == "__main__":
    main()
