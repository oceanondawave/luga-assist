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

from gemini_webapi import GeminiClient, set_log_level
from app.config import TEMP_DIR

# Suppress verbose quota logs in terminal
set_log_level("WARNING")

SESSION_FILE = TEMP_DIR / "gemini_session.json"

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
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

            if self.is_ready and self.client and self._current_psid == cleaned_psid:
                return True

            try:
                print("[GeminiSessionService] Đang kết nối session Google Gemini ngầm...")
                self.client = GeminiClient(
                    secure_1psid=cleaned_psid,
                    secure_1psidts=cleaned_psidts,
                )
                await self.client.init(timeout=30)
                self._current_psid = cleaned_psid
                self.is_ready = True

                # Persist to disk
                with open(SESSION_FILE, "w") as f:
                    json.dump({
                        "secure_1psid": cleaned_psid,
                        "secure_1psidts": cleaned_psidts or "",
                    }, f)

                print("[GeminiSessionService] ✅ Kết nối Google Gemini ngầm thành công! (Tối ưu hóa mô hình siêu tốc)")
                return True
            except Exception as e:
                print(f"[GeminiSessionService] ❌ Lỗi kết nối session Gemini: {e}")
                self.is_ready = False
                return False

    async def send_prompt(self, prompt: str, image_path: Optional[Path] = None) -> str:
        """
        Send prompt and current screenshot to Gemini using high-speed Flash-Lite model.
        Does not accumulate old screenshots in session context, avoiding Google's 35s timeout.
        """
        if not self.is_ready or not self.client:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng đảm bảo Extension đã bật và đã đăng nhập Google trên Chrome."
            )

        files = [str(image_path)] if image_path and image_path.exists() else None

        # Choose the fastest model discovered for this account: 'gemini-flash-lite' or 'gemini-flash'
        try:
            output = await self.client.generate_content(
                prompt=prompt,
                files=files,
                model="gemini-flash-lite"
            )
            response_text = output.text if hasattr(output, "text") else str(output)
            return response_text
        except Exception as e:
            # Fallback to gemini-flash if flash-lite is not available
            try:
                output = await self.client.generate_content(
                    prompt=prompt,
                    files=files,
                    model="gemini-flash"
                )
                return output.text if hasattr(output, "text") else str(output)
            except Exception:
                raise e

    def reset_chat(self):
        """No-op for stateless mode."""
        pass

gemini_service = GeminiSessionService()
