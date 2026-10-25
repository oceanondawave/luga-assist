"""
Luga Assist - Fast Standalone Windows Build & Release Tool.
Packages Luga Assist into a windowless standalone executable, compiles
the Windows Setup Wizard (Luga-Assist-Setup.exe) via Inno Setup,
and creates release archives.
"""
import sys
import os
import shutil
import zipfile
import subprocess
import time
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def is_network_path(path: Path) -> bool:
    """
    Checks if a directory path resides on a network share or UNC path.
    Windows Win32 PE Resource APIs (BeginUpdateResourceW) strictly require
    local NTFS/FAT filesystems and fail with WinError 19 (ERROR_WRITE_PROTECT)
    on SMB network shares, UNC paths, and VM shared folders (e.g. Parallels \\Mac\\...).
    """
    try:
        resolved = str(path.resolve())
        # Check UNC prefixes: \\..., //...
        if resolved.startswith(("\\\\", "//")):
            return True
        if os.name == "nt":
            import ctypes
            drive = os.path.splitdrive(resolved)[0]
            if drive:
                drive_root = drive + ("\\" if not drive.endswith("\\") else "")
                # DRIVE_REMOTE = 4
                if ctypes.windll.kernel32.GetDriveTypeW(drive_root) == 4:
                    return True
    except Exception:
        pass
    return False

def close_running_instances():
    """Closes any background running Luga Assist.exe so files are not locked."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "Luga Assist.exe"], capture_output=True, check=False)
        except Exception:
            pass

def disable_windows_quickedit():
    """
    Disables QuickEdit mode in Windows Command Prompt.
    When QuickEdit mode is enabled (default in Windows cmd.exe), clicking
    inside the terminal window highlights text and pauses/freezes the entire
    process (blocking stdout) until the user presses Enter or Esc.
    """
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            STD_INPUT_HANDLE = -10
            hStdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
                ENABLE_QUICK_EDIT_MODE = 0x0040
                ENABLE_EXTENDED_FLAGS = 0x0080
                new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
                kernel32.SetConsoleMode(hStdin, new_mode)
                print("--> [Console] Windows QuickEdit mode disabled (no more freezing on click).")
        except Exception:
            pass

def print_banner(text: str):
    print("\n" + "=" * 68)
    print(f"  {text}")
    print("=" * 68 + "\n")

def run_cmd(cmd_list, description: str):
    print(f"--> [Build] {description}...")
    t0 = time.time()
    res = subprocess.run(cmd_list, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print(f"\n[X] Error during: {description} (Exit code: {res.returncode})")
        sys.exit(res.returncode)
    elapsed = time.time() - t0
    print(f"    Done ({elapsed:.1f}s)")

def zip_directory(source_dir: Path, zip_file_path: Path):
    print(f"--> [Build] Creating archive: {zip_file_path.name}...")
    if zip_file_path.exists():
        zip_file_path.unlink()
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                archive_name = file_path.relative_to(source_dir.parent)
                zipf.write(file_path, arcname=str(archive_name))

def ensure_app_icon():
    ico_path = BASE_DIR / "app.ico"
    png_path = BASE_DIR / "assets" / "icons" / "icon128.png"
    if not ico_path.exists() and png_path.exists():
        try:
            from PIL import Image
            img = Image.open(png_path)
            img.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
            print("--> [Build] Generated app.ico from assets/icons/icon128.png")
        except Exception as e:
            print(f"--> [Build] Notice: Could not generate app.ico ({e})")

def check_python_environment():
    # 1. Detect 32-bit Python on modern Windows
    if sys.maxsize <= 2**32:
        for ver in ["-3.11-64", "-3.12-64", "-3.13-64", "-3-64"]:
            try:
                check = subprocess.run(
                    ["py", ver, "-c", "import sys; print(sys.executable)"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if check.returncode == 0 and check.stdout.strip():
                    py64_exe = check.stdout.strip()
                    print(f"[Notice] Current Python is 32-bit ({sys.executable}).")
                    print(f"[Auto-Switch] Found 64-bit Python: {py64_exe}")
                    print(f"[Auto-Switch] Switching to 64-bit Python to build...\n")
                    res = subprocess.run([py64_exe, str(Path(__file__).resolve())] + sys.argv[1:], cwd=str(BASE_DIR))
                    sys.exit(res.returncode)
            except Exception:
                pass

        print_banner("WARNING: 32-BIT PYTHON DETECTED (win32)")
        print(f"Current Python executable: {sys.executable}\n")
        print("Reason for 'Microsoft Visual C++ 14.0 or greater is required':")
        print("  - Essential dependencies (like 'curl-cffi') only provide")
        print("    pre-built binary wheels for 64-bit Python (win_amd64).")
        print("  - Running under 32-bit forces pip to compile from C++ source.\n")
        print("RECOMMENDED SOLUTION (No C++ compiler needed):")
        print("  1. Download official 64-bit Python (Python 3.11 64-bit):")
        print("     https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe")
        print("  2. During installation, make sure to check: [X] 'Add python.exe to PATH'")
        print("  3. Re-run 'build_windows.bat'!\n")
        print("=" * 68)
        sys.exit(1)

    # 2. Detect experimental/unsupported Python versions (>= 3.14, e.g. 3.15 alpha)
    if sys.version_info >= (3, 14):
        for ver in ["-3.11-64", "-3.12-64", "-3.13-64", "-3.11", "-3.12", "-3.13"]:
            try:
                check = subprocess.run(
                    ["py", ver, "-c", "import sys; exit(0 if (3, 10) <= sys.version_info < (3, 14) and sys.maxsize > 2**32 else 1)"],
                    capture_output=True,
                    check=False,
                )
                if check.returncode == 0:
                    py_stable = subprocess.run(["py", ver, "-c", "import sys; print(sys.executable)"], capture_output=True, text=True).stdout.strip()
                    if py_stable:
                        print(f"[Notice] Current Python {sys.version.split()[0]} is experimental.")
                        print(f"[Auto-Switch] Found stable 64-bit Python: {py_stable}")
                        print(f"[Auto-Switch] Switching to stable Python to build...\n")
                        res = subprocess.run([py_stable, str(Path(__file__).resolve())] + sys.argv[1:], cwd=str(BASE_DIR))
                        sys.exit(res.returncode)
            except Exception:
                pass

        print_banner("WARNING: EXPERIMENTAL PYTHON VERSION DETECTED")
        print(f"Current Python executable: {sys.executable}")
        print(f"Detected version: Python {sys.version.split()[0]} (cp{sys.version_info.major}{sys.version_info.minor})\n")
        print("RECOMMENDED SOLUTION:")
        print("  1. Download official STABLE Python (Python 3.11 64-bit):")
        print("     https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe")
        print("  2. Check: [X] 'Add python.exe to PATH'")
        print("  3. Re-run 'build_windows.bat'!\n")
        print("=" * 68)
        sys.exit(1)

def find_iscc_binary() -> str | None:
    candidates = [
        shutil.which("ISCC.exe"),
        shutil.which("iscc"),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    return None

def ensure_iscc_compiler() -> str | None:
    iscc = find_iscc_binary()
    if iscc:
        return iscc

    print("--> [Installer] Inno Setup compiler (ISCC.exe) not found on system.")

    # Method 1: winget
    winget = shutil.which("winget")
    if winget:
        print("--> [Installer] Attempting silent installation of Inno Setup via winget...")
        try:
            subprocess.run(
                [winget, "install", "--id", "JRSoftware.InnoSetup", "-e", "--accept-source-agreements", "--accept-package-agreements", "--silent"],
                check=False,
            )
            iscc = find_iscc_binary()
            if iscc:
                print(f"--> [Installer] Inno Setup installed successfully via winget: {iscc}")
                return iscc
        except Exception as e:
            print(f"--> [Installer] winget install notice: {e}")

    # Method 2: direct download and silent setup
    print("--> [Installer] Attempting direct download of official Inno Setup installer...")
    try:
        import urllib.request
        temp_dir = BASE_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        setup_installer = temp_dir / "innosetup-setup.exe"

        urls = [
            "https://files.jrsoftware.org/is/6/innosetup-6.3.3.exe",
            "https://www.jrsoftware.org/download.php/is.exe"
        ]
        downloaded = False
        for url in urls:
            try:
                print(f"--> [Installer] Downloading Inno Setup from {url}...")
                urllib.request.urlretrieve(url, str(setup_installer))
                if setup_installer.exists() and setup_installer.stat().st_size > 1000000:
                    downloaded = True
                    break
            except Exception as dl_err:
                print(f"--> [Installer] Download failed: {dl_err}")
                continue

        if downloaded:
            print("--> [Installer] Running silent installation of Inno Setup (/VERYSILENT)...")
            subprocess.run([str(setup_installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"], check=False)
            iscc = find_iscc_binary()
            if iscc:
                print(f"--> [Installer] Inno Setup installed successfully: {iscc}")
                return iscc
    except Exception as e:
        print(f"--> [Installer] Direct download notice: {e}")

    return None

def check_dependencies():
    # 1. PyInstaller check
    try:
        import PyInstaller
    except ImportError:
        run_cmd([sys.executable, "-m", "pip", "install", "pyinstaller"], "Installing PyInstaller")

    # 2. requirements.txt check
    try:
        import fastapi, uvicorn, websockets, mss, PIL, edge_tts, pydantic, sounddevice, pynput, numpy
        print("--> [Build] Required Python packages already verified (fast cache hit).")
    except ImportError:
        run_cmd(
            [sys.executable, "-m", "pip", "install", "--prefer-binary", "--disable-pip-version-check", "-r", "requirements.txt"],
            "Installing requirements.txt (pre-built wheels)"
        )

def main():
    disable_windows_quickedit()
    check_python_environment()
    close_running_instances()
    
    import platform
    arch = platform.machine().upper()

    print_banner("LUGA ASSIST - FAST STANDALONE WINDOWS PACKAGING & RELEASE")
    print(f"Working Directory: {BASE_DIR}")
    print(f"Python: {sys.executable}")
    if arch in ("AMD64", "X86_64"):
        print(f"Target Architecture: x86_64 / AMD64 (Chay tot tren tat ca PC Intel/AMD x86 & Windows ARM)")
    elif arch == "ARM64":
        print(f"Target Architecture: ARM64 (Windows ARM ban dia)")
    else:
        print(f"Target Architecture: {arch}")

    total_start_time = time.time()

    # 1. Fast dependency check
    check_dependencies()

    # 2. Ensure application icon
    ensure_app_icon()

    # Determine build paths (Work & Dist)
    # If the workspace is on a network share (UNC or Parallels VM shared folder \\Mac\...),
    # redirect workpath and distpath to local NTFS %TEMP% to prevent:
    # win32ctypes.pywin32.pywintypes.error: (19, 'BeginUpdateResourceW', 'The media is write protected.')
    is_network = is_network_path(BASE_DIR) or ("--temp-build" in sys.argv)
    if is_network:
        local_base = Path(tempfile.gettempdir()) / "luga_build"
        build_work_dir = local_base / "work"
        build_dist_dir = local_base / "dist"
        build_work_dir.mkdir(parents=True, exist_ok=True)
        build_dist_dir.mkdir(parents=True, exist_ok=True)
        print("--> [Notice] Network share / VM shared folder detected (UNC/Remote Drive):")
        print(f"    {BASE_DIR}")
        print("--> [Auto-Redirect] Windows kernel blocks PE resource updates on network shares (WinError 19).")
        print("--> [Auto-Redirect] Automatically redirecting build work & dist paths to local drive:")
        print(f"    Work path: {build_work_dir}")
        print(f"    Dist path: {build_dist_dir}")
    else:
        build_work_dir = BASE_DIR / "build"
        build_dist_dir = BASE_DIR / "dist"

    # 3. Run PyInstaller (incremental, UPX disabled for maximum speed)
    spec_path = BASE_DIR / "luga_assist_win.spec"
    if not spec_path.exists():
        print(f"[X] Spec file not found: {spec_path}")
        sys.exit(1)

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "-y",
        "--workpath",
        str(build_work_dir),
        "--distpath",
        str(build_dist_dir),
    ]
    if "--clean" in sys.argv:
        pyinstaller_cmd.append("--clean")
    pyinstaller_cmd.append(str(spec_path))

    run_cmd(pyinstaller_cmd, "Building standalone executable with PyInstaller (upx=False)")

    dist_app_dir = build_dist_dir / "Luga Assist"
    if not dist_app_dir.exists():
        print(f"[X] Expected output folder not found: {dist_app_dir}")
        sys.exit(1)

    # 4. Copy launcher scripts for portability
    vbs_src = BASE_DIR / "start_windows.vbs"
    if vbs_src.exists():
        shutil.copy2(vbs_src, dist_app_dir / "start_windows.vbs")

    project_dist_dir = BASE_DIR / "dist"
    project_dist_dir.mkdir(parents=True, exist_ok=True)

    # 5. Build the Standalone Setup Wizard Installer (Luga-Assist-Setup.exe)
    iss_file = BASE_DIR / "scripts" / "windows" / "installer.iss"
    iscc_bin = ensure_iscc_compiler()

    if iscc_bin and iss_file.exists():
        iscc_cmd = [
            iscc_bin,
            f"/DAppRootDir={BASE_DIR}",
            f"/DDistSourceDir={dist_app_dir}",
            f"/DOutputDir={build_dist_dir}",
            str(iss_file),
        ]
        run_cmd(iscc_cmd, "Compiling Windows Setup Wizard (Luga-Assist-Setup.exe)")
    else:
        print_banner("WARNING: INNO SETUP NOT FOUND")
        print("To generate the Windows Setup Wizard (.exe installer):")
        print("  1. Download Inno Setup 6 from: https://jrsoftware.org/isdl.php")
        print("  2. Install it, then run 'build_windows.bat' again.")
        print("=" * 68)

    # 6. If network build, copy final artifacts back to project dist folder
    final_setup_exe = build_dist_dir / "Luga-Assist-Setup.exe"
    target_setup_exe = project_dist_dir / "Luga-Assist-Setup.exe"
    target_app_dir = project_dist_dir / "Luga Assist"

    if is_network:
        print("--> [Build] Copying final build artifacts back to project dist folder...")
        if final_setup_exe.exists():
            try:
                shutil.copy2(final_setup_exe, target_setup_exe)
                print(f"    Copied: {target_setup_exe}")
            except Exception as e:
                print(f"    Warning copying setup exe: {e}")
        if dist_app_dir.exists():
            print(f"    Syncing: {target_app_dir}...")
            try:
                if target_app_dir.exists():
                    shutil.rmtree(target_app_dir)
            except Exception as e:
                print(f"    Notice cleaning old dist dir: {e}")
            try:
                shutil.copytree(dist_app_dir, target_app_dir, dirs_exist_ok=True)
                print(f"    Copied: {target_app_dir}")
            except Exception as e:
                print(f"    Warning syncing app dir: {e}")

        # Clean up temporary build directory on C: drive to free space
        print("--> [Build] Cleaning up temporary build directory on C: drive...")
        try:
            if local_base.exists():
                shutil.rmtree(local_base, ignore_errors=True)
                print(f"    Cleaned: {local_base}")
        except Exception:
            pass
    else:
        target_setup_exe = final_setup_exe

    # 7. Create Portable ZIP only if requested (--zip)
    win_zip = None
    if "--zip" in sys.argv:
        win_zip = project_dist_dir / "Luga-Assist-Windows.zip"
        zip_directory(target_app_dir, win_zip)

    # 8. Print Complete Release Summary
    total_elapsed = time.time() - total_start_time
    print_banner(f"BUILD COMPLETED IN {total_elapsed:.1f}s!")
    if target_setup_exe.exists():
        mb = target_setup_exe.stat().st_size / (1024 * 1024)
        print("  🎉 BO CAI DAT CHINH (STANDALONE SETUP WIZARD):")
        print(f"  👉 {target_setup_exe} ({mb:.1f} MB)\n")
        print("  * Day la file duy nhat can gui cho nguoi dung Windows.")
        print("  * May tinh dich KHONG CAN cai dat Python hay Chrome Extension.")
        print("  * Click dup vao file .exe nay de bat Setup Wizard cai dat:")
        print("      + Tu dong giai nen vao thu muc he thong.")
        print("      + Tao bieu tuong Luga Assist tren Desktop.")
        print("      + Tich hop trinh Go cai dat (Uninstaller) chuan Windows.")
    else:
        print(f"  * Luu y: Bo cai dat Setup.exe chua duoc tao do thieu Inno Setup.")
        print(f"  * Ban co the dung ban chay truc tiep: {target_app_dir / 'Luga Assist.exe'}")

    if win_zip and win_zip.exists():
        print(f"\n  Cac file bo tro:\n    - Portable ZIP  : {win_zip}")
    print("=" * 68 + "\n")

if __name__ == "__main__":
    main()
