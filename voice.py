"""
voice.py - Speech input (STT) and output (TTS) for FRIDAY
Uses SpeechRecognition for STT and pyttsx3 for TTS.
Runs listener in a background thread for non-blocking input.

NOTE (Python 3.14 compatibility):
  PyAudio has no pre-built wheel for Python 3.14.
  SpeechRecognition will use 'sounddevice' as the audio backend instead.
  'sounddevice' is already installed and works identically.
  If you still see microphone errors, run: pip install sounddevice
"""

import time
import threading
import queue
import sys

# Patch PyAudio using PyAudioWPatch for Python 3.14 compatibility
try:
    import pyaudiowpatch
    sys.modules['pyaudio'] = pyaudiowpatch
except ImportError:
    pass

import speech_recognition as sr
import pyttsx3
from config import (
    VOICE_RATE, VOICE_VOLUME, VOICE_INDEX,
    LISTEN_TIMEOUT, PHRASE_LIMIT, ENERGY_THRESHOLD
)

# ─────────────────────────────────────────────────────────
# TTS Engine (singleton, thread-safe via lock)
# ─────────────────────────────────────────────────────────

_tts_lock = threading.Lock()
_tts_engine = pyttsx3.init()
_tts_engine.setProperty("rate", VOICE_RATE)
_tts_engine.setProperty("volume", VOICE_VOLUME)

# Set preferred voice
voices = _tts_engine.getProperty("voices")
if voices and VOICE_INDEX < len(voices):
    _tts_engine.setProperty("voice", voices[VOICE_INDEX].id)


def speak(text: str) -> None:
    """
    Speak the given text aloud using pyttsx3.
    Thread-safe: acquires a lock to prevent concurrent TTS calls.
    """
    print(f"[FRIDAY]: {text}")
    with _tts_lock:
        _tts_engine.say(text)
        _tts_engine.runAndWait()


# ─────────────────────────────────────────────────────────
# Speech Recognition
# ─────────────────────────────────────────────────────────

_recognizer = sr.Recognizer()
_recognizer.energy_threshold = ENERGY_THRESHOLD
_recognizer.dynamic_energy_threshold = True   # auto-adjust for ambient noise
_recognizer.pause_threshold = 0.8             # seconds of silence to end a phrase


def listen_once() -> str | None:
    """
    Listen for a single utterance and return the recognized text.
    Returns None on failure (timeout, unrecognized speech, etc.).
    """
    with sr.Microphone() as source:
        print("[Voice]: Listening...")
        try:
            # Brief ambient noise adjustment
            _recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = _recognizer.listen(
                source,
                timeout=LISTEN_TIMEOUT,
                phrase_time_limit=PHRASE_LIMIT
            )
        except sr.WaitTimeoutError:
            print("[Voice]: No speech detected (timeout).")
            return None

    try:
        text = _recognizer.recognize_google(audio)
        print(f"[User]: {text}")
        return text
    except sr.UnknownValueError:
        print("[Voice]: Could not understand speech.")
        return None
    except sr.RequestError as e:
        print(f"[Voice]: Google STT service error — {e}")
        return None


# ─────────────────────────────────────────────────────────
# Continuous Background Listener
# ─────────────────────────────────────────────────────────

class VoiceListener:
    """
    Runs a continuous speech listener in a background thread.
    Recognized phrases are placed into a thread-safe queue for the
    main loop to consume without blocking.
    """

    def __init__(self):
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._is_speaking = False  # Pause listening while FRIDAY speaks

    def start(self) -> None:
        """Start the background listener thread."""
        if self._thread and self._thread.is_alive():
            return  # Already running
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Voice]: Background listener started.")

    def stop(self) -> None:
        """Signal the background listener to stop."""
        self._stop_event.set()
        print("[Voice]: Background listener stopped.")

    def set_speaking(self, speaking: bool) -> None:
        """Pause/resume listening while FRIDAY is speaking."""
        self._is_speaking = speaking

    def get(self, timeout: float = 0.1) -> str | None:
        """
        Non-blocking retrieval of the next recognized phrase.
        Returns None if the queue is empty.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _loop(self) -> None:
        """Internal listening loop running in background thread."""
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = ENERGY_THRESHOLD
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8

        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print("[Voice]: Calibrated to ambient noise.")

            while not self._stop_event.is_set():
                if self._is_speaking:
                    time.sleep(0.1)
                    continue
                try:
                    audio = recognizer.listen(
                        source,
                        timeout=LISTEN_TIMEOUT,
                        phrase_time_limit=PHRASE_LIMIT
                    )
                    text = recognizer.recognize_google(audio)
                    print(f"[User]: {text}")
                    self._queue.put(text)
                except sr.WaitTimeoutError:
                    pass   # No speech; keep looping
                except sr.UnknownValueError:
                    pass   # Unrecognized; keep looping
                except sr.RequestError as e:
                    print(f"[Voice]: STT error — {e}")
                    time.sleep(2)
                except Exception as e:
                    print(f"[Voice]: Unexpected error — {e}")
                    time.sleep(1)


# ─────────────────────────────────────────────────────────
# Thread-safe speak wrapper that pauses the listener
# ─────────────────────────────────────────────────────────

def speak_with_listener(text: str, listener: VoiceListener) -> None:
    """
    Speak text while temporarily pausing the background listener
    so FRIDAY doesn't accidentally hear its own voice.
    """
    listener.set_speaking(True)
    speak(text)
    listener.set_speaking(False)
