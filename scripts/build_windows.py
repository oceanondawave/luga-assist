"""
Luga Assist - Standalone Windows Build & Release Tool.
Packages Luga Assist into a windowless .exe, packages the Chrome Extension,
and creates release ZIP archives without batch file encoding issues.
"""
import sys
import os
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def print_banner(text: str):
    print("\n" + "=" * 65)
    print(f"  {text}")
    print("=" * 65 + "\n")

def run_cmd(cmd_list, description: str):
    print(f"--> [Build] {description}...")
    res = subprocess.run(cmd_list, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print(f"\n[X] Error during: {description} (Exit code: {res.returncode})")
        sys.exit(res.returncode)

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

def main():
    print_banner("LUGA ASSIST - WINDOWS STANDALONE PACKAGING & RELEASE")
    print(f"Working Directory: {BASE_DIR}")
    print(f"Python: {sys.executable}")

    # 1. Ensure dependencies installed
    run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], "Upgrading pip")
    run_cmd([sys.executable, "-m", "pip", "install", "pyinstaller"], "Installing PyInstaller")
    run_cmd([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], "Installing requirements.txt")

    # 2. Run PyInstaller
    spec_path = BASE_DIR / "luga_assist_win.spec"
    if not spec_path.exists():
        print(f"[X] Spec file not found: {spec_path}")
        sys.exit(1)

    run_cmd(
        [sys.executable, "-m", "PyInstaller", "--clean", "-y", str(spec_path)],
        "Building standalone executable with PyInstaller"
    )

    dist_app_dir = BASE_DIR / "dist" / "Luga Assist"
    if not dist_app_dir.exists():
        print(f"[X] Expected output folder not found: {dist_app_dir}")
        sys.exit(1)

    # 3. Copy extension into dist/Luga Assist/extension
    ext_src = BASE_DIR / "extension"
    ext_dest = dist_app_dir / "extension"
    if ext_src.exists():
        print(f"--> [Build] Copying Chrome Extension to {ext_dest}...")
        if ext_dest.exists():
            shutil.rmtree(ext_dest)
        shutil.copytree(ext_src, ext_dest)

    # 4. Copy launcher scripts for portability
    vbs_src = BASE_DIR / "start_windows.vbs"
    if vbs_src.exists():
        shutil.copy2(vbs_src, dist_app_dir / "start_windows.vbs")

    # 5. Create release ZIPs
    dist_dir = BASE_DIR / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    win_zip = dist_dir / "Luga-Assist-Windows.zip"
    zip_directory(dist_app_dir, win_zip)

    ext_zip = dist_dir / "Luga-Assist-Chrome-Extension.zip"
    if ext_src.exists():
        if ext_zip.exists():
            ext_zip.unlink()
        with zipfile.ZipFile(ext_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(ext_src):
                for file in files:
                    file_path = Path(root) / file
                    archive_name = file_path.relative_to(ext_src)
                    zipf.write(file_path, arcname=str(archive_name))
        print(f"--> [Build] Created: {ext_zip.name}")

    # 6. Check for Inno Setup compiler to build Installer
    iscc_candidates = [
        shutil.which("ISCC.exe") or shutil.which("iscc"),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    iscc_bin = next((str(p) for p in iscc_candidates if p and Path(p).exists()), None)
    iss_file = BASE_DIR / "scripts" / "windows" / "installer.iss"

    if iscc_bin and iss_file.exists():
        print(f"--> [Build] Compiling Inno Setup installer via {iscc_bin}...")
        res = subprocess.run([iscc_bin, str(iss_file)], cwd=str(BASE_DIR))
        if res.returncode == 0:
            print(f"--> [Build] Inno Setup Installer created successfully!")
        else:
            print(f"--> [Build] Inno Setup notice: compilation returned {res.returncode}")

    print_banner("BUILD COMPLETED SUCCESSFULLY!")
    print("Artifacts generated in dist/:")
    print(f"  1. Standalone Executable : {dist_app_dir / 'Luga Assist.exe'}")
    print(f"  2. Portable Release ZIP  : {win_zip}")
    print(f"  3. Chrome Extension ZIP  : {ext_zip}")
    installer_exe = dist_dir / "Luga-Assist-Windows-Installer.exe"
    if installer_exe.exists():
        print(f"  4. Setup Installer EXE   : {installer_exe}")
    print("\nReminder: Load the extension folder into Chrome/Edge before launching Luga Assist.")

if __name__ == "__main__":
    main()
