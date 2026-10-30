"""
Gemini Session Service for Luga Assist.
Leverages the user's existing Google Gemini web session via session cookies (__Secure-1PSID).
Runs 100% in the background with ZERO browser tabs needed.
Maintains continuous conversation context across all user requests.
Only creates a new chat if explicitly requested or if context is truly overloaded.
"""
import shutil
from pathlib import Path
import json
import re
import asyncio
from typing import Optional, Dict, Any

from gemini_webapi import GeminiClient, set_log_level
from gemini_webapi.exceptions import AuthError
from app.config import USER_DATA_DIR, TEMP_DIR

# Suppress verbose quota logs in terminal safely (guards against windowless PyInstaller NoneType)
try:
    if getattr(sys, "stderr", None) is not None:
        set_log_level("WARNING")
except Exception:
    pass

# Session file stored permanently in USER_DATA_DIR (never in %TEMP%)
SESSION_FILE = USER_DATA_DIR / "gemini_session.json"

# Auto-migrate legacy session file if present in TEMP_DIR
legacy_session = TEMP_DIR / "gemini_session.json"
if legacy_session.exists() and not SESSION_FILE.exists():
    try:
        shutil.copy2(legacy_session, SESSION_FILE)
    except Exception:
        pass

class GeminiSessionService:
    def __init__(self):
        self.client: Optional[GeminiClient] = None
        self.chat_session = None
        self.conversation_session = None
        self.is_ready = False
        self.is_restoring = False
        self.has_grounding = False
        self._current_psid: str = ""
        self._current_psidts: str = ""
        self._current_all_cookies: Dict[str, str] = {}
        self.current_thinking_level: str = "medium"
        self._init_lock = asyncio.Lock()
        self._saved_cookies = self._read_saved_cookies()

    def set_thinking_level(self, level: str):
        """Update active AI thinking level (low, medium, high)."""
        lvl = (level or "medium").strip().lower()
        if lvl in ("low", "medium", "high"):
            self.current_thinking_level = lvl
            print(f"[GeminiSessionService] ⚙️ Đã thiết lập mức độ suy nghĩ AI: {lvl.upper()}")

    def _read_saved_cookies(self) -> Optional[Dict[str, Any]]:
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("secure_1psid") or data.get("all_cookies"):
                        all_c = data.get("all_cookies", {})
                        if all_c:
                            self._current_all_cookies.update(all_c)
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
        """Persist rotated __Secure-1PSIDTS and all Google cookies back to disk so next startup never expires."""
        if not self.client:
            return
        try:
            live_psid = self._current_psid
            live_psidts = self._current_psidts
            all_cookies = dict(self._current_all_cookies)

            if hasattr(self.client, "cookies") and self.client.cookies:
                try:
                    for c in self.client.cookies.jar:
                        all_cookies[c.name] = c.value
                    c_psid = self.client.cookies.get("__Secure-1PSID")
                    c_psidts = self.client.cookies.get("__Secure-1PSIDTS")
                    if c_psid:
                        live_psid = c_psid
                    if c_psidts:
                        live_psidts = c_psidts
                except Exception:
                    pass

            if hasattr(self.client, "_live_client") and self.client._live_client:
                try:
                    lc = getattr(self.client._live_client, "cookies", None)
                    if lc:
                        for c in lc.jar:
                            all_cookies[c.name] = c.value
                        c_psidts = lc.get("__Secure-1PSIDTS")
                        if c_psidts:
                            live_psidts = c_psidts
                except Exception:
                    pass

            if live_psid:
                self._current_psid = live_psid
                self._current_psidts = live_psidts
                self._current_all_cookies = all_cookies
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                save_data = {
                    "secure_1psid": live_psid,
                    "secure_1psidts": live_psidts,
                    "all_cookies": all_cookies,
                    "updated_at": time.time()
                }
                with open(SESSION_FILE, "w") as f:
                    json.dump(save_data, f)
        except Exception as e:
            print(f"[GeminiSessionService] Warning syncing session to disk: {e}")

    async def _cookie_sync_loop(self):
        """Periodically sync rotated cookies to disk so next startup has latest token."""
        try:
            while self.is_ready:
                await asyncio.sleep(20)
                self._sync_cookies_to_disk()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _rotate_cookies_direct(self, psid: str, all_cookies: Dict[str, str]) -> Optional[str]:
        """
        Attempts to rotate and fetch a fresh __Secure-1PSIDTS directly from Google
        using the full account cookie set via curl_cffi AsyncSession.
        """
        try:
            from curl_cffi.requests import AsyncSession
            from gemini_webapi.constants import Endpoint, Headers, BROWSER_TYPE

            async with AsyncSession(impersonate=BROWSER_TYPE, allow_redirects=True) as session:
                for k, v in all_cookies.items():
                    if v:
                        session.cookies.set(k, v, domain=".google.com", secure=True)
                if psid:
                    session.cookies.set("__Secure-1PSID", psid, domain=".google.com", secure=True)

                resp = await session.post(
                    Endpoint.ROTATE_COOKIES,
                    headers=Headers.ROTATE_COOKIES.value,
                    data='[000,"-0000000000000000000"]',
                    timeout=10.0
                )
                if resp.status_code == 200:
                    new_ts = session.cookies.get("__Secure-1PSIDTS")
                    if new_ts:
                        for c in session.cookies.jar:
                            all_cookies[c.name] = c.value
                        return new_ts
        except Exception as e:
            print(f"[GeminiSessionService] Direct RotateCookies notice: {e}")
        return None

    async def auto_init_from_disk(self) -> bool:
        """Try to automatically initialize and restore session with zero user friction."""
        self.is_restoring = True
        try:
            cookies_data = self._read_saved_cookies()
            psid = ""
            psidts = ""
            all_cookies = {}
            if cookies_data:
                psid = cookies_data.get("secure_1psid", "")
                psidts = cookies_data.get("secure_1psidts", "")
                all_cookies = cookies_data.get("all_cookies", {})
                if all_cookies:
                    self._current_all_cookies.update(all_cookies)

            # Tier 1: Try with saved cookies directly (fastest path, works if reboot was quick)
            if psid and psidts:
                print("[GeminiSessionService] 🔄 [Tier 1] Đang thử kết nối session Google Gemini từ cookie lưu sẵn...")
                try:
                    ok = await self.init_session(psid, psidts, all_cookies=all_cookies)
                    if ok:
                        return True
                except Exception as e:
                    print(f"[GeminiSessionService] Tier 1 notice: {e}")

            # Tier 2: If psidts expired on reboot, rotate directly via RotateCookies endpoint
            if all_cookies and (psid or all_cookies.get("__Secure-1PSID")):
                target_psid = psid or all_cookies.get("__Secure-1PSID", "")
                print("[GeminiSessionService] 🔄 [Tier 2] Đang tự động làm mới token qua Google RotateCookies...")
                new_psidts = await self._rotate_cookies_direct(target_psid, all_cookies)
                if new_psidts:
                    ok = await self.init_session(target_psid, new_psidts, all_cookies=all_cookies)
                    if ok:
                        print("[GeminiSessionService] ✅ Làm mới token thành công qua RotateCookies!")
                        return True

            # Tier 3: Silent off-screen Chromium recovery (100% reliable, runs off-screen, zero user disruption)
            try:
                from app.google_auth import google_auth_manager
                print("[GeminiSessionService] 🔄 [Tier 3] Đang tự động làm mới session ngầm qua Google Chromium profile...")
                ok = await google_auth_manager.silent_refresh_cookies(old_psidts=psidts)
                if ok:
                    return True
            except Exception as e:
                print(f"[GeminiSessionService] Tier 3 notice: {e}")

            return False
        finally:
            self.is_restoring = False

    async def init_session(
        self,
        secure_1psid: str,
        secure_1psidts: Optional[str] = None,
        all_cookies: Optional[Dict[str, str]] = None
    ) -> bool:
        """Initialize or keep active background Gemini client using cookies."""
        async with self._init_lock:
            cleaned_psid = (secure_1psid or "").strip()
            cleaned_psidts = (secure_1psidts or "").strip() if secure_1psidts else ""

            if not cleaned_psid:
                return False

            if all_cookies:
                self._current_all_cookies.update(all_cookies)

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

                # Populate client cookies with full set if available
                if self._current_all_cookies:
                    for k, v in self._current_all_cookies.items():
                        if v and k not in ("__Secure-1PSID", "__Secure-1PSIDTS"):
                            try:
                                self.client.cookies.set(k, v, domain=".google.com", secure=True)
                                if k in ("__Secure-1PSIDCC", "SID", "HSID", "SSID", "SAPISID", "APISID"):
                                    self.client.cookies.set(k, v, domain=".googleapis.com", secure=True)
                            except Exception:
                                pass

                await self.client.init(timeout=25)

                # Ensure live HTTP session also has cross-domain credentials for content-push.googleapis.com
                if hasattr(self.client, "client") and self.client.client:
                    for k in ("__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-1PSIDCC", "SID", "HSID", "SSID", "SAPISID", "APISID"):
                        val = self._current_all_cookies.get(k) or (cleaned_psid if k == "__Secure-1PSID" else (cleaned_psidts if k == "__Secure-1PSIDTS" else None))
                        if val:
                            try:
                                self.client.client.cookies.set(k, val, domain=".googleapis.com", secure=True)
                            except Exception:
                                pass
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

                # Start periodic background cookie sync
                if not hasattr(self, "_sync_task") or self._sync_task is None or self._sync_task.done():
                    self._sync_task = asyncio.create_task(self._cookie_sync_loop())

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
            if "tos_pending" in err_str or "terms of service" in err_str:
                msg = (
                    "Tài khoản Google cần chấp nhận Điều khoản sử dụng mới của Gemini (Terms of Service). "
                    "Vui lòng truy cập https://gemini.google.com và bấm 'Đồng ý' (Accept / I agree) để kích hoạt tài khoản."
                )
                print(f"[GeminiSessionService] ⚠️ {msg}")
                try:
                    import webbrowser
                    webbrowser.open("https://gemini.google.com")
                except Exception:
                    pass
                raise RuntimeError(msg) from e
            elif isinstance(e, AuthError) or "unauthenticated" in err_str or "401" in err_str:
                print(f"[GeminiSessionService] ⚠️ Session Google hết hạn hoặc chưa xác thực: {e}. Đang tự động khôi phục ngầm...")
                recovered = await self.auto_init_from_disk()
                if recovered and self.chat_session:
                    print("[GeminiSessionService] ✅ Khôi phục session ngầm thành công, đang gửi lại câu lệnh...")
                    try:
                        output = await self.chat_session.send_message(
                            prompt,
                            files=files,
                            extended_thinking=use_extended_thinking
                        )
                        self.has_grounding = True
                        self._sync_cookies_to_disk()
                        response_text = output.text if hasattr(output, "text") else str(output)
                        return re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE)
                    except Exception as retry_e:
                        print(f"[GeminiSessionService] Lỗi khi gửi lại sau phục hồi: {retry_e}")
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

    async def send_prompt_with_screenshot(
        self,
        prompt: str,
        image_path: Optional[Path] = None,
        screenshot_b64: Optional[str] = None,
        thinking_level: Optional[str] = None
    ) -> str:
        """Alias for send_prompt, accepting image_path or screenshot."""
        return await self.send_prompt(
            prompt=prompt,
            image_path=image_path,
            thinking_level=thinking_level
        )

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
            if "tos_pending" in err_str or "terms of service" in err_str:
                msg = (
                    "Tài khoản Google cần chấp nhận Điều khoản sử dụng mới của Gemini (Terms of Service). "
                    "Vui lòng truy cập https://gemini.google.com và bấm 'Đồng ý' (Accept / I agree) để kích hoạt tài khoản."
                )
                print(f"[GeminiSessionService] ⚠️ {msg}")
                try:
                    import webbrowser
                    webbrowser.open("https://gemini.google.com")
                except Exception:
                    pass
                raise RuntimeError(msg) from e
            elif isinstance(e, AuthError) or "unauthenticated" in err_str or "401" in err_str:
                print(f"[GeminiSessionService] ⚠️ Session Google hết hạn trong Chat Mode: {e}. Đang tự động khôi phục ngầm...")
                recovered = await self.auto_init_from_disk()
                if recovered and self.conversation_session:
                    print("[GeminiSessionService] ✅ Khôi phục session Chat Mode thành công, đang gửi lại...")
                    try:
                        output = await self.conversation_session.send_message(
                            message,
                            extended_thinking=use_extended_thinking
                        )
                        self._sync_cookies_to_disk()
                        response_text = output.text if hasattr(output, "text") else str(output)
                        return re.sub(r"\[\s*cite[^\]]*\]", "", response_text, flags=re.IGNORECASE).strip()
                    except Exception as retry_e:
                        print(f"[GeminiSessionService] Lỗi khi gửi lại Chat Mode: {retry_e}")
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
