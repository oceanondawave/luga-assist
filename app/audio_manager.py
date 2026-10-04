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
        is_auto = (active_selection is None or active_selection.lower() in ("auto", ""))
        devices = [
            {
                "id": -1,
                "name": "🎯 Tự động chọn Micro tốt nhất (Auto)",
                "channels": 1,
                "sample_rate": 44100.0,
                "is_default": False,
                "is_selected": is_auto,
            }
        ]
        for i, d in enumerate(raw_devices):
            if d.get("max_input_channels", 0) > 0:
                name = d.get("name", f"Microphone {i}")
                is_selected = False
                if not is_auto and active_selection:
                    is_selected = (name == active_selection or active_selection.lower() in name.lower())
                elif not is_auto and default_in is not None and i == default_in:
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

    def probe_device_level(self, dev_id: int, duration: float = 0.05) -> int:
        """Quickly measure RMS energy of a device (50ms)."""
        try:
            info = sd.query_devices(dev_id)
            sr = int(info.get("default_samplerate", 44100))
            with sd.RawInputStream(samplerate=sr, channels=1, dtype="int16", device=dev_id) as s:
                data, _ = s.read(int(sr * duration))
                return audioop.rms(bytes(data), 2)
        except Exception:
            return 0

    def get_active_device_index(self) -> Tuple[Optional[int], str]:
        """
        Get the device index and name for recording.
        Matches by saved device name if available.
        If the chosen device is a virtual loopback with no signal (RMS <= 5),
        automatically falls back to an active physical microphone.
        """
        devices = self.list_input_devices(force_refresh=True)
        saved_name = self.get_saved_device_name()

        VIRTUAL_DEVICE_KEYWORDS = ["ocean audio", "blackhole", "soundflower", "loopback", "cadisplay"]

        # 1. Check if user selected a specific real device (not Auto)
        candidate = None
        is_auto_saved = (not saved_name or "auto" in saved_name.lower() or "tự động" in saved_name.lower())
        if not is_auto_saved:
            for d in devices:
                if d.get("id", -1) >= 0 and (d["name"] == saved_name or saved_name.lower() in d["name"].lower()):
                    candidate = d
                    break

        if candidate:
            is_virtual = any(k in candidate["name"].lower() for k in VIRTUAL_DEVICE_KEYWORDS)
            if is_virtual:
                rms = self.probe_device_level(candidate["id"], duration=0.05)
                if rms <= 10:
                    # Virtual device is dead silent. Look for an active physical mic.
                    for d in devices:
                        if d.get("id", -1) >= 0 and not any(k in d["name"].lower() for k in VIRTUAL_DEVICE_KEYWORDS):
                            phys_rms = self.probe_device_level(d["id"], duration=0.05)
                            if phys_rms > 30:
                                logger.info(
                                    f"⚡ Thiết bị '{candidate['name']}' đang im lặng (RMS: {rms}). "
                                    f"Tự động chuyển sang micro phần cứng '{d['name']}' (RMS: {phys_rms})!"
                                )
                                return d["id"], d["name"]
            return candidate["id"], candidate["name"]

        # 2. If 'Auto' or no candidate: find best physical microphone by active signal
        best_dev = None
        best_rms = -1
        first_physical = None

        for d in devices:
            dev_id = d.get("id", -1)
            if dev_id >= 0 and not any(k in d["name"].lower() for k in VIRTUAL_DEVICE_KEYWORDS):
                if first_physical is None:
                    first_physical = d
                # Measure 40ms acoustic level
                rms = self.probe_device_level(dev_id, duration=0.04)
                if rms > best_rms:
                    best_rms = rms
                    best_dev = d

        if best_dev and best_rms > 30:
            return best_dev["id"], best_dev["name"]

        if first_physical:
            return first_physical["id"], first_physical["name"]

        # Fallback to default device
        if default_dev:
            return default_dev["id"], default_dev["name"]

        # Fallback to first available real input device
        for d in devices:
            if d.get("id", -1) >= 0:
                return d["id"], d["name"]

        return None, "Default Microphone"

    def set_active_device(self, name_or_id: Any) -> Dict[str, Any]:
        """Save user's preferred microphone by name or id."""
        devices = self.list_input_devices(force_refresh=True)
        chosen = None

        if name_or_id in (-1, "auto", "Auto") or "tự động" in str(name_or_id).lower():
            try:
                with open(AUDIO_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump({"selected_device_name": "Auto", "selected_device_id": -1}, f, indent=2)
                self._cached_devices = None
                logger.info("Active microphone set to Auto-Detect")
                return {"id": -1, "name": "🎯 Tự động chọn Micro tốt nhất (Auto)", "channels": 1, "is_default": False, "is_selected": True}
            except Exception as e:
                logger.error(f"Error saving auto config: {e}")

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
        Record a brief snippet to test if microphone is picking up sound.
        Returns average RMS, peak level, and whether signal is detected.
        """
        if device_id is None:
            dev_idx, dev_name = self.get_active_device_index()
        else:
            dev_idx = device_id
            dev_name = f"Device {device_id}"

        try:
            # Use native sample rate of device (e.g. 44100 on Loopback/Ocean Audio or 48000 on USB mics)
            # to prevent virtual/HAL drivers from returning silent zeroes
            try:
                dev_info = sd.query_devices(dev_idx) if dev_idx is not None else {}
                sample_rate = int(dev_info.get("default_samplerate", 44100)) if isinstance(dev_info, dict) else 44100
            except Exception:
                sample_rate = 44100

            chunk_size = int(sample_rate * 0.1)  # 100ms chunks
            chunks_to_read = max(1, int(duration / 0.1))

            total_rms = 0
            peak_rms = 0
            with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype="int16", device=dev_idx) as stream:
                for _ in range(chunks_to_read):
                    data, _ = stream.read(chunk_size)
                    chunk_rms = audioop.rms(bytes(data), 2)
                    total_rms += chunk_rms
                    if chunk_rms > peak_rms:
                        peak_rms = chunk_rms

            avg_rms = total_rms // chunks_to_read
            has_signal = avg_rms > 15  # Anything above digital noise floor
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
