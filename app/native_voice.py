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
import subprocess
from pathlib import Path
from typing import Optional, Callable

import audioop
import sounddevice as sd
import speech_recognition as sr
from pynput import keyboard
from app.sound_effects import sound_manager

class NativeVoiceListener:
    def __init__(self, on_command_callback: Optional[Callable[[str], None]] = None):
        self.on_command = on_command_callback
        self.recognizer = sr.Recognizer()
        self.is_recording = False
        self.is_processing = False
        self._stop_requested = False
        self.sample_rate = 16000
        self.channels = 1
        self._hotkey_listener: Optional[keyboard.Listener] = None
        self._current_keys = set()

    def listen_and_transcribe(self) -> Optional[str]:
        """
        Record audio from system microphone with rapid voice activity detection (VAD).
        Stops automatically when user stops speaking (0.65s silence threshold).
        """
        self.is_recording = True
        self._stop_requested = False
        sound_manager.play_start()
        print("\n" + "=" * 60)
        print("🎙️ ĐANG LẮNG NGHE BẠN NÓI... (Nói lệnh và dừng lại khi nói xong)")
        print("=" * 60)

        chunk_duration = 0.08  # 80ms chunks for rapid response
        chunk_samples = int(self.sample_rate * chunk_duration)
        recorded_frames = []

        silence_threshold = 280  # RMS energy threshold
        speech_detected = False
        silence_start_time = None
        silence_duration_to_stop = 0.55  # Ultra-fast 0.55s silence cutoff (instant response)
        max_duration = 10.0  # Max 10 seconds per command
        start_time = time.time()

        try:
            with sd.RawInputStream(samplerate=self.sample_rate, channels=self.channels, dtype="int16") as stream:
                while self.is_recording and not self._stop_requested:
                    data, overflowed = stream.read(chunk_samples)
                    raw_bytes = bytes(data)
                    recorded_frames.append(raw_bytes)

                    # Calculate RMS energy using C-accelerated audioop
                    try:
                        rms = audioop.rms(raw_bytes, 2)
                    except Exception:
                        rms = 0

                    if rms > silence_threshold:
                        speech_detected = True
                        silence_start_time = None
                    elif speech_detected:
                        if silence_start_time is None:
                            silence_start_time = time.time()
                        elif time.time() - silence_start_time >= silence_duration_to_stop:
                            print("[NativeVoice] 🔇 Đã phát hiện kết thúc câu nói.")
                            break

                    if time.time() - start_time > max_duration:
                        break

        except Exception as e:
            print(f"[NativeVoice] Lỗi khi thu âm từ micro: {e}")
            sound_manager.play_error()
            self.is_recording = False
            return None

        self.is_recording = False
        if not recorded_frames or not speech_detected:
            print("[NativeVoice] Không phát hiện thấy giọng nói.")
            sound_manager.play_error()
            return None

        # Start pulsing sound as soon as voice stops and thinking begins!
        sound_manager.start_pulsing()
        print("[NativeVoice] ⏳ Đang nhận diện tiếng Việt qua Google STT...")

        audio_bytes = b"".join(recorded_frames)
        audio = sr.AudioData(audio_bytes, self.sample_rate, 2)

        try:
            text = self.recognizer.recognize_google(audio, language="vi-VN")
            text = text.strip()
            print(f"\n[NativeVoice] 🗣️ Nhận diện thành công: \"{text}\"")
            return text
        except sr.UnknownValueError:
            print("[NativeVoice] Chưa nghe rõ câu lệnh, vui lòng thử lại.")
            sound_manager.play_error()
            return None
        except Exception as e:
            print(f"[NativeVoice] Lỗi nhận diện: {e}")
            sound_manager.play_error()
            return None

    def trigger_voice_flow(self):
        """Trigger the complete voice-to-action flow without opening any browser."""
        if self.is_processing:
            print("[NativeVoice] Hệ thống đang bận thực hiện tác vụ trước...")
            return

        if self.is_recording:
            self._stop_requested = True
            return

        self.is_processing = True

        def _worker():
            try:
                cmd_text = self.listen_and_transcribe()
                if cmd_text and self.on_command:
                    self.on_command(cmd_text)
            finally:
                self.is_processing = False

        threading.Thread(target=_worker, daemon=True).start()

    def start_global_hotkeys(self):
        """
        Start global keyboard listener in background.
        Global Hotkeys:
        - F8: Toggle listening (Dedicated physical key, perfect for visually impaired users)
        - Ctrl + Space: Alternative hotkey
        """
        def on_press(key):
            try:
                # F8
                if key == keyboard.Key.f8:
                    print("\n[Global Hotkey] Đã nhấn F8 -> Bắt đầu lắng nghe!")
                    self.trigger_voice_flow()
                    return

                # Ctrl + Space
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._current_keys.add("ctrl")
                elif key == keyboard.Key.space:
                    if "ctrl" in self._current_keys:
                        print("\n[Global Hotkey] Đã nhấn Ctrl + Space -> Bắt đầu lắng nghe!")
                        self.trigger_voice_flow()
                        return
            except Exception:
                pass

        def on_release(key):
            try:
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._current_keys.discard("ctrl")
            except Exception:
                pass

        self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        print("\n" + "=" * 65)
        print("🎙️ GLOBAL WAY - TRỢ LÝ TOÀN HỆ THỐNG ĐÃ SẴN SÀNG!")
        print("👉 Nhấn phím F8 (hoặc Ctrl + Space) BẤT CỨ ĐÂU để nói lệnh.")
        print("👉 KHÔNG CẦN MỞ TRÌNH DUYỆT - MÀN HÌNH HOÀN TOÀN THOÁNG ĐÃNG.")
        print("=" * 65 + "\n")
