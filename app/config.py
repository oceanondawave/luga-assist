"""
Configuration settings for Luga Assist.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Server configuration
HOST = os.getenv("LUGA_HOST", "127.0.0.1")
PORT = int(os.getenv("LUGA_PORT", "8000"))

# Static and Web assets
WEB_DIR = BASE_DIR / "web"
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# TTS Settings (Edge TTS & fallback)
# Vietnamese Neural Voices:
# - vi-VN-HoaiMyNeural (Female, natural, clear, recommended)
# - vi-VN-NamMinhNeural (Male, natural, newsreader style)
DEFAULT_TTS_VOICE = os.getenv("LUGA_TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_RATE = "+0%"
TTS_VOLUME = "+0%"

# Visual Grid Settings for precise AI Grounding
# Draws a reference grid overlay on screenshots so Gemini can pinpoint exact coordinates
ENABLE_VISUAL_GRID = True
GRID_PERCENT_STEP = 5  # 5% grid lines for fine-grained coordinate precision
SCREENSHOT_MAX_WIDTH = 1920  # High-definition resolution for crisp UI labels & inputs

# High-Speed Automation limits
MOUSE_MOVE_DURATION = 0.08  # Ultra-fast, snappy mouse movement
ACTION_SAFETY_PAUSE = 0.03  # Instant pacing between steps

# Audio Feedback Settings
# Processing pulse: default False to avoid unnecessary sound during fast tasks
ENABLE_PROCESSING_PULSE = os.getenv("LUGA_ENABLE_PULSE", "false").lower() in ("true", "1", "yes")
