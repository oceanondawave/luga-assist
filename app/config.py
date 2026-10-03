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
GRID_PERCENT_STEP = 10  # 10% grid lines (0%, 10%, 20%... 100%)
SCREENSHOT_MAX_WIDTH = 1920  # Rescale screenshot to fit upload limits if screen is 4K/Retina

# Automation limits
MOUSE_MOVE_DURATION = 0.4  # Smooth mouse movement
ACTION_SAFETY_PAUSE = 0.2  # Pause between sequential actions
