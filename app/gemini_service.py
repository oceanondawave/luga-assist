"""
Gemini Session Service for Luga Assist.
Leverages the user's existing Google Gemini web session via session cookies (__Secure-1PSID).
Runs 100% in the background with ZERO browser tabs needed.
Automatically resets to a new chat when overloaded.
"""
from pathlib import Path
import json
import asyncio
from typing import Optional, Dict, Any

from gemini_webapi import GeminiClient
from app.config import TEMP_DIR, MAX_TURNS_PER_CHAT

SESSION_FILE = TEMP_DIR / "gemini_session.json"

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
        self.chat_session = None
        self.turns_count = 0
        self.is_ready = False
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
        """Initialize background Gemini client using cookies."""
        async with self._init_lock:
            if not secure_1psid:
                return False

            try:
                print("[GeminiSessionService] Đang kết nối session Google Gemini ngầm...")
                self.client = GeminiClient(
                    secure_1psid=secure_1psid.strip(),
                    secure_1psidts=secure_1psidts.strip() if secure_1psidts else None,
                )
                await self.client.init(timeout=30)
                self.chat_session = self.client.start_chat()
                self.turns_count = 0
                self.is_ready = True

                # Persist to disk
                with open(SESSION_FILE, "w") as f:
                    json.dump({
                        "secure_1psid": secure_1psid.strip(),
                        "secure_1psidts": secure_1psidts.strip() if secure_1psidts else "",
                    }, f)

                print("[GeminiSessionService] ✅ Kết nối Google Gemini ngầm thành công! (100% Không cần mở tab)")
                return True
            except Exception as e:
                print(f"[GeminiSessionService] ❌ Lỗi kết nối session Gemini: {e}")
                self.is_ready = False
                return False

    async def send_prompt(self, prompt: str, image_path: Optional[Path] = None) -> str:
        """Send prompt and optional screenshot to Gemini in background."""
        if not self.is_ready or not self.client or not self.chat_session:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng đảm bảo Extension đã bật và đã đăng nhập Google trên Chrome."
            )

        self.turns_count += 1
        print(f"[GeminiSessionService] Gửi lệnh tới Gemini ngầm (Lượt chat: {self.turns_count}/{MAX_TURNS_PER_CHAT})...")

        # Auto new chat when reaching threshold
        if self.turns_count > MAX_TURNS_PER_CHAT:
            print("[GeminiSessionService] Đã đạt ngưỡng giới hạn phiên, tự động tạo chat mới...")
            self.reset_chat()

        files = [str(image_path)] if image_path and image_path.exists() else None

        try:
            output = await self.chat_session.send_message(prompt, files=files)
            response_text = output.text if hasattr(output, "text") else str(output)
            return response_text
        except Exception as e:
            err_str = str(e).lower()
            if "exhausted" in err_str or "overload" in err_str or "quota" in err_str or "expired" in err_str:
                print(f"[GeminiSessionService] Phiên quá tải ({e}), tự động làm mới chat...")
                self.reset_chat()
                # Retry once on fresh chat
                output = await self.chat_session.send_message(prompt, files=files)
                return output.text if hasattr(output, "text") else str(output)
            raise e

    def reset_chat(self):
        """Create a fresh chat session without memory overload."""
        if self.client:
            self.chat_session = self.client.start_chat()
            self.turns_count = 0
            print("[GeminiSessionService] Đã tạo phiên chat mới thành công.")

gemini_service = GeminiSessionService()
