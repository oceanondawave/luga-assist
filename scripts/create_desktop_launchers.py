"""
Windows Desktop Launcher & Shortcut Generator for Luga Assist.
Creates 100% GUI single unified application launcher on the user's Desktop for Windows.

Strictly 1 Single App on Desktop:
- "Luga Assist" -> Starts unified app + Spotlight Chat HUD + Voice & Hotkeys (F7, F8, F9).
- Zero terminal window required.
- Zero browser tabs opened automatically.
- All controls (Stop app, Change mode, Chat, Voice, Web) are accessible right inside
  the Spotlight HUD (F7) and global hotkeys!
"""
import sys
import os
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def get_desktop_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    return Path.home()

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
                print(f"[Desktop] Cleaned legacy shortcut: {old_s.name}")
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
http.Open "GET", "http://127.0.0.1:8765/api/status", False
http.Send

If Err.Number = 0 And http.Status = 200 Then
    http.Open "POST", "http://127.0.0.1:8765/api/spotlight/show", False
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
$s.Description = "Luga Assist - Ctrl+Shift+Space to Chat, Ctrl+Space to Speak";
$s.Save();
'''
    flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        check=False,
        capture_output=True,
        creationflags=flags
    )
    print(f"[Windows] Desktop Shortcut created: {desktop / 'Luga Assist.lnk'}")

def main():
    print("Desktop Launcher Generator: Setting up Windows Desktop shortcut...")
    create_windows_launchers()

if __name__ == "__main__":
    main()
