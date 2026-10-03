"""
Gemini Session Service for Luga Assist.
Leverages the user's existing Google Gemini web session via session cookies (__Secure-1PSID).
Runs 100% in the background with ZERO browser tabs needed.
Maintains continuous conversation context across all user requests.
Only creates a new chat if explicitly requested or if context is truly overloaded.
"""
from pathlib import Path
import json
import asyncio
from typing import Optional, Dict, Any

from gemini_webapi import GeminiClient
from app.config import TEMP_DIR

SESSION_FILE = TEMP_DIR / "gemini_session.json"

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
        self.chat_session = None
        self.is_ready = False
        self._current_psid: str = ""
        self._init_lock = asyncio.Lock()
        self._saved_cookies = self._read_saved_cookies()

    def _read_saved_cookies(self) -> Optional[Dict[str, str]]:
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("secure_1psid"):
                        return data
            except Exception as e:
                print(f"[GeminiSessionService] Warning loading saved session: {e}")
        return None

    async def auto_init_from_disk(self):
        """Try to automatically initialize if session was previously saved."""
        cookies = self._read_saved_cookies()
        if cookies:
            await self.init_session(
                cookies.get("secure_1psid", ""),
                cookies.get("secure_1psidts", ""),
            )

    async def init_session(self, secure_1psid: str, secure_1psidts: Optional[str] = None) -> bool:
        """Initialize or keep active background Gemini client using cookies."""
        async with self._init_lock:
            cleaned_psid = (secure_1psid or "").strip()
            cleaned_psidts = (secure_1psidts or "").strip() if secure_1psidts else None

            if not cleaned_psid:
                return False

            # If already initialized with the same cookies and session is active,
            # KEEP THE EXISTING CHAT to preserve full conversation context!
            if self.is_ready and self.client and self.chat_session and self._current_psid == cleaned_psid:
                return True

            try:
                print("[GeminiSessionService] Đang kết nối session Google Gemini ngầm...")
                self.client = GeminiClient(
                    secure_1psid=cleaned_psid,
                    secure_1psidts=cleaned_psidts,
                )
                await self.client.init(timeout=30)
                
                # Start or retain chat session
                if self.chat_session is None:
                    self.chat_session = self.client.start_chat()
                    print("[GeminiSessionService] Đã khởi tạo phiên trò chuyện liên tục (Continuous Chat).")
                
                self._current_psid = cleaned_psid
                self.is_ready = True

                # Persist to disk
                with open(SESSION_FILE, "w") as f:
                    json.dump({
                        "secure_1psid": cleaned_psid,
                        "secure_1psidts": cleaned_psidts or "",
                    }, f)

                print("[GeminiSessionService] ✅ Kết nối Google Gemini ngầm thành công! (Duy trì cùng một cuộc hội thoại)")
                return True
            except Exception as e:
                print(f"[GeminiSessionService] ❌ Lỗi kết nối session Gemini: {e}")
                self.is_ready = False
                return False

    async def send_prompt(self, prompt: str, image_path: Optional[Path] = None) -> str:
        """
        Send prompt and optional screenshot to Gemini in the SAME continuous chat.
        This preserves all conversation history and screen context.
        """
        if not self.is_ready or not self.client or not self.chat_session:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng đảm bảo Extension đã bật và đã đăng nhập Google trên Chrome."
            )

        print(f"[GeminiSessionService] Gửi lệnh tiếp nối vào cuộc trò chuyện hiện tại...")

        files = [str(image_path)] if image_path and image_path.exists() else None

        try:
            output = await self.chat_session.send_message(prompt, files=files)
            response_text = output.text if hasattr(output, "text") else str(output)
            return response_text
        except Exception as e:
            err_str = str(e).lower()
            # Only reset if truly overloaded/exhausted by Google's backend
            if "exhausted" in err_str or "too long" in err_str or "context window" in err_str:
                print(f"[GeminiSessionService] Context thật sự bị quá tải ({e}), tạo chat mới...")
                self.reset_chat()
                output = await self.chat_session.send_message(prompt, files=files)
                return output.text if hasattr(output, "text") else str(output)
            raise e

    def reset_chat(self):
        """Create a fresh chat session only when explicitly asked or overloaded."""
        if self.client:
            self.chat_session = self.client.start_chat()
            print("[GeminiSessionService] Đã tạo phiên chat mới thành công.")

gemini_service = GeminiSessionService()
