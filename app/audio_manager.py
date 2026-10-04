"""
Audio Device & Microphone Manager for Luga Assist.
Allows users to discover, test, select, and persist their preferred microphone.
Prevents recording silence from virtual or muted audio devices.
"""
import sys
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import sounddevice as sd
import audioop

from app.config import TEMP_DIR
from app.logger import get_logger

logger = get_logger("AudioManager")
AUDIO_CONFIG_FILE = TEMP_DIR / "audio_device.json"


class AudioManager:
    def __init__(self):
        self._cached_devices: Optional[List[Dict[str, Any]]] = None
        self._last_scan_time: float = 0.0

    def list_input_devices(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List all available audio input devices (microphones)."""
        now = time.time()
        if not force_refresh and self._cached_devices and (now - self._last_scan_time < 3.0):
            return self._cached_devices

        try:
            raw_devices = sd.query_devices()
            try:
                default_in = sd.default.device[0] if sd.default.device is not None else None
            except Exception:
                default_in = None
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
            return []

        active_selection = self.get_saved_device_name()
        is_default = (active_selection is None or active_selection.lower() in ("default", "auto", "mặc định", "mặc định hệ thống", ""))
        devices = [
            {
                "id": -1,
                "name": "⚙️ Mặc định hệ thống (System Default)",
                "channels": 1,
                "sample_rate": 44100.0,
                "is_default": False,
                "is_selected": is_default,
            }
        ]
        for i, d in enumerate(raw_devices):
            if d.get("max_input_channels", 0) > 0:
                name = d.get("name", f"Microphone {i}")
                is_selected = False
                if not is_default and active_selection:
                    is_selected = (name == active_selection or active_selection.lower() in name.lower())
                elif is_default and default_in is not None and i == default_in:
                    is_selected = True

                devices.append({
                    "id": i,
                    "name": name,
                    "channels": d.get("max_input_channels", 1),
                    "sample_rate": d.get("default_samplerate", 44100.0),
                    "is_default": (i == default_in),
                    "is_selected": is_selected,
                })

        self._cached_devices = devices
        self._last_scan_time = now
        return devices

    def get_saved_device_name(self) -> Optional[str]:
        """Read saved microphone name from disk."""
        if AUDIO_CONFIG_FILE.exists():
            try:
                with open(AUDIO_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("selected_device_name")
            except Exception:
                pass
        return None

    def get_active_device_index(self) -> Tuple[Optional[int], str]:
        """
        Get the device index and name for recording.
        Supports 100% of audio devices (hardware and virtual).
        Uses exactly what the computer/OS is currently using (system default)
        unless the user explicitly picked a specific device.
        """
        devices = self.list_input_devices(force_refresh=True)
        saved_name = self.get_saved_device_name()

        # 1. If user explicitly selected a specific device (and not default/auto)
        is_default_saved = (not saved_name or saved_name.lower() in ("default", "auto", "mặc định", "mặc định hệ thống", ""))
        if not is_default_saved:
            for d in devices:
                if d.get("id", -1) >= 0 and (d["name"] == saved_name or saved_name.lower() in d["name"].lower()):
                    return d["id"], d["name"]

        # 2. Use system default device that the computer is currently using
        try:
            default_in = sd.default.device[0] if sd.default.device is not None else None
            if default_in is not None and default_in >= 0:
                def_info = sd.query_devices(default_in)
                return default_in, def_info.get("name", f"Microphone {default_in}")
        except Exception as e:
            logger.error(f"Error getting default audio device: {e}")

        # 3. Fallback to first available real device
        for d in devices:
            if d.get("id", -1) >= 0:
                return d["id"], d["name"]

        return None, "Default Microphone"

    def set_active_device(self, name_or_id: Any) -> Dict[str, Any]:
        """Save user's preferred microphone by name or id."""
        devices = self.list_input_devices(force_refresh=True)
        chosen = None

        if name_or_id in (-1, "auto", "Auto", "default", "Default") or "mặc định" in str(name_or_id).lower() or "tự động" in str(name_or_id).lower():
            try:
                with open(AUDIO_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"selected_device_name": "Default", "selected_device_id": -1}, f, indent=2)
                self._cached_devices = None
                logger.info("Active microphone set to System Default")
                return {"id": -1, "name": "⚙️ Mặc định hệ thống (System Default)", "channels": 1, "is_default": False, "is_selected": True}
            except Exception as e:
                logger.error(f"Error saving default config: {e}")

        if isinstance(name_or_id, int):
            for d in devices:
                if d["id"] == name_or_id:
                    chosen = d
                    break
        elif isinstance(name_or_id, str):
            for d in devices:
                if d["name"] == name_or_id or name_or_id.lower() in d["name"].lower():
                    chosen = d
                    break

        if not chosen and devices:
            chosen = devices[0]

        if chosen:
            try:
                with open(AUDIO_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"selected_device_name": chosen["name"], "selected_device_id": chosen["id"]}, f, indent=2)
                logger.info(f"Active microphone updated to: {chosen['name']} (ID: {chosen['id']})")
            except Exception as e:
                logger.error(f"Error saving audio config: {e}")

            # Update cache
            self._cached_devices = None
            return chosen

        return {"error": "Device not found"}

    def test_microphone_level(self, device_id: Optional[int] = None, duration: float = 0.5) -> Dict[str, Any]:
        """
        Record a brief snippet using non-blocking audio callbacks to test if microphone is picking up sound.
        Returns average RMS, peak level, and whether signal is detected.
        Safe against AUHAL / PortAudio deadlocks.
        """
        import queue
        if device_id is None:
            dev_idx, dev_name = self.get_active_device_index()
        else:
            dev_idx = device_id
            dev_name = f"Device {device_id}"

        try:
            try:
                dev_info = sd.query_devices(dev_idx) if dev_idx is not None else {}
                sample_rate = int(dev_info.get("default_samplerate", 44100)) if isinstance(dev_info, dict) else 44100
                channels = min(2, int(dev_info.get("max_input_channels", 1))) if isinstance(dev_info, dict) else 1
                if "name" in dev_info:
                    dev_name = dev_info["name"]
            except Exception:
                sample_rate = 44100
                channels = 1

            chunk_size = int(sample_rate * 0.1)  # 100ms chunks
            chunks_to_read = max(1, int(duration / 0.1))

            audio_queue = queue.Queue()
            def _audio_callback(indata, frames, time_info, status):
                audio_queue.put(bytes(indata))

            total_rms = 0
            peak_rms = 0
            chunks_received = 0

            with sd.RawInputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                device=dev_idx,
                blocksize=chunk_size,
                callback=_audio_callback
            ):
                for _ in range(chunks_to_read):
                    try:
                        raw_data = audio_queue.get(timeout=0.35)
                        if channels == 2:
                            mono_data = audioop.tomono(raw_data, 2, 0.5, 0.5)
                            chunk_rms = audioop.rms(mono_data, 2)
                        else:
                            chunk_rms = audioop.rms(raw_data, 2)
                        total_rms += chunk_rms
                        if chunk_rms > peak_rms:
                            peak_rms = chunk_rms
                        chunks_received += 1
                    except queue.Empty:
                        break

            avg_rms = (total_rms // chunks_received) if chunks_received > 0 else 0
            has_signal = avg_rms > 0
            return {
                "success": True,
                "device_id": dev_idx,
                "device_name": dev_name,
                "avg_rms": avg_rms,
                "peak_rms": peak_rms,
                "has_signal": has_signal,
            }
        except Exception as e:
            logger.error(f"Error testing microphone {dev_idx}: {e}")
            return {
                "success": False,
                "device_id": dev_idx,
                "device_name": dev_name,
                "error": str(e),
                "avg_rms": 0,
                "peak_rms": 0,
                "has_signal": False,
            }


audio_manager = AudioManager()
