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

from app.config import TEMP_DIR

class SoundManager:
    def __init__(self):
        self._pulse_thread: Optional[threading.Thread] = None
        self._stop_pulse = threading.Event()
        self._prepare_fallback_wavs()

    def _prepare_fallback_wavs(self):
        """Generate smooth procedural WAV files for cross-platform sound."""
        self.snd_start = TEMP_DIR / "snd_start.wav"
        self.snd_pulse = TEMP_DIR / "snd_pulse.wav"
        self.snd_done = TEMP_DIR / "snd_done.wav"
        self.snd_error = TEMP_DIR / "snd_error.wav"

        if not self.snd_pulse.exists():
            self._create_tone(self.snd_start, [523.25, 659.25], duration=0.12, volume=0.25)
            self._create_tone(self.snd_pulse, [587.33], duration=0.04, volume=0.18)
            self._create_tone(self.snd_done, [523.25, 659.25, 783.99], duration=0.15, volume=0.25)
            self._create_tone(self.snd_error, [220.0, 180.0], duration=0.2, volume=0.25)

    def _create_tone(self, path: Path, freqs: list, duration: float = 0.1, volume: float = 0.25):
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

    def _play_file(self, file_path: str, volume: float = 0.5):
        """Play sound file non-blocking in background."""
        try:
            if sys.platform == "darwin":  # macOS
                subprocess.Popen(
                    ["/usr/bin/afplay", "-v", str(volume), file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif sys.platform.startswith("win"):  # Windows
                subprocess.Popen(
                    ["powershell", "-c", f"(New-Object Media.SoundPlayer '{file_path}').Play()"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        except Exception:
            pass

    def play_start(self):
        """Chime when voice listening is activated."""
        if sys.platform == "darwin" and os.path.exists("/System/Library/Sounds/Tink.aiff"):
            self._play_file("/System/Library/Sounds/Tink.aiff", volume=0.7)
        else:
            self._play_file(str(self.snd_start), volume=0.4)
        print("\n[Sound] 🔔 TINK (Đã kích hoạt chế độ nghe)")

    def start_pulsing(self):
        """Start repeating pulse sound while Gemini is thinking/processing."""
        if self._pulse_thread and self._pulse_thread.is_alive() and not self._stop_pulse.is_set():
            return  # Already pulsing smoothly
        self.stop_pulsing()
        self._stop_pulse.clear()

        def _pulse_loop():
            pulse_sound = "/System/Library/Sounds/Pop.aiff" if sys.platform == "darwin" and os.path.exists("/System/Library/Sounds/Pop.aiff") else str(self.snd_pulse)
            while not self._stop_pulse.is_set():
                self._play_file(pulse_sound, volume=0.35)
                # Pulse rhythm every 500ms
                if self._stop_pulse.wait(0.50):
                    break

        self._pulse_thread = threading.Thread(target=_pulse_loop, daemon=True)
        self._pulse_thread.start()
        print("[Sound] ⏳ PULSING (Đang phát nhịp tim âm thanh trong khi xử lý...)")

    def stop_pulsing(self):
        """Stop pulsing sound immediately."""
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._stop_pulse.set()
            self._pulse_thread.join(timeout=0.2)
            self._pulse_thread = None

    def play_done(self):
        """Chime when processing and action execution is complete."""
        self.stop_pulsing()
        if sys.platform == "darwin" and os.path.exists("/System/Library/Sounds/Glass.aiff"):
            self._play_file("/System/Library/Sounds/Glass.aiff", volume=0.7)
        else:
            self._play_file(str(self.snd_done), volume=0.5)
        print("[Sound] 🔔 GLASS (Xử lý hoàn tất!)")

    def play_error(self):
        """Error sound."""
        self.stop_pulsing()
        if sys.platform == "darwin" and os.path.exists("/System/Library/Sounds/Basso.aiff"):
            self._play_file("/System/Library/Sounds/Basso.aiff", volume=0.6)
        else:
            self._play_file(str(self.snd_error), volume=0.5)
        print("[Sound] ⚠️ BASSO (Có lỗi xảy ra)")

sound_manager = SoundManager()
