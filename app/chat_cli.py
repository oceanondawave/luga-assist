"""
Luga Assist - Interactive Terminal Chat & Command CLI.
Allows users to chat with text to control the computer or query the system.
Usage:
  luga chat
  python3 -m app.chat_cli
"""
import sys
import asyncio
import urllib.request
import json
from pathlib import Path
from typing import Optional, Dict, Any

def is_server_running() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/status", headers={"User-Agent": "LugaCLI"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "online"
    except Exception:
        return False

def command_via_server(command: str, speak: bool = False) -> Optional[Dict[str, Any]]:
    try:
        payload = json.dumps({"command": command, "speak": speak}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/command",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"\n[Lỗi kết nối Server]: {e}")
        return None

def clear_chat_via_server():
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/chat/clear",
            data=b"{}",
            headers={"Content-Type": "application/json", "User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=5.0):
            pass
    except Exception:
        pass

def main():
    server_online = is_server_running()
    print("=" * 66)
    print("      💬 LUGA ASSIST - ĐIỀU KHIỂN HỆ THỐNG BẰNG CHAT TEXT       ")
    print("=" * 66)
    if server_online:
        print("🔗 Đã kết nối với Luga Assist Background Server (Cổng 8000).")
    else:
        print("⚠️ Server chưa chạy. Vui lòng gõ './luga start' để khởi động hệ thống ngầm.")
    print("👉 Nhập lệnh điều khiển máy tính, mở app, tìm file, đọc màn hình...")
    print("   Ví dụ: 'mở Chrome và vào youtube', 'tắt tiếng', 'tìm file report.docx'")
    print("👉 Gõ 'clear' để làm mới đoạn chat, 'exit' hoặc 'quit' để thoát.")
    print("=" * 66 + "\n")

    speak_mode = "--speak" in sys.argv

    while True:
        try:
            user_msg = input("\n👤 Bạn: ").strip()
            if not user_msg:
                continue

            if user_msg.lower() in ("exit", "quit", "q"):
                print("\n👋 Tạm biệt bạn! Hẹn gặp lại.")
                break

            if user_msg.lower() in ("clear", "cls", "reset", "new"):
                if server_online:
                    clear_chat_via_server()
                print("✨ Đã làm mới phiên trò chuyện (Context reset).")
                continue

            print("🤖 Luga: Đang phân tích màn hình và thực thi...", end="\r", flush=True)

            if not server_online:
                # Re-check server in case it was started
                server_online = is_server_running()

            if server_online:
                res = command_via_server(user_msg, speak=speak_mode)
            else:
                print(" " * 55, end="\r")
                print("❌ Server Luga Assist chưa chạy. Hãy mở terminal khác gõ: './luga start'")
                continue

            print(" " * 55, end="\r")
            if res:
                speech = res.get("speech", "")
                action_res = res.get("action_result", {})
                print(f"🤖 Luga: {speech}")
                if action_res.get("details"):
                    print(f"⚡ Thao tác: {action_res.get('details')}")
                dyn_res = action_res.get("speech_result")
                if dyn_res and dyn_res != speech:
                    print(f"📋 Kết quả chi tiết:\n{dyn_res}")
            else:
                print("❌ Không nhận được phản hồi từ hệ thống.")

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Tạm biệt bạn! Hẹn gặp lại.")
            break

if __name__ == "__main__":
    main()
