"""
Sound Effects & Audio Feedback Manager for Luga Assist.
Provides auditory cues for visually impaired users:
- Activation chime (when voice mode is started)
- Pulsing heartbeat cue (while Gemini is processing/thinking)
- Completion chime (when action is executed)
- Error chime
Works natively on macOS (system sounds) and Windows/Linux (procedural WAVs).
"""
import sys
import os
import time
import math
import struct
import wave
import threading
import subprocess
from pathlib import Path
from typing import Optional

try:
    import winsound
except ImportError:
    winsound = None

from app.config import TEMP_DIR, ENABLE_PROCESSING_PULSE

class SoundManager:
    def __init__(self):
        self._pulse_thread: Optional[threading.Thread] = None
        self._stop_pulse = threading.Event()
        self._pulse_id: int = 0
        self.pulse_enabled: bool = ENABLE_PROCESSING_PULSE
        self._prepare_fallback_wavs()

    def set_pulse_enabled(self, enabled: bool):
        """Toggle processing pulse sound on/off."""
        self.pulse_enabled = enabled
        if not enabled:
            self.stop_pulsing()

    def _prepare_fallback_wavs(self):
        """Generate loud, clear procedural WAV files for cross-platform audio feedback."""
        self.snd_start = TEMP_DIR / "snd_start.wav"
        self.snd_pulse = TEMP_DIR / "snd_pulse.wav"
        self.snd_done = TEMP_DIR / "snd_done.wav"
        self.snd_error = TEMP_DIR / "snd_error.wav"

        # Generate loud & crisp assistant sounds (only if missing or 0 bytes to prevent file locks)
        if not self.snd_start.exists() or self.snd_start.stat().st_size == 0:
            self._create_rising_chime(self.snd_start)
        if not self.snd_pulse.exists() or self.snd_pulse.stat().st_size == 0:
            self._create_gentle_pulse(self.snd_pulse)
        if not self.snd_done.exists() or self.snd_done.stat().st_size == 0:
            self._create_tone(self.snd_done, [523.25, 659.25, 783.99], duration=0.18, volume=0.85)
        if not self.snd_error.exists() or self.snd_error.stat().st_size == 0:
            self._create_tone(self.snd_error, [220.0, 180.0], duration=0.22, volume=0.85)

    def _create_gentle_pulse(self, path: Path):
        """Generate a loud, warm ambient thinking pulse (E5 droplet tone with natural decay)."""
        rate = 44100
        duration = 0.09
        samples = int(rate * duration)
        data = bytearray()
        for i in range(samples):
            t = float(i) / rate
            if i < int(rate * 0.004):
                env = math.sin((math.pi / 2) * (i / (rate * 0.004)))
            else:
                env = math.exp(-28 * (t - 0.004))
            val = math.sin(2 * math.pi * 659.25 * t) * 0.85 + math.sin(2 * math.pi * 987.77 * t) * 0.15
            # Loud and clear volume (0.85 amplitude)
            sample = int(32767 * 0.85 * env * val)
            data.extend(struct.pack("<h", max(-32768, min(32767, sample))))

        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(data)

    def _create_rising_chime(self, path: Path):
        """Generate a bright, loud assistant activation chime (D5 -> A5 rising bell)."""
        rate = 44100
        note1_dur = 0.09
        note2_dur = 0.19
        total_dur = note1_dur + note2_dur
        samples1 = int(rate * note1_dur)
        samples2 = int(rate * note2_dur)
        data = bytearray()

        # Note 1: 587.33 Hz (D5) - Loud & crisp
        for i in range(samples1):
            t = float(i) / rate
            env = math.sin(math.pi * (i / samples1)) ** 0.5
            val = math.sin(2 * math.pi * 587.33 * t) * 0.75 + math.sin(2 * math.pi * 1174.66 * t) * 0.25
            sample = int(32767 * 0.90 * env * val)
            data.extend(struct.pack("<h", max(-32768, min(32767, sample))))

        # Note 2: 880 Hz (A5) with bell resonance decay - High volume
        for i in range(samples2):
            t = float(i) / rate
            env = math.exp(-3.8 * (i / samples2))
            val = math.sin(2 * math.pi * 880.0 * t) * 0.80 + math.sin(2 * math.pi * 1760.0 * t) * 0.20
            sample = int(32767 * 0.95 * env * val)
            data.extend(struct.pack("<h", max(-32768, min(32767, sample))))

        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(data)

    def _create_tone(self, path: Path, freqs: list, duration: float = 0.18, volume: float = 0.85):
        rate = 22050
        with wave.open(str(path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            n_samples = int(rate * duration)
            data = bytearray()
            for i in range(n_samples):
                t = float(i) / rate
                env = math.sin(math.pi * (i / n_samples))
                val = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
                sample = int(32767 * volume * env * val)
                data.extend(struct.pack("<h", max(-32768, min(32767, sample))))
            wf.writeframes(data)

    def _play_file(self, file_path: str, volume: float = 0.85):
        """Play sound file non-blocking in background without flashing console windows."""
        path_str = str(file_path)
        if not os.path.exists(path_str):
            # Try to regenerate if somehow removed
            self._prepare_fallback_wavs()
            if not os.path.exists(path_str):
                return

        # 1. Primary on Windows: winsound standard library (Direct in-process, 0 latency, 0 windows)
        if sys.platform.startswith("win"):
            if winsound is not None:
                try:
                    winsound.PlaySound(path_str, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                    return
                except Exception:
                    pass

            # 2. Secondary on Windows: WinMM PlaySoundW via ctypes with explicit types
            try:
                import ctypes
                winmm = ctypes.windll.winmm
                winmm.PlaySoundW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
                winmm.PlaySoundW.restype = ctypes.c_bool
                # 0x00020003 = SND_FILENAME (0x20000) | SND_ASYNC (0x1) | SND_NODEFAULT (0x2)
                res = winmm.PlaySoundW(path_str, None, 0x00020003)
                if res:
                    return
            except Exception:
                pass

            # 3. Tertiary: Silent background PowerShell (GUARANTEED CREATE_NO_WINDOW)
            try:
                flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(New-Object Media.SoundPlayer '{path_str}').PlaySync()"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags
                )
            except Exception:
                pass
        else:
            try:
                import shutil
                player = shutil.which("afplay") or shutil.which("paplay") or shutil.which("aplay")
                if player:
                    subprocess.Popen([player, path_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def play_start(self):
        """Chime when voice listening is activated (distinct, loud, bright earcon)."""
        now = time.time()
        if hasattr(self, "_last_start_sound_time") and now - self._last_start_sound_time < 0.15:
            return
        self._last_start_sound_time = now
        self._play_file(str(self.snd_start), volume=1.0)
        print("\n[Sound] 🔔 CHIME (Đã kích hoạt chế độ nghe - Bắt đầu lắng nghe)")

    def play_chime(self):
        """Notification / popup activation earcon."""
        self.play_start()

    def start_pulsing(self):
        """Start repeating pulse sound while Gemini is thinking/processing."""
        if not self.pulse_enabled:
            return  # Pulsing disabled by user preference

        # Check if already running smoothly
        if self._pulse_thread and self._pulse_thread.is_alive() and not self._stop_pulse.is_set():
            return

        self._pulse_id += 1
        current_id = self._pulse_id
        self._stop_pulse.clear()

        def _pulse_loop(pulse_id: int):
            pulse_sound = str(self.snd_pulse)
            while not self._stop_pulse.is_set() and self._pulse_id == pulse_id:
                self._play_file(pulse_sound, volume=0.85)
                # Steady, reassuring 850ms rhythm (calm heartbeat pace)
                if self._stop_pulse.wait(0.85):
                    break

        self._pulse_thread = threading.Thread(target=_pulse_loop, args=(current_id,), daemon=True)
        self._pulse_thread.start()
        print("[Sound] ⏳ PULSING (Đang phát nhịp tim âm thanh trong khi xử lý...)")

    def stop_pulsing(self):
        """Stop pulsing sound immediately."""
        self._pulse_id += 1
        self._stop_pulse.set()
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._pulse_thread = None

    def play_done(self):
        """Chime when processing and action execution is complete."""
        self.stop_pulsing()
        self._play_file(str(self.snd_done), volume=0.9)
        print("[Sound] 🔔 GLASS (Xử lý hoàn tất!)")

    def play_error(self):
        """Error sound."""
        self.stop_pulsing()
        self._play_file(str(self.snd_error), volume=0.9)
        print("[Sound] ⚠️ BASSO (Có lỗi xảy ra)")

    def play_success(self):
        """Alias for play_done sound."""
        self.play_done()

    def play_click(self):
        """Short UI interaction click sound."""
        self.play_chime()


sound_manager = SoundManager()
