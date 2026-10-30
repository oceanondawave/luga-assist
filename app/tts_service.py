"""
Text-to-Speech service using Edge-TTS with natural Vietnamese Neural voices
and fallback to gTTS and native OS audio playback.
"""
import asyncio
import os
import sys
import shutil
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
        self._is_speaking: bool = False
        self._abort_speech: bool = False

    @property
    def is_speaking(self) -> bool:
        """Check if speech audio is currently playing or being generated."""
        if self._is_speaking and self._current_process:
            if self._current_process.poll() is not None:
                self._is_speaking = False
        return self._is_speaking

    async def generate_audio(self, text: str, voice: Optional[str] = None) -> Optional[Path]:
        """
        Generate MP3 audio file from text using edge-tts (or gTTS fallback).
        """
        if self._abort_speech:
            return None

        selected_voice = voice or self.voice
        clean_text = text.strip()
        if not clean_text:
            clean_text = "Dạ, tôi đã sẵn sàng."

        # Stop any active playback to unlock destination file
        self.stop_speaking()
        self._abort_speech = False

        import time
        output_file = self.latest_audio_path
        try:
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=selected_voice,
                rate=self.rate,
                volume=self.volume
            )
            await communicate.save(str(output_file))
            if self._abort_speech:
                return None
            return output_file
        except Exception as e:
            if self._abort_speech:
                return None
            print(f"[TTSService] Edge-TTS warning ({e}), falling back to gTTS...")
            try:
                tts = gTTS(text=clean_text, lang="vi", slow=False)
                # If primary file is somehow locked, use unique timestamp filename
                try:
                    tts.save(str(output_file))
                except Exception:
                    output_file = TEMP_DIR / f"tts_{int(time.time() * 1000)}.mp3"
                    tts.save(str(output_file))
                if self._abort_speech:
                    return None
                return output_file
            except Exception as gtts_err:
                print(f"[TTSService] gTTS error: {gtts_err}")
                raise gtts_err

    def _play_via_mci(self, audio_file: Path, block: bool = False) -> bool:
        """
        Play audio file in-process via Windows Media Control Interface (winmm.dll).
        Zero external processes, zero console windows, instantaneous start.
        """
        if not sys.platform.startswith("win") or self._abort_speech:
            return False
        try:
            import ctypes
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW("close luga_tts", None, 0, None)

            # Get short path to prevent issues with spaces/unicode in MCI commands
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.kernel32.GetShortPathNameW(str(audio_file), buf, 512)
            short_path = buf.value or str(audio_file)

            res = winmm.mciSendStringW(f'open "{short_path}" type mpegvideo alias luga_tts', None, 0, None)
            if res != 0:
                res = winmm.mciSendStringW(f'open "{short_path}" alias luga_tts', None, 0, None)

            if res == 0:
                if self._abort_speech:
                    winmm.mciSendStringW("close luga_tts", None, 0, None)
                    return False
                self._is_speaking = True
                cmd = "play luga_tts wait" if block else "play luga_tts"
                play_res = winmm.mciSendStringW(cmd, None, 0, None)
                if play_res == 0:
                    if block:
                        self._is_speaking = False
                    print("[TTSService] 🔊 Đang phát giọng đọc qua Windows MCI.")
                    return True
                winmm.mciSendStringW("close luga_tts", None, 0, None)
        except Exception as e:
            print(f"[TTSService] MCI playback notice: {e}")
        return False

    def _play_via_powershell(self, audio_file: Path, block: bool = False):
        """
        High-reliability Windows audio player using native WMPlayer.OCX COM engine.
        Guaranteed to work on Windows 10 & 11 without requiring WPF Dispatcher loops.
        """
        if self._abort_speech:
            return
        escaped_path = str(audio_file).replace("'", "''")
        ps_script = (
            f"$f = '{escaped_path}'; "
            f"try {{ "
            f"  $w = New-Object -ComObject WMPlayer.OCX; "
            f"  $w.settings.volume = 100; "
            f"  $w.settings.autoStart = $true; "
            f"  $w.URL = $f; "
            f"  $w.controls.play(); "
            f"  for ($i = 0; $i -lt 40 -and $w.playState -ne 3 -and $w.playState -ne 1; $i++) {{ Start-Sleep -Milliseconds 50 }}; "
            f"  while ($w.playState -eq 3 -or $w.playState -eq 6 -or $w.playState -eq 9) {{ Start-Sleep -Milliseconds 100 }}; "
            f"}} catch {{ "
            f"  try {{ "
            f"    Add-Type -AssemblyName System.Windows.Forms; "
            f"    Add-Type -AssemblyName PresentationCore; "
            f"    $p = New-Object System.Windows.Media.MediaPlayer; "
            f"    $p.Open([System.Uri]::new($f)); "
            f"    $p.Play(); "
            f"    for ($i = 0; $i -lt 30 -and !$p.NaturalDuration.HasTimeSpan; $i++) {{ "
            f"      [System.Windows.Forms.Application]::DoEvents(); "
            f"      Start-Sleep -Milliseconds 100; "
            f"    }}; "
            f"    if ($p.NaturalDuration.HasTimeSpan) {{ "
            f"      Start-Sleep -Seconds ($p.NaturalDuration.TimeSpan.TotalSeconds + 0.3); "
            f"    }}; "
            f"  }} catch {{}} "
            f"}}"
        )
        flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script]

        try:
            self._is_speaking = True
            print("[TTSService] 🔊 Đang phát giọng đọc qua Windows Media Engine.")
            if block:
                subprocess.run(cmd, check=False, creationflags=flags)
                self._is_speaking = False
            else:
                self._current_process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
                )
        except Exception as e:
            self._is_speaking = False
            print(f"[TTSService] Background audio player error: {e}")

    def play_audio_file(self, audio_file: Path, block: bool = False):
        """
        Play the audio file natively on the operating system without flashing windows.
        """
        if self._abort_speech or not audio_file:
            return

        # Stop previous playback if still running
        self.stop_speaking()
        self._abort_speech = False

        # 1. Primary: Windows in-process MCI
        if sys.platform.startswith("win"):
            if self._play_via_mci(audio_file, block=block):
                return
            # 2. Secondary: Silent background PowerShell (CREATE_NO_WINDOW)
            self._play_via_powershell(audio_file, block=block)
        else:
            player = shutil.which("afplay") or shutil.which("paplay") or shutil.which("aplay")
            if player:
                cmd = [player, str(audio_file)]
                self._is_speaking = True
                if block:
                    subprocess.run(cmd, check=False)
                    self._is_speaking = False
                else:
                    self._current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def speak(self, text: str, block: bool = False) -> str:
        """
        Synthesize speech, play it on system speakers, and return base64 audio URI.
        """
        self._abort_speech = False
        self._is_speaking = True
        try:
            audio_path = await self.generate_audio(text)
            if self._abort_speech or not audio_path or not audio_path.exists():
                self._is_speaking = False
                return ""

            self.play_audio_file(audio_path, block=block)
            if self._abort_speech:
                self._is_speaking = False
                return ""

            # Also encode to base64 so web browser can play if needed
            with open(audio_path, "rb") as f:
                b64_audio = base64.b64encode(f.read()).decode("utf-8")
            return f"data:audio/mp3;base64,{b64_audio}"
        except asyncio.CancelledError:
            self._is_speaking = False
            return ""
        except Exception as e:
            self._is_speaking = False
            raise e

    def stop_speaking(self):
        """Immediately stop currently playing audio and cancel any active/pending speech."""
        self._abort_speech = True
        self._is_speaking = False

        if sys.platform.startswith("win"):
            try:
                import ctypes
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW("stop luga_tts", None, 0, None)
                winmm.mciSendStringW("close luga_tts", None, 0, None)
                winmm.mciSendStringW("stop all", None, 0, None)
                winmm.mciSendStringW("close all", None, 0, None)
            except Exception:
                pass

        if self._current_process:
            try:
                if self._current_process.poll() is None:
                    if sys.platform.startswith("win"):
                        flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self._current_process.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=flags,
                            check=False
                        )
                    else:
                        self._current_process.kill()
            except Exception:
                pass
            self._current_process = None

tts_service = TTSService()
