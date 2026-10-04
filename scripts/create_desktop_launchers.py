"""
Cross-Platform Desktop Launcher & Shortcut Generator for Luga Assist.
Creates 100% GUI double-clickable application launchers on the user's Desktop
for macOS, Windows, and Linux.

Zero Terminal required for end users:
1. "Luga Assist" -> Starts background engine + Opens WebUI + Audio chime
2. "Dừng Luga" -> Stops background engine + Shows notification
3. "Trạng thái Luga" -> Shows native status dialog / alert
"""
import sys
import os
import stat
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_desktop_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    # Fallback to home if Desktop folder doesn't exist
    return Path.home()


def create_macos_apps():
    desktop = get_desktop_dir()
    python_bin = sys.executable

    # 1. Luga Assist.app (Start & Open WebUI)
    app_start = desktop / "Luga Assist.app"
    macos_dir = app_start / "Contents" / "MacOS"
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
</dict>
</plist>
"""
    with open(app_start / "Contents" / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist)

    launcher_start_script = f"""#!/bin/bash
cd "{BASE_DIR}"
"{python_bin}" -m app.daemon start >/dev/null 2>&1
open "http://localhost:8000"
osascript -e 'display notification "Luga Assist đã sẵn sàng phục vụ!" with title "Luga Assist" subtitle "Đang hoạt động"'
"""
    launcher_file = macos_dir / "launcher"
    with open(launcher_file, "w", encoding="utf-8") as f:
        f.write(launcher_start_script)
    launcher_file.chmod(launcher_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 2. Dừng Luga.app (Stop)
    app_stop = desktop / "Dừng Luga.app"
    macos_stop_dir = app_stop / "Contents" / "MacOS"
    macos_stop_dir.mkdir(parents=True, exist_ok=True)

    with open(app_stop / "Contents" / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist.replace("Luga Assist", "Dừng Luga").replace("com.luga.assist", "com.luga.stop"))

    launcher_stop_script = f"""#!/bin/bash
cd "{BASE_DIR}"
"{python_bin}" -m app.daemon stop >/dev/null 2>&1
osascript -e 'display notification "Luga Assist đã dừng hoàn toàn." with title "Luga Assist" subtitle "Đã tắt"'
"""
    launcher_stop_file = macos_stop_dir / "launcher"
    with open(launcher_stop_file, "w", encoding="utf-8") as f:
        f.write(launcher_stop_script)
    launcher_stop_file.chmod(launcher_stop_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 3. Trạng thái Luga.app (Check Status)
    app_status = desktop / "Trạng thái Luga.app"
    macos_status_dir = app_status / "Contents" / "MacOS"
    macos_status_dir.mkdir(parents=True, exist_ok=True)

    with open(app_status / "Contents" / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist.replace("Luga Assist", "Trạng thái Luga").replace("com.luga.assist", "com.luga.status"))

    launcher_status_script = f"""#!/bin/bash
cd "{BASE_DIR}"
STATUS=$("{python_bin}" -c "
import urllib.request, json
try:
    with urllib.request.urlopen('http://localhost:8000/api/system/status', timeout=1.5) as r:
        d = json.loads(r.read())
        mode = d.get('mode_label', 'Không rõ')
        gem = 'Sẵn sàng' if d.get('gemini_ready') else 'Chưa kết nối'
        print(f'🟢 Luga Assist đang HOẠT ĐỘNG!\\\\n\\\\n• Chế độ: {{mode}}\\\\n• Gemini AI: {{gem}}\\\\n• Độ phân giải: {{d.get(\"screen_resolution\")}}\\\\n• Tiến trình PID: {{d.get(\"pid\")}}\\\\n\\\\n🎙️ Phím tắt Micro: F8 hoặc phím Space\\\\n🌐 Giao diện Web: http://localhost:8000')
except Exception:
    print('🔴 Luga Assist hiện ĐANG DỪNG (Không chạy ngầm).\\\\n\\\\nHãy bấm đôi vào Luga Assist trên Desktop để khởi động.')
")
osascript -e "display dialog \\"$STATUS\\" with title \\"Luga Assist - Trạng thái hệ thống\\" buttons {{\\"OK\\"}} default button \\"OK\\""
"""
    launcher_status_file = macos_status_dir / "launcher"
    with open(launcher_status_file, "w", encoding="utf-8") as f:
        f.write(launcher_status_script)
    launcher_status_file.chmod(launcher_status_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print("✅ [macOS] Đã tạo thành công các ứng dụng Desktop:")
    print(f"   • {app_start}")
    print(f"   • {app_stop}")
    print(f"   • {app_status}")


def create_windows_launchers():
    desktop = get_desktop_dir()
    scripts_dir = BASE_DIR / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Start VBS script (Zero cmd window)
    vbs_start = scripts_dir / "start_luga_desktop.vbs"
    with open(vbs_start, "w", encoding="utf-8") as f:
        f.write(f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{BASE_DIR}"
WshShell.Run "python -m app.daemon start", 0, True
WshShell.Run "http://localhost:8000", 1, False
''')

    # 2. Stop VBS script
    vbs_stop = scripts_dir / "stop_luga_desktop.vbs"
    with open(vbs_stop, "w", encoding="utf-8") as f:
        f.write(f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{BASE_DIR}"
WshShell.Run "python -m app.daemon stop", 0, True
MsgBox "Luga Assist đã dừng hoàn toàn.", 64, "Luga Assist"
''')

    # 3. Status VBS script
    vbs_status = scripts_dir / "status_luga_desktop.vbs"
    with open(vbs_status, "w", encoding="utf-8") as f:
        f.write(f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{BASE_DIR}"
Set objExec = WshShell.Exec("python -c ""import urllib.request, json; (lambda: print('🟢 Luga Assist đang HOẠT ĐỘNG!\\n\\nChế độ: ' + json.loads(urllib.request.urlopen('http://localhost:8000/api/system/status').read().decode())['mode_label'] + '\\nMicro: Phím F8'))()"" ")
strOut = ""
Do While Not objExec.StdOut.AtEndOfStream
    strOut = strOut & objExec.StdOut.ReadLine() & vbCrLf
Loop
If strOut = "" Then
    strOut = "🔴 Luga Assist hiện ĐANG DỪNG.\\n\\nHãy bấm vào Luga Assist để khởi động."
End If
MsgBox strOut, 64, "Luga Assist - Trạng thái"
''')

    # Create Shortcuts on Desktop via PowerShell
    ps_cmd = f'''
$wsh = New-Object -ComObject WScript.Shell;
$desktop = [Environment]::GetFolderPath('Desktop');

$s1 = $wsh.CreateShortcut("$desktop\\Luga Assist.lnk");
$s1.TargetPath = "wscript.exe";
$s1.Arguments = '"{vbs_start}"';
$s1.WorkingDirectory = '{BASE_DIR}';
$s1.Description = "Khởi động Luga Assist";
$s1.Save();

$s2 = $wsh.CreateShortcut("$desktop\\Dừng Luga.lnk");
$s2.TargetPath = "wscript.exe";
$s2.Arguments = '"{vbs_stop}"';
$s2.WorkingDirectory = '{BASE_DIR}';
$s2.Description = "Dừng Luga Assist";
$s2.Save();

$s3 = $wsh.CreateShortcut("$desktop\\Trạng thái Luga.lnk");
$s3.TargetPath = "wscript.exe";
$s3.Arguments = '"{vbs_status}"';
$s3.WorkingDirectory = '{BASE_DIR}';
$s3.Description = "Kiểm tra trạng thái Luga Assist";
$s3.Save();
'''
    flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        check=False,
        capture_output=True,
        creationflags=flags
    )
    print("✅ [Windows] Đã tạo thành công các Shortcut Desktop:")
    print(f"   • {desktop / 'Luga Assist.lnk'}")
    print(f"   • {desktop / 'Dừng Luga.lnk'}")
    print(f"   • {desktop / 'Trạng thái Luga.lnk'}")


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
