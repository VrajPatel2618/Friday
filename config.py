"""
config.py - Central configuration for FRIDAY AI Assistant
Includes: AI backend, voice, memory, vision, gesture, wake word,
          facial emotion, smart home, and dashboard settings.
"""

import os

# ─────────────────────────────────────────────
# API Keys (set via environment variables)
# ─────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")

# ─────────────────────────────────────────────
# AI Backend Selection
# ─────────────────────────────────────────────
# Options:
#   "auto"   -> tries OpenAI first; falls back to Ollama if offline/no key
#   "openai" -> always use OpenAI (requires internet + API key)
#   "ollama" -> always use local Ollama (100% offline, no API key needed)
AI_BACKEND = "auto"

# OpenAI settings
OPENAI_MODEL = "gpt-4o-mini"   # or "gpt-4o", "gpt-3.5-turbo"

# Ollama settings (local LLM — install from https://ollama.ai)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3"        # run: ollama pull llama3

# Auto-mode connectivity check
CONNECTIVITY_CHECK_HOST = "api.openai.com"
CONNECTIVITY_CHECK_PORT = 443
CONNECTIVITY_TIMEOUT = 3      # seconds to wait before declaring offline

# ─────────────────────────────────────────────
# Voice Settings
# ─────────────────────────────────────────────
VOICE_RATE = 175          # TTS speech rate (words per minute)
VOICE_VOLUME = 0.9        # TTS volume (0.0 – 1.0)
VOICE_INDEX = 0           # Voice index (0 = first system voice)
LISTEN_TIMEOUT = 5        # Seconds to wait before giving up on speech
PHRASE_LIMIT = 10         # Max seconds per spoken phrase
ENERGY_THRESHOLD = 300    # Microphone sensitivity

# ─────────────────────────────────────────────
# Memory Settings
# ─────────────────────────────────────────────
MEMORY_FILE = "friday_memory.json"
MAX_MEMORY_FACTS = 30     # Max stored facts per user
MAX_CONTEXT_TURNS = 10    # Conversation turns kept in context

# ─────────────────────────────────────────────
# Camera / Vision Settings
# ─────────────────────────────────────────────
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
GESTURE_FPS_LIMIT = 20    # Max frames/sec for gesture processing
KNOWN_FACES_DIR = "known_faces"  # Folder with user face images

# ─────────────────────────────────────────────
# Gesture Control Settings
# ─────────────────────────────────────────────
SMOOTHING_BUFFER = 5      # Frames used for cursor smoothing
CLICK_COOLDOWN = 1.0      # Seconds between pinch-clicks
PINCH_THRESHOLD = 40      # Pixel distance for pinch detection
GESTURE_SCALE_X = 1.5     # Horizontal sensitivity multiplier
GESTURE_SCALE_Y = 1.5     # Vertical sensitivity multiplier

# ─────────────────────────────────────────────
# Assistant Personality
# ─────────────────────────────────────────────
ASSISTANT_NAME = "FRIDAY"
SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME}, an intelligent personal AI assistant inspired by Iron Man's FRIDAY.
You are witty, helpful, and highly capable. You speak in a professional yet friendly tone.
You have access to the user's memory and can recall facts about them.
Adjust your tone based on the user's detected emotion:
  - Happy: be cheerful and enthusiastic
  - Sad: be empathetic and supportive
  - Angry: be calm and de-escalating
  - Neutral: be professional and helpful
Keep responses concise unless asked to elaborate. Avoid unnecessary filler phrases."""

# ─────────────────────────────────────────────────────────
# Wake Word Settings
# ─────────────────────────────────────────────────────────
# Picovoice requires a company email — use STT fallback instead (no account needed).
# STT fallback listens for "Friday" / "Hey Friday" via Google STT (free, works now).
# To upgrade to Porcupine later: get key at console.picovoice.ai (needs work email)
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "YOUR_PORCUPINE_KEY_HERE")
WAKE_WORD_SENSITIVITY = 0.5    # 0.0 (strict) to 1.0 (permissive)
USE_WAKE_WORD = True           # STT fallback active — say "Friday" to wake

# ─────────────────────────────────────────────────────────
# Facial Emotion Detection (MediaPipe — no TensorFlow needed)
# ─────────────────────────────────────────────────────────
# DeepFace is NOT used (requires TensorFlow which has no Python 3.14 build).
# Setting this to True activates the MediaPipe Face Mesh geometric detector instead.
# No extra install needed — mediapipe is already installed.
USE_DEEPFACE = True            # Set True to enable webcam facial emotion detection

# ─────────────────────────────────────────────────────────
# Face Recognition
# ─────────────────────────────────────────────────────────
# face_recognition + dlib are installed. Add photos to known_faces/ to use.
# Photo format: known_faces/YourName.jpg  (filename = your name)
USE_FACE_RECOGNITION = True    # dlib + face_recognition are installed

# ─────────────────────────────────────────────────────────
# Smart Home / IoT Settings (MQTT)
# ─────────────────────────────────────────────────────────
MQTT_BROKER      = os.getenv("MQTT_BROKER",   "localhost")  # e.g. Home Assistant IP
MQTT_PORT        = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME    = os.getenv("MQTT_USER",     "")
MQTT_PASSWORD    = os.getenv("MQTT_PASS",     "")
HOME_ASSISTANT_URL  = os.getenv("HA_URL",    "")  # e.g. http://192.168.1.100:8123
HOME_ASSISTANT_TOKEN = os.getenv("HA_TOKEN", "")  # Long-lived access token

# ─────────────────────────────────────────────────────────
# Dashboard Settings
# ─────────────────────────────────────────────────────────
USE_DASHBOARD = True           # Set False to disable the GUI dashboard

# ─────────────────────────────────────────────────────────
# Weather (OpenWeatherMap)
# ─────────────────────────────────────────────────────────
# Free API key: https://openweathermap.org/api
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "YOUR_OPENWEATHER_KEY")
WEATHER_CITY        = os.getenv("WEATHER_CITY", "Mumbai")   # Your city name

# ─────────────────────────────────────────────────────────
# News (NewsAPI)
# ─────────────────────────────────────────────────────────
# Free API key: https://newsapi.org/register
NEWSAPI_KEY  = os.getenv("NEWSAPI_KEY", "YOUR_NEWSAPI_KEY")
NEWS_COUNTRY = os.getenv("NEWS_COUNTRY", "in")   # "in"=India, "us"=USA, "gb"=UK

# ─────────────────────────────────────────────────────────
# Telegram Notifications
# ─────────────────────────────────────────────────────────
# 1. Create bot: Telegram -> @BotFather -> /newbot -> copy token
# 2. Get chat ID: https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "0")
TELEGRAM_POLLING   = False   # Set True to receive Telegram messages as FRIDAY commands

# ─────────────────────────────────────────────────────────
# Screenshot / OCR Settings
# ─────────────────────────────────────────────────────────
# Install Tesseract for OCR: https://github.com/UB-Mannheim/tesseract/wiki
SCREENSHOT_DIR      = os.path.join(os.path.dirname(__file__), "screenshots")
TESSERACT_PATH      = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

