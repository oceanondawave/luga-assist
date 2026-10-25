"""
Configuration settings for Luga Assist.
"""
from pathlib import Path
import os

import sys

BASE_DIR = Path(__file__).resolve().parent.parent

# Server configuration (Port 8765: dedicated non-conflicting port for Luga Assist)
HOST = os.getenv("LUGA_HOST", "127.0.0.1")
PORT = int(os.getenv("LUGA_PORT", "8765"))

# Static and Web assets
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    WEB_DIR = Path(sys._MEIPASS) / "web"
    if not WEB_DIR.exists():
        WEB_DIR = BASE_DIR / "web"
else:
    WEB_DIR = BASE_DIR / "web"

# Runtime directories (User Data, temp and logs)
# Use user home directory (.luga_assist) to guarantee write permissions
# and ensure credentials & profiles persist permanently across application updates.
USER_DATA_DIR = Path.home() / ".luga_assist"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

TEMP_DIR = USER_DATA_DIR / "temp"
LOGS_DIR = USER_DATA_DIR / "logs"
GEMINI_CACHE_DIR = USER_DATA_DIR / "gemini_cache"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
GEMINI_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Tell gemini_webapi to use persistent cache in USER_DATA_DIR (never in %TEMP%)
os.environ["GEMINI_COOKIE_PATH"] = str(GEMINI_CACHE_DIR)

LOG_FILE = LOGS_DIR / "luga_assist.log"
ERROR_LOG_FILE = LOGS_DIR / "error.log"
PID_FILE = TEMP_DIR / "luga_assist.pid"

# TTS Settings (Edge TTS & fallback)
# Vietnamese Neural Voices:
# - vi-VN-HoaiMyNeural (Female, natural, clear, recommended)
# - vi-VN-NamMinhNeural (Male, natural, newsreader style)
DEFAULT_TTS_VOICE = os.getenv("LUGA_TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_RATE = "+0%"
TTS_VOLUME = os.getenv("LUGA_TTS_VOLUME", "+25%")  # Boosted loud & clear volume

# AI Thinking Level Settings:
# - 'low': Ultra-fast execution, direct actions, concise explanation
# - 'medium': Balanced reasoning and thorough step planning (Default / Khuyên dùng)
# - 'high': Deep multi-step reasoning, exhaustive UI grounding, deep explanation
DEFAULT_THINKING_LEVEL = os.getenv("LUGA_THINKING_LEVEL", "medium")

# Visual Grid Settings for precise AI Grounding
# Draws a reference grid overlay on screenshots so Gemini can pinpoint exact coordinates
ENABLE_VISUAL_GRID = True
GRID_PERCENT_STEP = 5  # 5% grid lines for fine-grained coordinate precision
SCREENSHOT_MAX_WIDTH = 2560  # Native 2K/QHD resolution for pixel-sharp UI labels, icons & buttons

# High-Speed Automation limits
MOUSE_MOVE_DURATION = 0.08  # Ultra-fast, snappy mouse movement
ACTION_SAFETY_PAUSE = 0.03  # Instant pacing between steps

# Audio Feedback Settings
# Processing pulse: enabled by default for reassuring auditory UX while Gemini is thinking
ENABLE_PROCESSING_PULSE = os.getenv("LUGA_ENABLE_PULSE", "true").lower() in ("true", "1", "yes")

# Voice Recognition Language Settings:
# - 'auto': Concurrent bilingual recognition (vi-VN & en-US in parallel, auto-detected)
# - 'vi-VN': Vietnamese only
# - 'en-US': English only
VOICE_RECOGNITION_LANG = os.getenv("LUGA_STT_LANG", "auto")
