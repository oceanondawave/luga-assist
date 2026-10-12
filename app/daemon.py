"""
Cross-platform Background Service / Daemon Manager for Luga Assist.
Allows running Luga Assist 100% in the background on both macOS and Windows
with ZERO terminal windows and ZERO browser tabs needed.
"""
import sys
import os
import time
import signal
import subprocess
import argparse
from pathlib import Path
from typing import Optional

from app.config import (
    BASE_DIR,
    PID_FILE,
    LOG_FILE,
    PORT,
    HOST,
)

def is_pid_running(pid: int) -> bool:
    """Check if process with given PID is currently active on Windows."""
    if pid <= 0:
        return False
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        return str(pid) in res.stdout
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False


def get_running_pid() -> Optional[int]:
    """Get PID of currently running Luga Assist daemon from PID file."""
    if not PID_FILE.exists():
        return None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
            if is_pid_running(pid):
                return pid
    except Exception:
        pass
    # Stale PID file
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def wait_for_server_healthy(timeout: float = 6.0) -> bool:
    """Check if HTTP server on port 8000 responds with 200 OK."""
    import urllib.request
    url = f"http://{HOST}:{PORT}/api/status"
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LugaDaemonCheck/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def start_daemon():
    """Start Luga Assist as a detached background daemon."""
    existing_pid = get_running_pid()
    if existing_pid:
        print(f"⚠️ Luga Assist đã đang chạy ngầm với PID: {existing_pid}")
        print(f"👉 Dùng lệnh: python -m app.daemon status  hoặc  python -m app.daemon stop")
        return True

    print("==========================================================")
    print("      KHỞI ĐỘNG LUGA ASSIST CHẠY NGẦM (BACKGROUND DAEMON) ")
    print("==========================================================")
    print("🚀 Đang khởi động tiến trình ngầm...")

    python_executable = sys.executable

    # Prepare command
    cmd = [python_executable, "-m", "app.main"]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)
    env["LUGA_DAEMON_MODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    # Windows: Use pythonw.exe if available to avoid ANY cmd window
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        cmd[0] = str(pythonw)

    # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = 0x00000008 | 0x00000200
    with open(LOG_FILE, "a", encoding="utf-8") as log_out:
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout=log_out,
            stderr=log_out,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        pid = process.pid

    # Save PID
    with open(PID_FILE, "w") as f:
        f.write(str(pid))

    print(f"⏳ Đang chờ hệ thống sẵn sàng (PID: {pid})...")
    healthy = wait_for_server_healthy(timeout=7.0)

    if healthy:
        print("✅ KHỞI ĐỘNG THÀNH CÔNG! LUGA ASSIST ĐANG CHẠY NGẦM 100%!")
        print("----------------------------------------------------------")
        print("🎙️ Phím tắt toàn cục F8 (hoặc Ctrl + Space) ĐÃ SẴN SÀNG.")
        print("🔇 Màn hình hoàn toàn thoáng đãng, không có cửa sổ terminal nào.")
        print(f"📄 File log hệ thống: {LOG_FILE}")
        print("👉 Dừng chương trình ngầm:  python -m app.daemon stop")
        print("👉 Xem trạng thái:          python -m app.daemon status")
        print("👉 Xem log trực tiếp:       python -m app.daemon logs")
        print("----------------------------------------------------------")
        return True
    else:
        print("⚠️ Tiến trình đã khởi động nhưng chưa phản hồi port 8000.")
        print(f"👉 Vui lòng kiểm tra log: {LOG_FILE}")
        return False


def stop_daemon():
    """Stop running Luga Assist daemon."""
    pid = get_running_pid()
    if not pid:
        print("ℹ️ Luga Assist hiện không chạy ngầm.")
        PID_FILE.unlink(missing_ok=True)
        return True

    print(f"🛑 Đang dừng tiến trình Luga Assist ngầm (PID: {pid})...")

    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            capture_output=True,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        PID_FILE.unlink(missing_ok=True)
        print("✅ Đã dừng Luga Assist ngầm thành công!")
        return True
    except Exception as e:
        print(f"❌ Lỗi khi dừng tiến trình: {e}")
        return False


def status_daemon():
    """Check and display daemon status."""
    pid = get_running_pid()
    print("==========================================================")
    print("           TRẠNG THÁI LUGA ASSIST (DAEMON STATUS)         ")
    print("==========================================================")
    if pid:
        healthy = wait_for_server_healthy(timeout=1.5)
        status_text = "🟢 ĐANG HOẠT ĐỘNG (HEALTHY)" if healthy else "🟡 TIẾN TRÌNH ĐANG CHẠY (Port chưa phản hồi)"
        print(f"Trạng thái:   {status_text}")
        print(f"Process PID:  {pid}")
        print(f"Cổng Server:  http://127.0.0.1:{PORT}")
        print(f"File Log:     {LOG_FILE}")
        print(f"Hotkeys:      F8 hoặc Ctrl+Space sẵn sàng lắng nghe")
    else:
        print("Trạng thái:   🔴 ĐÃ DỪNG (OFFLINE)")
        print(f"Để bật ngầm:  python -m app.daemon start")
    print("==========================================================")


def tail_logs(num_lines: int = 50, follow: bool = False):
    """View recent logs."""
    from app.logger import read_recent_logs
    print(f"--- 50 DÒNG LOG GẦN NHẤT ({LOG_FILE}) ---")
    lines = read_recent_logs(num_lines)
    for l in lines:
        sys.stdout.write(l)

    if follow:
        print("\n--- Đang theo dõi log (Ctrl+C để thoát) ---")
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, os.SEEK_END)
                while True:
                    line = f.readline()
                    if line:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description="Luga Assist Background Daemon Manager")
    parser.add_argument("action", choices=["start", "stop", "restart", "status", "logs"], help="Action to execute")
    parser.add_argument("-n", "--lines", type=int, default=50, help="Number of log lines to show")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow logs live")

    args = parser.parse_args()

    if args.action == "start":
        start_daemon()
    elif args.action == "stop":
        stop_daemon()
    elif args.action == "restart":
        stop_daemon()
        time.sleep(1.0)
        start_daemon()
    elif args.action == "status":
        status_daemon()
    elif args.action == "logs":
        tail_logs(num_lines=args.lines, follow=args.follow)

if __name__ == "__main__":
    main()
