"""
Luga Assist - Interactive Terminal Chat CLI.
Allows users to chat with Google Gemini directly from the terminal.
Usage:
  luga chat
  python3 -m app.chat_cli
"""
import sys
import asyncio
import urllib.request
import json
from pathlib import Path
from typing import Optional

def is_server_running() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/status", headers={"User-Agent": "LugaCLI"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "online"
    except Exception:
        return False

def chat_via_server(message: str, speak: bool = False) -> Optional[str]:
    try:
        payload = json.dumps({"message": message, "speak": speak}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/chat",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "LugaCLI"}
        )
        with urllib.request.urlopen(req, timeout=45.0) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "")
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

async def chat_direct(message: str) -> str:
    from app.gemini_service import gemini_service
    if not gemini_service.is_ready:
        await gemini_service.auto_init_from_disk()
    if not gemini_service.is_ready:
        return "❌ Chưa tìm thấy phiên Google Gemini đăng nhập. Vui lòng mở Chrome đăng nhập Gemini hoặc khởi động server qua 'luga start'."
    return await gemini_service.send_chat_message(message)

def main():
    server_online = is_server_running()
    print("=" * 62)
    print("        💬 LUGA ASSIST - TRÒ CHUYỆN AI (CHAT MODE)        ")
    print("=" * 62)
    if server_online:
        print("🔗 Đã kết nối với Luga Assist Background Server (Cổng 8000).")
    else:
        print("⚡ Chạy ở chế độ độc lập (Standalone Session).")
    print("👉 Gõ câu hỏi hoặc nội dung bạn muốn trò chuyện.")
    print("👉 Gõ 'clear' để làm mới đoạn chat, 'exit' hoặc 'quit' để thoát.")
    print("=" * 62 + "\n")

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
                else:
                    from app.gemini_service import gemini_service
                    gemini_service.reset_conversation()
                print("✨ Đã làm mới phiên trò chuyện (Context reset).")
                continue

            print("🤖 Gemini: Đang suy nghĩ...", end="\r", flush=True)

            if server_online:
                reply = chat_via_server(user_msg, speak=speak_mode)
            else:
                reply = asyncio.run(chat_direct(user_msg))

            # Erase the 'Đang suy nghĩ...' line
            print(" " * 40, end="\r")
            if reply:
                print(f"🤖 Gemini:\n{reply}\n")
            else:
                print("❌ Không nhận được phản hồi từ Gemini.")

        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Tạm biệt bạn! Hẹn gặp lại.")
            break

if __name__ == "__main__":
    main()
