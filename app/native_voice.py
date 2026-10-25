"""
Native Global Voice & Hotkey Assistant for Luga Assist.
Allows completely hands-free and browser-free operation across the entire OS.
Listens globally for hotkey (F8 or Ctrl+Space) and records Vietnamese voice natively.
Zero browser windows needed! The screen remains 100% unobstructed.
"""
import sys
import os
import time
import threading
import queue
import subprocess
from pathlib import Path
from typing import Optional, Callable

import audioop
import concurrent.futures
import re
import sounddevice as sd
import speech_recognition as sr
from pynput import keyboard
from app.sound_effects import sound_manager
from app.config import VOICE_RECOGNITION_LANG
from app.audio_manager import audio_manager

VI_DIACRITICS = set(
    "àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    "ÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
)

COMMON_EN_WORDS = {
    "a", "about", "action", "after", "all", "also", "an", "and", "any", "app",
    "application", "are", "as", "at", "audio", "back", "be", "before", "browser",
    "button", "by", "can", "cancel", "check", "chrome", "click", "close", "compose",
    "computer", "confirm", "copy", "cut", "delete", "desktop", "discard", "display",
    "document", "done", "down", "double", "download", "drag", "edit", "email",
    "enter", "escape", "exit", "file", "find", "first", "folder", "for", "from",
    "get", "go", "google", "help", "here", "home", "how", "in", "input", "into",
    "is", "it", "item", "jump", "key", "keyboard", "last", "launch", "left",
    "link", "list", "lock", "log", "login", "look", "mac", "mail", "make", "menu",
    "message", "microsoft", "minimize", "mouse", "move", "music", "mute", "new",
    "next", "no", "not", "now", "off", "ok", "on", "open", "or", "outlook", "page",
    "paste", "pause", "play", "please", "press", "prev", "previous", "print",
    "put", "read", "refresh", "reload", "restart", "return", "right", "run",
    "safari", "save", "say", "screen", "screenshot", "scroll", "search", "select",
    "send", "setting", "settings", "shift", "show", "shutdown", "sleep", "sound",
    "speak", "spotify", "start", "stop", "subject", "system", "tab", "take",
    "task", "test", "text", "the", "then", "this", "to", "turn", "type", "undo",
    "unmute", "up", "url", "volume", "wait", "web", "website", "what", "where",
    "which", "window", "windows", "with", "word", "write", "yes", "you", "youtube"
}

def normalize_spoken_terms(text: str) -> str:
    """
    Intelligently normalize spoken Vietnamese loanwords and tech terms
    (e.g., 'chấm loga' -> '.luga', 'tiêu đề taxi/tết' -> 'tiêu đề test', 'cơ rôm' -> 'Chrome').
    """
    if not text:
        return text

    # Common email domain and recipient corrections
    text = re.sub(r'(?i)\bphương\s*mai\s*chấm\s*loga\b', 'phuongma.luga', text)
    text = re.sub(r'(?i)\bphương\s*mai\s*chấm\s*luga\b', 'phuongma.luga', text)
    text = re.sub(r'(?i)\bchấm\s*loga\b', '.luga', text)
    text = re.sub(r'(?i)\bchấm\s*duca\b', '.luga', text)
    text = re.sub(r'(?i)\bchấm\s*luga\b', '.luga', text)

    # Common misinterpretations of 'test' in tech context
    text = re.sub(r'(?i)\btiêu\s*đề\s+(taxi|tết|tét|tab)\b', 'tiêu đề test', text)
    text = re.sub(r'(?i)\bnội\s*dung\s+(cũng\s+là\s+)?(taxi|tết|tét|tab)\b', r'nội dung \1test', text)

    # Common tech & app spoken loanwords in Vietnamese
    text = re.sub(r'(?i)\bmáy\s+mát\b', 'máy Mac', text)
    text = re.sub(r'(?i)\b(c[ơờ]\s*rôm|crôm)\b', 'Chrome', text)
    text = re.sub(r'(?i)\bkhôm\b', 'Chrome', text)
    text = re.sub(r'(?i)\bgúc\s*gồ\b', 'Google', text)
    text = re.sub(r'(?i)\bgu\s*gồ\b', 'Google', text)
    text = re.sub(r'(?i)\bxa\s*fa\s*ri\b', 'Safari', text)
    text = re.sub(r'(?i)\bbóp\s*phi\b', 'Spotify', text)
    text = re.sub(r'(?i)\bspốt\s*ti\s*phai\b', 'Spotify', text)
    text = re.sub(r'(?i)\bốt\s*lúc\b', 'Outlook', text)
    text = re.sub(r'(?i)\bót\s*lúc\b', 'Outlook', text)
    text = re.sub(r'(?i)\bát\s*láp\b', 'Outlook', text)
    text = re.sub(r'(?i)\byou\s*tube\b', 'YouTube', text)
    text = re.sub(r'(?i)\byu\s*túp\b', 'YouTube', text)

    return text.strip()

def count_vietnamese_diacritics(text: str) -> int:
    return sum(1 for c in text if c in VI_DIACRITICS)

def evaluate_english_word_ratio(text: str) -> float:
    words = [w.strip('.,!?:;\"\'()[]{}').lower() for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return 0.0
    matches = sum(1 for w in words if w in COMMON_EN_WORDS)
    return matches / len(words)

def select_best_transcript(
    vi_res: Optional[tuple[str, float]], 
    en_res: Optional[tuple[str, float]]
) -> Optional[str]:
    """
    Intelligently select between Vietnamese and English speech recognition hypotheses.
    Handles:
    - Pure English commands ('mute system audio', 'volume up', 'open Spotify')
    - Pure Vietnamese commands ('cho máy tính ngủ', 'tắt tiếng hệ thống')
    - Mixed code-switching commands
    """
    if not vi_res and not en_res:
        return None
    if not vi_res:
        return en_res[0]
    if not en_res:
        return vi_res[0]

    vi_text, vi_conf = vi_res
    en_text, en_conf = en_res

    vi_diacritics = count_vietnamese_diacritics(vi_text)
    en_ratio = evaluate_english_word_ratio(en_text)

    # 1. Clear English commands:
    # If English confidence is solid (>= 0.70) and all or most words are common English words:
    if en_conf >= 0.70 and en_ratio >= 0.60:
        # Check if VI has zero diacritics (e.g. 'Musical Open Google Chrome', 'Doraemon')
        # OR EN is 100% common English command words (like 'mute sound', 'volume up')
        # OR EN confidence is high and VI has minimal accidental diacritics
        if vi_diacritics == 0 or en_ratio == 1.0 or (en_conf >= 0.85 and vi_diacritics <= 2):
            return en_text

    # 2. Clear Vietnamese speech:
    # If VI has Vietnamese diacritics and en_conf is low or en_ratio is low:
    if vi_diacritics >= 2 and (en_conf < 0.70 or en_ratio < 0.50):
        return vi_text

    # 3. If VI has higher confidence and has diacritics:
    if vi_conf >= en_conf and vi_diacritics > 0:
        return vi_text

    # 4. Fallback based on English ratio and confidence
    if en_ratio >= 0.5 and en_conf >= vi_conf:
        return en_text
    return vi_text

    return vi_text


class NativeVoiceListener:
    def __init__(
        self,
        on_command_callback: Optional[Callable[[str], None]] = None,
        on_mode_toggle_callback: Optional[Callable[[], None]] = None,
        on_spotlight_toggle_callback: Optional[Callable[[], None]] = None,
        on_cancel_callback: Optional[Callable[[], None]] = None,
        on_status_callback: Optional[Callable[[str, str], None]] = None,
    ):
        self.on_command = on_command_callback
        self.on_mode_toggle = on_mode_toggle_callback
        self.on_spotlight_toggle = on_spotlight_toggle_callback
        self.on_cancel = on_cancel_callback
        self.on_status = on_status_callback
        self.recognizer = sr.Recognizer()
        self.is_recording = False
        self.is_processing = False
        self._stop_requested = False
        self._discard_recording = False
        self._last_trigger_time = 0.0
        self._recording_start_time = 0.0
        self.sample_rate = 16000
        self.channels = 1
        self._hotkey_listener: Optional[keyboard.Listener] = None
        self._supervisor_thread: Optional[threading.Thread] = None
        self._stop_hotkeys = False
        self._hotkeys_active = False
        self._has_announced_hotkeys = False
        self._current_keys = set()

    def cancel_all(self):
        """Immediately halt recording, speech, and executing pipeline."""
        print("\n[NativeVoice] ⏹️ Kích hoạt ngắt khẩn cấp (Emergency Stop / Cancel)...")
        self._discard_recording = True
        self._stop_requested = True
        self.is_recording = False
        self.is_processing = False
        sound_manager.stop_pulsing()
        sound_manager.play_error()
        self._update_status("cancelled", "⏹️ Đã ngắt tác vụ đang xử lý!")
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception as e:
                print(f"[NativeVoice] Lỗi trong on_cancel: {e}")


    def _update_status(self, state: str, text_or_msg: str = ""):
        """Notify status listener (Spotlight HUD, etc.) of voice recording progression."""
        if self.on_status:
            try:
                self.on_status(state, text_or_msg)
            except Exception:
                pass

    def listen_and_transcribe(self) -> Optional[str]:
        """
        Record audio from system microphone using the active OS microphone directly.
        Stops automatically when user stops speaking (natural silence pause), or when F8 is pressed again.
        """
        self.is_recording = True
        self._stop_requested = False
        self._discard_recording = False
        self._recording_start_time = time.time()
        self._update_status("recording", "🎙️ Đang lắng nghe... Hãy nói lệnh vào Micro")
        print("\n" + "=" * 60)
        print("🎙️ ĐANG LẮNG NGHE BẠN NÓI... (Nói lệnh và dừng lại khi nói xong)")
        print("=" * 60)

        chunk_duration = 0.08  # 80ms chunks for rapid response
        chunk_samples = int(self.sample_rate * chunk_duration)
        recorded_frames = []

        speech_detected = False
        speech_duration = 0.0
        silence_start_time = None
        silence_duration_to_stop = 0.75  # 0.75s natural pause threshold
        max_duration = 4.5  # Max 4.5s per command (rapid and responsive)
        start_time = time.time()

        ambient_samples = 0
        ambient_rms_sum = 0
        speech_threshold = 350
        silence_threshold = 200

        dev_idx, dev_name = audio_manager.get_active_device_index()

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=dev_idx,
                blocksize=chunk_samples,
            ) as stream:
                while self.is_recording and not self._stop_requested and not self._discard_recording:
                    data, overflowed = stream.read(chunk_samples)
                    raw_bytes = bytes(data)
                    recorded_frames.append(raw_bytes)

                    try:
                        rms = audioop.rms(raw_bytes, 2)
                    except Exception:
                        rms = 0

                    # Dynamic baseline adaptation during first 3 chunks (first ~240ms)
                    if ambient_samples < 3:
                        ambient_rms_sum += rms
                        ambient_samples += 1
                        baseline = ambient_rms_sum // ambient_samples
                        speech_threshold = max(350, int(baseline * 1.55))
                        silence_threshold = max(180, int(baseline * 1.15))

                    if rms >= speech_threshold:
                        speech_detected = True
                        speech_duration += chunk_duration
                        silence_start_time = None
                    elif speech_detected and speech_duration >= 0.25:
                        if rms <= silence_threshold:
                            if silence_start_time is None:
                                silence_start_time = time.time()
                            elif time.time() - silence_start_time >= silence_duration_to_stop:
                                print("[NativeVoice] 🔇 Đã phát hiện kết thúc câu nói.")
                                break
                        else:
                            silence_start_time = None

                    if time.time() - start_time > max_duration:
                        break
        except Exception as e:
            print(f"[NativeVoice] Lỗi khi thu âm từ micro: {e}")
            self._update_status("error", f"Lỗi micro: {e}")
            sound_manager.play_error()
            self.is_recording = False
            return None

        self.is_recording = False
        if self._discard_recording:
            print("[NativeVoice] ⏹️ Đã hủy bản ghi âm theo yêu cầu.")
            self._discard_recording = False
            return None

        total_audio_duration = len(recorded_frames) * chunk_duration
        if not recorded_frames or total_audio_duration < 0.35:
            print("[NativeVoice] Không phát hiện thấy âm thanh ghi lại.")
            self._update_status("error", "⚠️ Không phát hiện âm thanh.")
            sound_manager.play_error()
            return None

        sound_manager.start_pulsing()
        self._update_status("transcribing", "⏳ Đang nhận diện câu lệnh...")

        audio_bytes = b"".join(recorded_frames)

        # Automatic Gain Control (AGC) - amplify quiet mic signal so Google STT acoustic model hears clearly
        try:
            peak = audioop.max(audio_bytes, 2)
            if peak == 0:
                print("\n[NativeVoice] ⚠️ Micro trả về tín hiệu bằng 0 (Hoàn toàn im lặng).")
                print("[NativeVoice] 👉 Vui lòng kiểm tra Microphone trong Windows Settings (Settings -> Privacy & Security -> Microphone)!")
                self._update_status("error", "⚠️ Micro không nhận được tín hiệu (vui lòng bật mic trong Windows).")
                sound_manager.play_error()
                return None
            elif 0 < peak < 22000:
                gain = min(7.0, 26000.0 / peak)
                audio_bytes = audioop.mul(audio_bytes, 2, gain)
        except Exception:
            pass

        audio = sr.AudioData(audio_bytes, self.sample_rate, 2)

        try:
            import tempfile
            wav_path = Path(tempfile.gettempdir()) / "last_voice_command.wav"
            with open(wav_path, "wb") as f:
                f.write(audio.get_wav_data())
        except Exception:
            pass

        def _recognize_lang(lang: str) -> Optional[tuple[str, float]]:
            for attempt in range(2):
                try:
                    res = self.recognizer.recognize_google(audio, language=lang, with_confidence=True)
                    if isinstance(res, tuple):
                        return (res[0].strip(), float(res[1]))
                    return (str(res).strip(), 0.8)
                except sr.UnknownValueError:
                    try:
                        res = self.recognizer.recognize_google(audio, language=lang)
                        return (str(res).strip(), 0.75)
                    except Exception:
                        return None
                except (sr.RequestError, OSError, Exception) as e:
                    if attempt == 0:
                        time.sleep(0.25)
                        continue
                    print(f"[NativeVoice] ⚠️ Lỗi STT ({lang}): {e}")
                    return None
            return None

        mode = VOICE_RECOGNITION_LANG.lower().strip()
        best_text = None

        if mode == "vi-vn":
            print("[NativeVoice] ⏳ Đang nhận diện tiếng Việt qua Google STT...")
            res = _recognize_lang("vi-VN")
            if res:
                best_text = res[0]
        elif mode == "en-us":
            print("[NativeVoice] ⏳ Đang nhận diện tiếng Anh qua Google STT...")
            res = _recognize_lang("en-US")
            if res:
                best_text = res[0]
        else:
            print("[NativeVoice] ⏳ Đang nhận diện song ngữ (Tiếng Việt & English concurrently)...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                fut_vi = executor.submit(_recognize_lang, "vi-VN")
                fut_en = executor.submit(_recognize_lang, "en-US")
                vi_res = fut_vi.result()
                en_res = fut_en.result()

            best_text = select_best_transcript(vi_res, en_res)

        if not best_text:
            print("[NativeVoice] Chưa nghe rõ câu lệnh, vui lòng thử lại.")
            self._update_status("error", "⚠️ Chưa nghe rõ câu lệnh, vui lòng nói lại.")
            sound_manager.play_error()
            return None

        best_text = normalize_spoken_terms(best_text)
        print(f"\n[NativeVoice] 🗣️ Nhận diện thành công: \"{best_text}\"")
        self._update_status("transcribed", best_text)
        return best_text

    def trigger_voice_flow(self):
        """Trigger the complete voice-to-action flow without opening any browser."""
        now = time.time()
        # Debounce: ignore repeated keypresses within 0.3s
        if now - self._last_trigger_time < 0.3:
            return
        self._last_trigger_time = now

        # If already recording, allow manual stop via keypress or button
        if self.is_recording:
            if now - self._recording_start_time > 0.35:
                print("[NativeVoice] ⏹️ Nhận lệnh dừng ghi âm từ phím nóng.")
                self._stop_requested = True
            return

        if self.is_processing:
            print("[NativeVoice] ⏹️ Đang xử lý tác vụ, nhấn phím nóng để ngắt ngay lập tức (Cancel)!")
            self.cancel_all()
            return

        self.is_processing = True
        # Play activation chime IMMEDIATELY at keypress
        sound_manager.play_start()

        def _worker():
            try:
                # 0.35s pause allows activation chime sound wave to finish ringing completely
                # before opening the microphone stream, preventing chime noise pollution
                time.sleep(0.35)
                cmd_text = self.listen_and_transcribe()
                if cmd_text and self.on_command:
                    self.on_command(cmd_text)
            finally:
                self.is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    def _start_listener_internal(self) -> bool:
        """Create and start a new pynput keyboard.Listener instance."""
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None

        def _is_f8(k) -> bool:
            if k == keyboard.Key.f8:
                return True
            if hasattr(keyboard.Key, "media_play_pause") and k == keyboard.Key.media_play_pause:
                return True
            vk = getattr(k, "vk", getattr(getattr(k, "value", None), "vk", None))
            if vk in (100, 119):
                return True
            s = str(k).lower()
            return "f8" in s or s in ("<100>", "<119>", "'<100>'", "'<119>'")

        def _is_f7(k) -> bool:
            if k == keyboard.Key.f7:
                return True
            if hasattr(keyboard.Key, "media_previous") and k == keyboard.Key.media_previous:
                return True
            vk = getattr(k, "vk", getattr(getattr(k, "value", None), "vk", None))
            if vk in (98, 118):
                return True
            s = str(k).lower()
            return "f7" in s or s in ("<98>", "<118>", "'<98>'", "'<118>'")

        def _is_f9(k) -> bool:
            if k == keyboard.Key.f9:
                return True
            if hasattr(keyboard.Key, "media_next") and k == keyboard.Key.media_next:
                return True
            vk = getattr(k, "vk", getattr(getattr(k, "value", None), "vk", None))
            if vk in (101, 120):
                return True
            s = str(k).lower()
            return "f9" in s or s in ("<101>", "<120>", "'<101>'", "'<120>'")

        def _is_f10(k) -> bool:
            if k == keyboard.Key.f10:
                return True
            if hasattr(keyboard.Key, "media_volume_mute") and k == keyboard.Key.media_volume_mute:
                return True
            vk = getattr(k, "vk", getattr(getattr(k, "value", None), "vk", None))
            if vk in (109, 121):
                return True
            s = str(k).lower()
            return "f10" in s or s in ("<109>", "<121>", "'<109>'", "'<121>'")

        def _is_modifier_pressed(mod_name: str) -> bool:
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    vk_map = {
                        "ctrl": 0x11,   # VK_CONTROL
                        "alt": 0x12,    # VK_MENU
                        "shift": 0x10,  # VK_SHIFT
                        "win": 0x5B,    # VK_LWIN
                    }
                    vk = vk_map.get(mod_name)
                    if vk:
                        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
                except Exception:
                    pass
            return False

        def _has_mod(mod_name: str) -> bool:
            return (mod_name in self._current_keys) or _is_modifier_pressed(mod_name)

        def on_press(key):
            try:
                # 1. Emergency Cancel (F10 ONLY)
                if _is_f10(key):
                    print("\n[Global Hotkey] Đã kích hoạt F10: NGẮT TÁC VỤ KHẨN CẤP (Emergency Cancel)!")
                    self.cancel_all()
                    return

                # 2. Spotlight Floating Chat HUD (F7 ONLY)
                if _is_f7(key):
                    print("\n[Global Hotkey] Đã kích hoạt F7: Bật/Tắt Cửa sổ Chat Nổi (Spotlight)!")
                    if self.on_spotlight_toggle:
                        self.on_spotlight_toggle()
                    return

                # 3. Direct Microphone Voice Trigger (F8 ONLY)
                if _is_f8(key):
                    print("\n[Global Hotkey] Đã kích hoạt F8: Lắng nghe giọng nói qua Micro!")
                    self.trigger_voice_flow()
                    return

                # 4. Toggle Mode: OS Control <-> AI Chat (F9 ONLY)
                if _is_f9(key):
                    print("\n[Global Hotkey] Đã kích hoạt F9: Chuyển đổi chế độ (Điều khiển OS <-> Chat AI)!")
                    if self.on_mode_toggle:
                        self.on_mode_toggle()
                    return

            except Exception:
                pass

        def on_release(key):
            pass

        try:
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            time.sleep(0.15)
            if listener.is_alive():
                self._hotkey_listener = listener
                return True
            else:
                return False
        except Exception as e:
            print(f"[Global Hotkeys] ⚠️ Lỗi khởi động listener: {e}")
            return False

    def _hotkey_supervisor_loop(self):
        """
        Background watchdog thread that continuously ensures global hotkeys are active on Windows.
        Automatically starts listener and restarts if disconnected.
        """
        while not self._stop_hotkeys:
            is_alive = (self._hotkey_listener is not None and self._hotkey_listener.is_alive())

            if not is_alive:
                self._hotkeys_active = False
                success = self._start_listener_internal()
                if success:
                    self._hotkeys_active = True
                    if not self._has_announced_hotkeys:
                        self._has_announced_hotkeys = True
                        print("\n" + "=" * 65)
                        print("🎙️ LUGA ASSIST - HỆ THỐNG PHÍM TẮT TOÀN CẦU (F7 - F10)")
                        print("👉 F7  : Bật / Tắt Cửa sổ Chat Nổi (Spotlight)")
                        print("👉 F8  : Bật Micro Lắng nghe Giọng nói (Push-to-Talk)")
                        print("👉 F9  : Chuyển đổi Chế độ (Điều khiển OS <-> Chat AI)")
                        print("👉 F10 : Ngắt Khẩn Cấp / Hủy lệnh ngay lập tức")
                        print("=" * 65 + "\n")
                        try:
                            from app.system_ui import show_desktop_notification
                            show_desktop_notification("Luga Assist", "✅ Phím tắt F7-F10 đã sẵn sàng! F7: Chat, F8: Nói, F9: Chế độ, F10: Ngắt.")
                        except Exception:
                            pass
            else:
                self._hotkeys_active = True

            time.sleep(2.0)

    def start_global_hotkeys(self):
        """Start global keyboard listener with automatic watchdog supervisor."""
        self._stop_hotkeys = False
        if self._supervisor_thread is None or not self._supervisor_thread.is_alive():
            self._supervisor_thread = threading.Thread(target=self._hotkey_supervisor_loop, daemon=True)
            self._supervisor_thread.start()

    def stop_global_hotkeys(self):
        """Stop global keyboard listener and supervisor watchdog."""
        self._stop_hotkeys = True
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
