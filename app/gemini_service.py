"""
Gemini Session Service for Luga Assist.
Leverages the user's existing Google Gemini web session via session cookies (__Secure-1PSID).
Runs 100% in the background with ZERO browser tabs needed.
Maintains continuous conversation context across all user requests.
Only creates a new chat if explicitly requested or if context is truly overloaded.
"""
from pathlib import Path
import json
import re
import asyncio
from typing import Optional, Dict, Any

from gemini_webapi import GeminiClient, set_log_level
from app.config import TEMP_DIR

# Suppress verbose quota logs in terminal
set_log_level("WARNING")

SESSION_FILE = TEMP_DIR / "gemini_session.json"

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
        self.chat_session = None
        self.is_ready = False
        self._current_psid: str = ""
        self._current_psidts: str = ""
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

    def _start_chat_safe(self):
        """Start chat with fastest model (gemini-flash-lite) to maintain context without stalls."""
        try:
            return self.client.start_chat(model="gemini-flash-lite")
        except Exception:
            return self.client.start_chat(model="gemini-flash")

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
            cleaned_psidts = (secure_1psidts or "").strip() if secure_1psidts else ""

            if not cleaned_psid:
                return False

            # If already initialized with THE EXACT SAME COOKIES and IS HEALTHY, keep existing session
            if (
                self.is_ready
                and self.client
                and self._current_psid == cleaned_psid
                and self._current_psidts == cleaned_psidts
            ):
                if self.chat_session is None:
                    self.chat_session = self._start_chat_safe()
                return True

            try:
                print("[GeminiSessionService] Đang kết nối session Google Gemini ngầm...")
                self.client = GeminiClient(
                    secure_1psid=cleaned_psid,
                    secure_1psidts=cleaned_psidts or None,
                )
                await self.client.init(timeout=30)
                self._current_psid = cleaned_psid
                self._current_psidts = cleaned_psidts
                self.is_ready = True

                # Start or retain continuous chat session
                if self.chat_session is None:
                    self.chat_session = self._start_chat_safe()
                    print(f"[GeminiSessionService] Đã khởi tạo 1 phiên trò chuyện liên tục duy nhất (Continuous Chat).")

                # Persist to disk
                with open(SESSION_FILE, "w") as f:
                    json.dump({
                        "secure_1psid": cleaned_psid,
                        "secure_1psidts": cleaned_psidts,
                    }, f)

                print("[GeminiSessionService] ✅ Kết nối Google Gemini ngầm thành công! (Duy trì 1 cuộc trò chuyện liên tục)")
                return True
            except Exception as e:
                print(f"[GeminiSessionService] ❌ Lỗi kết nối session Gemini: {e}")
                self.is_ready = False
                return False

    async def send_prompt(self, prompt: str, image_path: Optional[Path] = None) -> str:
        """
        Send prompt and current screenshot to Gemini in the SAME continuous chat.
        This preserves all conversation history and screen context.
        Uses high-speed Flash-Lite model for immediate responses (<5s).
        """
        if not self.is_ready or not self.client:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng đảm bảo Extension đã bật và đã đăng nhập Google trên Chrome."
            )

        if self.chat_session is None:
            self.chat_session = self._start_chat_safe()

        files = [str(image_path)] if image_path and image_path.exists() else None

        try:
            print(f"[GeminiSessionService] Gửi lệnh vào cuộc trò chuyện hiện tại (cid={self.chat_session.cid or 'mới'})...")
            output = await self.chat_session.send_message(prompt, files=files)
            response_text = output.text if hasattr(output, "text") else str(output)
            # Remove any citation badges e.g. [cite: 1], [cite: 1, 2], [cite: ...]
            response_text = re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
            return response_text
        except Exception as e:
            err_str = str(e).lower()
            if "unauthenticated" in err_str or "permission denied" in err_str or "cookie" in err_str:
                print(f"[GeminiSessionService] ⚠️ Session Google hết hạn hoặc chưa xác thực: {e}")
                self.is_ready = False
                self.client = None
                self.chat_session = None
            elif "exhausted" in err_str or "too long" in err_str or "context window" in err_str:
                print(f"[GeminiSessionService] Context bị quá tải ({e}), tự động làm mới chat session...")
                self.reset_chat()
                output = await self.chat_session.send_message(prompt, files=files)
                response_text = output.text if hasattr(output, "text") else str(output)
                return re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
            raise e

    def reset_chat(self):
        """Reset to a fresh chat session only when explicitly requested or overloaded."""
        if self.client:
            self.chat_session = self._start_chat_safe()
            print("[GeminiSessionService] Đã tạo phiên chat mới thành công.")

gemini_service = GeminiSessionService()
