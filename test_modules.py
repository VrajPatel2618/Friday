"""
test_modules.py - Quick sanity check for all FRIDAY modules
Run this first to verify your installation before starting main.py
"""

import sys
import os

# Force UTF-8 output on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=" * 55)
print("  FRIDAY Module Check")
print("=" * 55)

PASS = "  [OK]  "
FAIL = "  [FAIL]"
WARN = "  [WARN]"

# ── config ────────────────────────────────────────────────
try:
    import config
    print(f"{PASS} config.py loaded | Backend: {config.AI_BACKEND}")
except Exception as e:
    print(f"{FAIL} config.py - {e}")
    sys.exit(1)

# ── memory ────────────────────────────────────────────────
try:
    import memory as mem
    mem.save_fact("TestUser", "test_key", "test_value")
    facts = mem.get_facts("TestUser")
    assert any(f["key"] == "test_key" for f in facts)
    print(f"{PASS} memory.py - JSON persistence OK")
except Exception as e:
    print(f"{FAIL} memory.py - {e}")

# ── SpeechRecognition ─────────────────────────────────────
try:
    import speech_recognition as sr
    r = sr.Recognizer()
    print(f"{PASS} SpeechRecognition v{sr.__version__} installed")
except ImportError:
    print(f"{FAIL} SpeechRecognition not installed  (pip install SpeechRecognition)")

# ── pyttsx3 ───────────────────────────────────────────────
try:
    import pyttsx3
    e = pyttsx3.init()
    print(f"{PASS} pyttsx3 TTS engine initialized")
except Exception as e:
    print(f"{FAIL} pyttsx3 - {e}")

# ── sounddevice (replaces PyAudio on Python 3.14) ─────────
try:
    import sounddevice as sd
    print(f"{PASS} sounddevice installed (microphone backend for Python 3.14)")
except ImportError:
    print(f"{WARN} sounddevice not installed  (pip install sounddevice)")

# ── PyAudio (legacy check) ────────────────────────────────
try:
    import pyaudio
    pa = pyaudio.PyAudio()
    pa.terminate()
    print(f"{PASS} PyAudio installed")
except ImportError:
    print(f"{WARN} PyAudio not installed - OK on Python 3.14 (sounddevice is used instead)")

# ── OpenAI ────────────────────────────────────────────────
try:
    import openai
    print(f"{PASS} openai v{openai.__version__} installed")
    if config.OPENAI_API_KEY.startswith("your-"):
        print(f"{WARN}        API key not set in config.py")
        print("         Edit config.py and set OPENAI_API_KEY = 'sk-...'")
        print("         OR: set OPENAI_API_KEY=sk-... in your environment")
except ImportError:
    print(f"{FAIL} openai not installed  (pip install openai)")

# ── NumPy ─────────────────────────────────────────────────
try:
    import numpy as np
    print(f"{PASS} NumPy v{np.__version__} installed")
except ImportError:
    print(f"{FAIL} numpy not installed  (pip install numpy)")

# ── OpenCV ────────────────────────────────────────────────
try:
    import cv2
    print(f"{PASS} OpenCV v{cv2.__version__} installed")
except ImportError:
    print(f"{WARN} opencv-python not installed  (pip install opencv-python)")

# ── MediaPipe ─────────────────────────────────────────────
try:
    import mediapipe as mp
    print(f"{PASS} MediaPipe v{mp.__version__} installed")
except ImportError:
    print(f"{WARN} mediapipe not installed  (pip install mediapipe)")

# ── PyAutoGUI ─────────────────────────────────────────────
try:
    import pyautogui
    w, h = pyautogui.size()
    print(f"{PASS} PyAutoGUI installed | Screen: {w}x{h}")
except ImportError:
    print(f"{WARN} pyautogui not installed  (pip install pyautogui)")

# ── face_recognition ──────────────────────────────────────
try:
    import face_recognition
    print(f"{PASS} face_recognition installed")
except ImportError:
    print(f"{WARN} face_recognition not installed")
    print("         Windows: pip install cmake dlib face_recognition")

# ── brain.py ──────────────────────────────────────────────
try:
    import brain
    print(f"{PASS} brain.py loaded | Backend: {config.AI_BACKEND}")
except Exception as e:
    print(f"{FAIL} brain.py - {e}")

# ── voice.py ──────────────────────────────────────────────
try:
    import voice
    print(f"{PASS} voice.py loaded")
except Exception as e:
    print(f"{FAIL} voice.py - {e}")

# ── emotion.py ────────────────────────────────────────────
try:
    import emotion
    print(f"{PASS} emotion.py loaded")
except Exception as e:
    print(f"{FAIL} emotion.py - {e}")

# ── gesture.py ────────────────────────────────────────────
try:
    from gesture import GESTURE_AVAILABLE
    status = "ready" if GESTURE_AVAILABLE else "dependencies missing"
    print(f"{PASS} gesture.py loaded ({status})")
except Exception as e:
    print(f"{FAIL} gesture.py - {e}")

# ── vision.py ─────────────────────────────────────────────
try:
    from vision import VISION_AVAILABLE, load_known_faces
    enc, names = load_known_faces()
    status = f"{len(names)} known face(s)" if VISION_AVAILABLE else "dependencies missing"
    print(f"{PASS} vision.py loaded ({status})")
except Exception as e:
    print(f"{FAIL} vision.py - {e}")

# ── commands.py ───────────────────────────────────────────
try:
    from commands import CommandHandler
    ch = CommandHandler()
    matched, _ = ch.handle("open notepad", "TestUser")
    print(f"{PASS} commands.py loaded (command match: {matched})")
except Exception as e:
    print(f"{FAIL} commands.py - {e}")

print("\n" + "=" * 55)
print("  Check complete.")
print("  Fix any [FAIL] errors before running main.py")
print("  [WARN] = optional feature, FRIDAY still works without it")
print("=" * 55)
