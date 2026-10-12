"""
Text-to-Speech service using Edge-TTS with natural Vietnamese Neural voices
and fallback to gTTS and native OS audio playback.
"""
import asyncio
import os
import sys
import subprocess
import base64
from pathlib import Path
from typing import Optional

import edge_tts
from gtts import gTTS

from app.config import (
    TEMP_DIR,
    DEFAULT_TTS_VOICE,
    TTS_RATE,
    TTS_VOLUME,
)

class TTSService:
    def __init__(self):
        self.voice = DEFAULT_TTS_VOICE
        self.rate = TTS_RATE
        self.volume = TTS_VOLUME
        self.latest_audio_path = TEMP_DIR / "tts_latest.mp3"
        self._current_process: Optional[subprocess.Popen] = None

    async def generate_audio(self, text: str, voice: Optional[str] = None) -> Path:
        """
        Generate MP3 audio file from text using edge-tts (or gTTS fallback).
        """
        selected_voice = voice or self.voice
        clean_text = text.strip()
        if not clean_text:
            clean_text = "Dạ, tôi đã sẵn sàng."

        output_file = self.latest_audio_path

        try:
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=selected_voice,
                rate=self.rate,
                volume=self.volume
            )
            await communicate.save(str(output_file))
            return output_file
        except Exception as e:
            print(f"[TTSService] Edge-TTS warning ({e}), falling back to gTTS...")
            try:
                tts = gTTS(text=clean_text, lang="vi", slow=False)
                tts.save(str(output_file))
                return output_file
            except Exception as gtts_err:
                print(f"[TTSService] gTTS error: {gtts_err}")
                raise gtts_err

    def play_audio_file(self, audio_file: Path, block: bool = False):
        """
        Play the audio file natively on the operating system.
        """
        # Stop previous playback if still running
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass

        # Windows: WMPlayer.OCX COM object natively supports MP3 playback without extra dependencies
        ps_script = (
            f"$w = New-Object -ComObject WMPlayer.OCX; "
            f"$w.URL = '{audio_file}'; "
            f"$w.controls.play(); "
            f"while($w.playState -ne 1) {{ Start-Sleep -Milliseconds 100 }}"
        )
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script]

        try:
            if block:
                subprocess.run(cmd, check=False)
            else:
                self._current_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception as e:
            print(f"[TTSService] Error playing audio: {e}")

    async def speak(self, text: str, block: bool = False) -> str:
        """
        Synthesize speech, play it on system speakers, and return base64 audio URI.
        """
        audio_path = await self.generate_audio(text)
        self.play_audio_file(audio_path, block=block)

        # Also encode to base64 so web browser can play if needed
        with open(audio_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("utf-8")
        return f"data:audio/mp3;base64,{b64_audio}"

    def stop_speaking(self):
        """Immediately stop currently playing audio."""
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass

tts_service = TTSService()
