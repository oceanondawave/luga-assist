"""
Luga Assist - Premium Interactive Terminal Chat & Command Center.
Provides a modern, high-UX terminal interface to control the computer via text.
Powered by Rich, with live spinners, markdown formatting, action trees, and readline history.
Usage:
  luga chat
  python3 -m app.chat_cli
"""
import sys
import os
import atexit
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.config import HOST, PORT
BASE_API_URL = f"http://{HOST}:{PORT}"

# Setup readline for bash-like history & completion
try:
    import readline
    HISTORY_FILE = Path.home() / ".luga_cli_history"
    if HISTORY_FILE.exists():
        try:
            readline.read_history_file(str(HISTORY_FILE))
        except Exception:
            pass
    readline.set_history_length(1000)
    atexit.register(lambda: readline.write_history_file(str(HISTORY_FILE)) if HISTORY_FILE.parent.exists() else None)
except ImportError:
    readline = None

# Rich UI Library
try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    from rich.tree import Tree
    from rich.text import Text
    from rich.syntax import Syntax
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Group = None

console = Console() if RICH_AVAILABLE else None

SLASH_COMMANDS = ["/help", "/screen", "/read", "/tts", "/status", "/clear", "/logs", "/exit", "/quit"]

def completer(text: str, state: int) -> Optional[str]:
    options = [cmd for cmd in SLASH_COMMANDS if cmd.startswith(text.lower())]
    if state < len(options):
        return options[state]
    return None

if readline:
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")

def check_server_status() -> Dict[str, Any]:
    try:
        req = urllib.request.Request(f"{BASE_API_URL}/api/status", headers={"User-Agent": "LugaCLI"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception:
        return {"status": "offline"}

def send_command(command: str, speak: bool = False) -> Optional[Dict[str, Any]]:
    try:
        payload = json.dumps({"command": command, "speak": speak}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_API_URL}/api/command",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"status": "error", "message": str(e)}

def clear_server_chat():
    try:
        req = urllib.request.Request(
            f"{BASE_API_URL}/api/chat/clear",
            data=b"{}",
            headers={"Content-Type": "application/json", "User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=3.0):
            pass
    except Exception:
        pass

def fetch_recent_logs(lines: int = 15) -> List[str]:
    try:
        req = urllib.request.Request(
            f"{BASE_API_URL}/api/logs?lines={lines}",
            headers={"User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
            return data.get("lines", [])
    except Exception:
        return []

def display_welcome_banner(status_data: Dict[str, Any], speak_enabled: bool):
    is_online = status_data.get("status") == "online"
    gemini_ready = status_data.get("gemini_ready", False)
    screen_size = status_data.get("screen_size", (0, 0))

    if not console:
        print("=== LUGA ASSIST - TERMINAL COMMAND CENTER ===")
        return

    banner_text = Text()
    banner_text.append("🎙️ LUGA ASSIST - TRUNG TÂM ĐIỀU KHIỂN & CHAT TERMINAL\n", style="bold cyan")
    banner_text.append("Ra lệnh máy tính qua văn bản • Tương tác tự nhiên • Phản hồi trực quan", style="dim")

    console.print(Panel(
        banner_text,
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2)
    ))

    # Status Grid
    status_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    status_table.add_column("Key", style="dim")
    status_table.add_column("Value")
    status_table.add_column("Key2", style="dim")
    status_table.add_column("Value2")

    server_val = f"[bold green]● Đang chạy (Port {PORT})[/bold green]" if is_online else "[bold red]● Đang dừng (Offline)[/bold red]"
    gemini_val = "[bold green]● Sẵn sàng[/bold green]" if gemini_ready else "[bold yellow]● Chờ kết nối[/bold yellow]"
    tts_val = "[bold green]🔊 BẬT[/bold green]" if speak_enabled else "[bold dim]🔇 TẮT[/bold dim]"
    screen_val = f"[cyan]{screen_size[0]}x{screen_size[1]}[/cyan]" if screen_size[0] > 0 else "[dim]Tự động[/dim]"

    status_table.add_row("Server:", server_val, "Google Gemini:", gemini_val)
    status_table.add_row("Giọng đọc (TTS):", tts_val, "Độ phân giải:", screen_val)

    console.print(status_table)
    console.print("[dim]💡 Gõ câu lệnh trực tiếp hoặc dùng lệnh tắt: [cyan]/help[/cyan] (Trợ giúp) • [cyan]/screen[/cyan] (Mô tả màn hình) • [cyan]/tts[/cyan] (Bật/tắt đọc) • [cyan]/exit[/cyan] (Thoát)[/dim]\n")

def display_help():
    table = Table(title="📋 DANH SÁCH LỆNH TẮT & HƯỚNG DẪN", box=box.ROUNDED, border_style="cyan")
    table.add_column("Lệnh tắt", style="bold cyan", width=14)
    table.add_column("Ý nghĩa / Chức năng", style="white")

    table.add_row("/help", "Xem bảng hướng dẫn lệnh này")
    table.add_row("/screen, /read", "Chụp ảnh và đọc to miêu tả chi tiết màn hình hiện tại")
    table.add_row("/tts", "Bật hoặc tắt giọng đọc âm thanh (TTS)")
    table.add_row("/status", "Kiểm tra trạng thái kết nối server, Gemini, màn hình")
    table.add_row("/logs", "Xem các dòng nhật ký hoạt động hệ thống gần nhất")
    table.add_row("/clear", "Xóa màn hình console và làm mới ngữ cảnh hội thoại")
    table.add_row("/exit, /quit", "Thoát khỏi phòng chat terminal")

    console.print(table)

    examples_panel = Panel(
        "[bold]Ví dụ câu lệnh điều khiển bạn có thể gõ:[/bold]\n"
        "• [cyan]mở Google Chrome và vào trang YouTube[/cyan]\n"
        "• [cyan]tắt tiếng âm thanh hệ thống[/cyan] hoặc [cyan]tăng âm lượng[/cyan]\n"
        "• [cyan]tìm file báo cáo trong thư mục Downloads[/cyan]\n"
        "• [cyan]cho máy tính ngủ ngay lập tức[/cyan]\n"
        "• [cyan]chạy lệnh git status trong terminal[/cyan]\n"
        "• [cyan]soạn thư gửi đến phuongma.luga với tiêu đề test[/cyan]",
        title="💡 Ví dụ câu lệnh",
        border_style="blue",
        box=box.ROUNDED
    )
    console.print(examples_panel)

def render_assistant_response(res: Dict[str, Any]):
    speech = res.get("speech", "Đã thực hiện xong.")
    action_result = res.get("action_result", {})
    details = action_result.get("details", "")
    speech_res = action_result.get("speech_result", "")
    is_done = res.get("done", True)
    step = res.get("step", 1)

    # Main speech markdown
    speech_md = Markdown(speech)

    # Action tree
    tree = None
    if details:
        tree = Tree(f"[bold cyan]⚡ Thao tác OS (Bước {step}):[/bold cyan]")
        parts = details.split(" | ")
        actions_part = parts[0]
        for act in actions_part.split("; "):
            tree.add(f"[green]✓[/green] {act}")
        if len(parts) > 1:
            tree.add(f"[dim]{parts[1]}[/dim]")

    # Dynamic result (file search / terminal output / read file)
    extra_widget = None
    if speech_res and speech_res != speech:
        extra_widget = Panel(
            speech_res,
            title="[bold yellow]📋 Chi tiết kết quả[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED
        )

    # Verification footer
    verified_badge = "[bold green]🎯 Đã xác minh hoàn tất 100% (Outcome Verified)[/bold green]" if is_done else "[yellow]⏳ Đang tiếp tục xử lý...[/yellow]"

    # Assemble assistant panel
    panel_content = []
    panel_content.append(speech_md)
    if tree:
        panel_content.append(Text("\n"))
        panel_content.append(tree)
    if extra_widget:
        panel_content.append(Text("\n"))
        panel_content.append(extra_widget)
    panel_content.append(Text.from_markup(f"\n{verified_badge}"))

    panel = Panel(
        Group(*panel_content),
        title="[bold green]🤖 Luga Assist[/bold green]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2)
    )
    console.print(panel)

def main():
    speak_enabled = "--speak" in sys.argv
    status = check_server_status()

    # If server is offline, offer to auto-start background daemon
    if status.get("status") != "online":
        console.print("\n[bold yellow]⚠️ Server Luga Assist hiện chưa chạy ngầm.[/bold yellow]")
        try:
            start_choice = input("👉 Bạn có muốn tự động khởi động Luga Assist chạy ngầm ngay bây giờ không? (Y/n): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return

        if start_choice in ("", "y", "yes", "có"):
            with console.status("[bold cyan]Đang khởi động Luga Assist ngầm...", spinner="dots"):
                try:
                    from app.daemon import start_daemon
                    start_daemon()
                    # Re-check status
                    import time
                    time.sleep(2.0)
                    status = check_server_status()
                except Exception as e:
                    console.print(f"[bold red]❌ Không thể tự khởi động: {e}[/bold red]")

    # Clear and show welcome banner
    os.system("clear" if os.name != "nt" else "cls")
    display_welcome_banner(status, speak_enabled)

    while True:
        try:
            console.print("[bold cyan]╭─ 👤 Bạn[/bold cyan]")
            user_input = input("╰─➤ ").strip()
            console.print()

            if not user_input:
                continue

            # Handle slash commands
            cmd_lower = user_input.lower()
            if cmd_lower in ("/exit", "/quit", "exit", "quit", "q"):
                console.print(Panel("[bold green]👋 Tạm biệt bạn! Luga Assist luôn sẵn sàng khi bạn cần.[/bold green]", border_style="cyan"))
                break

            if cmd_lower in ("/help", "help", "?"):
                display_help()
                continue

            if cmd_lower in ("/clear", "clear", "cls"):
                clear_server_chat()
                os.system("clear" if os.name != "nt" else "cls")
                status = check_server_status()
                display_welcome_banner(status, speak_enabled)
                continue

            if cmd_lower == "/tts":
                speak_enabled = not speak_enabled
                state_str = "[bold green]BẬT[/bold green]" if speak_enabled else "[bold dim]TẮT[/bold dim]"
                console.print(f"🔊 Giọng đọc âm thanh (TTS) hiện đã: {state_str}\n")
                continue

            if cmd_lower in ("/screen", "/read"):
                user_input = "Hãy miêu tả chi tiết những gì đang hiển thị trên màn hình máy tính của tôi."

            if cmd_lower == "/status":
                status = check_server_status()
                display_welcome_banner(status, speak_enabled)
                continue

            if cmd_lower == "/logs":
                logs = fetch_recent_logs(15)
                if logs:
                    log_text = "".join(logs)
                    console.print(Panel(Syntax(log_text, "log", theme="monokai"), title="📝 Nhật ký gần nhất", border_style="cyan"))
                else:
                    console.print("[dim]Chưa có nhật ký nào gần đây.[/dim]")
                continue

            # Execute command with animated spinner
            with console.status("[bold cyan]⠋ Luga đang phân tích màn hình và thực thi thao tác...", spinner="dots"):
                res = send_command(user_input, speak=speak_enabled)

            if not res or res.get("status") == "error":
                err = res.get("message", "Mất kết nối với server.") if res else "Không phản hồi."
                console.print(Panel(f"[bold red]❌ Lỗi: {err}[/bold red]\n[dim]Hãy kiểm tra lại daemon qua: './luga status'[/dim]", border_style="red"))
            else:
                render_assistant_response(res)

        except (KeyboardInterrupt, EOFError):
            console.print("\n\n" + Panel("[bold green]👋 Tạm biệt bạn! Luga Assist hẹn gặp lại.[/bold green]", border_style="cyan"))
            break

if __name__ == "__main__":
    main()
