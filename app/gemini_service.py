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
from gemini_webapi.exceptions import AuthError
from app.config import TEMP_DIR

# Suppress verbose quota logs in terminal safely (guards against windowless PyInstaller NoneType)
try:
    if getattr(sys, "stderr", None) is not None:
        set_log_level("WARNING")
except Exception:
    pass

SESSION_FILE = TEMP_DIR / "gemini_session.json"

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
        self.chat_session = None
        self.conversation_session = None
        self.is_ready = False
        self.has_grounding = False
        self._current_psid: str = ""
        self._current_psidts: str = ""
        self.current_thinking_level: str = "medium"
        self._init_lock = asyncio.Lock()
        self._saved_cookies = self._read_saved_cookies()

    def set_thinking_level(self, level: str):
        """Update active AI thinking level (low, medium, high)."""
        lvl = (level or "medium").strip().lower()
        if lvl in ("low", "medium", "high"):
            self.current_thinking_level = lvl
            print(f"[GeminiSessionService] ⚙️ Đã thiết lập mức độ suy nghĩ AI: {lvl.upper()}")

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

    def _get_model_for_level(self, level: str) -> Optional[Any]:
        """Find the most appropriate registered Gemini model for the requested thinking level."""
        if not self.client or not getattr(self.client, "_model_registry", None):
            return None
        models = self.client.list_models() or []
        available = [m for m in models if getattr(m, "is_available", True)]
        if not available:
            return None

        lvl = (level or "medium").strip().lower()
        if lvl == "high":
            # Prefer Pro model if available for this account
            pro_models = [m for m in available if "pro" in getattr(m, "model_name", "").lower()]
            if pro_models:
                return pro_models[0]
        elif lvl == "low":
            # Prefer flash-lite or fastest flash model
            flash_lite = [m for m in available if "lite" in getattr(m, "model_name", "").lower()]
            if flash_lite:
                return flash_lite[0]
            flash_models = [m for m in available if "flash" in getattr(m, "model_name", "").lower()]
            if flash_models:
                return flash_models[0]

        return None

    def _start_chat_safe(self, preferred_model: Optional[str] = None):
        """Start chat with standard Gemini model (full multimodal vision & spatial reasoning)."""
        if preferred_model and self.client:
            try:
                return self.client.start_chat(model=preferred_model)
            except Exception:
                pass
        try:
            return self.client.start_chat()
        except Exception:
            try:
                return self.client.start_chat(model="gemini-flash")
            except Exception:
                return self.client.start_chat(model="gemini-flash-lite")

    def _sync_cookies_to_disk(self):
        """Persist rotated __Secure-1PSIDTS back to disk so next startup never expires."""
        if not self.client:
            return
        try:
            live_psid = self._current_psid
            live_psidts = self._current_psidts
            if hasattr(self.client, "cookies"):
                c_psid = self.client.cookies.get("__Secure-1PSID")
                c_psidts = self.client.cookies.get("__Secure-1PSIDTS")
                if c_psid:
                    live_psid = c_psid
                if c_psidts:
                    live_psidts = c_psidts
            elif hasattr(self.client, "_live_client") and self.client._live_client:
                c_psidts = self.client._live_client.cookies.get("__Secure-1PSIDTS")
                if c_psidts:
                    live_psidts = c_psidts

            if live_psid:
                self._current_psid = live_psid
                self._current_psidts = live_psidts
                with open(SESSION_FILE, "w") as f:
                    json.dump({"secure_1psid": live_psid, "secure_1psidts": live_psidts}, f)
        except Exception:
            pass

    async def auto_init_from_disk(self):
        """Try to automatically initialize if session was previously saved."""
        cookies = self._read_saved_cookies()
        if cookies:
            psid = cookies.get("secure_1psid", "")
            psidts = cookies.get("secure_1psidts", "")
            if psid:
                # 1. Try with saved cookies
                ok = await self.init_session(psid, psidts)
                # 2. If failed (e.g. psidts expired while app was closed), try with psid alone
                # so gemini_webapi can load rotated cookies from its cache
                if not ok:
                    print("[GeminiSessionService] 🔄 Đang khôi phục session bằng __Secure-1PSID từ cache...")
                    await self.init_session(psid, None)

    async def init_session(
        self,
        secure_1psid: str,
        secure_1psidts: Optional[str] = None
    ) -> bool:
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
                    self.has_grounding = False
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
                self.has_grounding = False

                # Start continuous chat session
                if self.chat_session is None:
                    self.chat_session = self._start_chat_safe()
                    print(f"[GeminiSessionService] Đã khởi tạo 1 phiên trò chuyện liên tục duy nhất (Continuous Chat).")

                # Persist to disk
                self._sync_cookies_to_disk()

                print("[GeminiSessionService] ✅ Kết nối Google Gemini ngầm thành công! (Duy trì 1 cuộc trò chuyện liên tục)")
                return True
            except Exception as e:
                print(f"[GeminiSessionService] ❌ Lỗi kết nối session Gemini: {e}")
                self.is_ready = False
                return False

    async def send_prompt(
        self,
        prompt: str,
        image_path: Optional[Path] = None,
        thinking_level: Optional[str] = None
    ) -> str:
        """
        Send prompt and current screenshot to Gemini in the SAME continuous chat.
        This preserves all conversation history and screen context.
        Directly passes extended_thinking to Gemini when thinking_level is high!
        """
        if not self.is_ready or not self.client:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối."
            )

        if self.chat_session is None:
            self.chat_session = self._start_chat_safe()
            self.has_grounding = False

        files = [str(image_path)] if image_path and image_path.exists() else None

        active_lvl = (thinking_level or self.current_thinking_level or "medium").strip().lower()
        use_extended_thinking = (active_lvl == "high")
        target_model = self._get_model_for_level(active_lvl)
        if target_model and self.chat_session:
            self.chat_session.model = target_model

        try:
            model_info = getattr(target_model, "model_name", "mặc định") if target_model else "mặc định"
            print(f"[GeminiSessionService] Gửi lệnh vào cuộc trò chuyện hiện tại (cid={self.chat_session.cid or 'mới'}, model={model_info}, mức={active_lvl}, extended_thinking={use_extended_thinking})...")
            try:
                output = await self.chat_session.send_message(
                    prompt,
                    files=files,
                    extended_thinking=use_extended_thinking
                )
            except TypeError:
                # If library method doesn't take extended_thinking kwargs
                output = await self.chat_session.send_message(prompt, files=files)

            self.has_grounding = True
            self._sync_cookies_to_disk()

            response_text = output.text if hasattr(output, "text") else str(output)
            # Remove any citation badges e.g. [cite: 1], [cite: 1, 2], [cite: ...]
            response_text = re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
            return response_text
        except Exception as e:
            err_str = str(e).lower()
            if isinstance(e, AuthError) or "unauthenticated" in err_str or "401" in err_str:
                print(f"[GeminiSessionService] ⚠️ Session Google hết hạn hoặc chưa xác thực: {e}")
                self.is_ready = False
                self.client = None
                self.chat_session = None
                self.has_grounding = False
            elif "exhausted" in err_str or "too long" in err_str or "context window" in err_str:
                print(f"[GeminiSessionService] Context bị quá tải ({e}), tự động làm mới chat session...")
                self.reset_chat()
                try:
                    output = await self.chat_session.send_message(
                        prompt,
                        files=files,
                        extended_thinking=use_extended_thinking
                    )
                except TypeError:
                    output = await self.chat_session.send_message(prompt, files=files)
                self.has_grounding = True
                self._sync_cookies_to_disk()
                response_text = output.text if hasattr(output, "text") else str(output)
                return re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
            raise e

    def reset_chat(self):
        """Reset to a fresh chat session only when explicitly requested or overloaded."""
        if self.client:
            self.chat_session = self._start_chat_safe()
            self.has_grounding = False
            print("[GeminiSessionService] Đã tạo phiên chat mới thành công.")

    async def send_chat_message(self, message: str, thinking_level: Optional[str] = None) -> str:
        """
        Send a natural conversational message to Gemini in Chat Mode.
        Maintains conversational context across turns with zero screen clutter.
        Directly passes extended_thinking to Gemini when thinking_level is high!
        """
        if not self.is_ready or not self.client:
            raise RuntimeError(
                "Chưa kết nối được với session Google Gemini. "
                "Vui lòng nhấn nút 'Đăng nhập Google' trên cửa sổ Spotlight (F7) để kết nối."
            )

        if self.conversation_session is None:
            self.conversation_session = self._start_chat_safe()

        active_lvl = (thinking_level or self.current_thinking_level or "medium").strip().lower()
        use_extended_thinking = (active_lvl == "high")
        target_model = self._get_model_for_level(active_lvl)
        if target_model and self.conversation_session:
            self.conversation_session.model = target_model

        try:
            model_info = getattr(target_model, "model_name", "mặc định") if target_model else "mặc định"
            print(f"[GeminiSessionService] [Chat Mode] Gửi tin nhắn (model={model_info}, mức={active_lvl}, extended_thinking={use_extended_thinking}): \"{message[:60]}...\"")
            try:
                output = await self.conversation_session.send_message(
                    message,
                    extended_thinking=use_extended_thinking
                )
            except TypeError:
                output = await self.conversation_session.send_message(message)

            self._sync_cookies_to_disk()
            response_text = output.text if hasattr(output, "text") else str(output)
            # Remove any citation badges
            response_text = re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
            return response_text.strip()
        except Exception as e:
            err_str = str(e).lower()
            if isinstance(e, AuthError) or "unauthenticated" in err_str or "401" in err_str:
                self.is_ready = False
                self.client = None
                self.conversation_session = None
            elif "exhausted" in err_str or "too long" in err_str or "context window" in err_str:
                self.conversation_session = self._start_chat_safe()
                try:
                    output = await self.conversation_session.send_message(
                        message,
                        extended_thinking=use_extended_thinking
                    )
                except TypeError:
                    output = await self.conversation_session.send_message(message)
                response_text = output.text if hasattr(output, "text") else str(output)
                return re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE).strip()
            raise e

    def reset_conversation(self):
        """Reset conversational chat session."""
        if self.client:
            self.conversation_session = self._start_chat_safe()
            print("[GeminiSessionService] Đã làm mới phiên trò chuyện (Chat Mode).")

gemini_service = GeminiSessionService()
