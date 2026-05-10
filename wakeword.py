"""
wakeword.py - Wake Word Detection for FRIDAY
Uses Picovoice Porcupine for offline "Hey FRIDAY" detection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Install: pip install pvporcupine pvrecorder
2. Get a FREE access key at: https://console.picovoice.ai
3. Set PORCUPINE_ACCESS_KEY in config.py

FALLBACK MODE (no API key):
  Uses SpeechRecognition to listen for "hey friday" via Google STT.
  Works but requires internet + is slower than Porcupine.

RUN STANDALONE:
  python wakeword.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import threading
import time
import sys

# ── Porcupine (preferred — offline, fast) ─────────────────
try:
    import pvporcupine
    from pvrecorder import PvRecorder
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    print("[WakeWord]: pvporcupine/pvrecorder not installed.")
    print("           Install: pip install pvporcupine pvrecorder")

# ── SpeechRecognition fallback ────────────────────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

from config import PORCUPINE_ACCESS_KEY, WAKE_WORD_SENSITIVITY


# ─────────────────────────────────────────────────────────
# Porcupine-based Wake Word Detector
# ─────────────────────────────────────────────────────────

class PorcupineWakeWord:
    """
    Uses pvporcupine for offline, low-latency wake word detection.
    Detects "friday" (built-in keyword).
    On detection, calls the registered callback.
    """

    def __init__(self, callback=None):
        self._callback = callback
        self._running  = False
        self._thread   = None
        self._porcupine = None
        self._recorder  = None

    def set_callback(self, fn):
        """Register a function to call when wake word is detected."""
        self._callback = fn

    def start(self) -> None:
        if not PORCUPINE_AVAILABLE:
            print("[WakeWord]: Porcupine unavailable — cannot start.")
            return
        if not PORCUPINE_ACCESS_KEY or PORCUPINE_ACCESS_KEY.startswith("YOUR_"):
            print("[WakeWord]: No Porcupine access key in config.py.")
            print("           Get a free key at: https://console.picovoice.ai")
            return
        if self._thread and self._thread.is_alive():
            return

        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[WakeWord]: Porcupine started — say "Hey FRIDAY" to activate.')

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        try:
            self._porcupine = pvporcupine.create(
                access_key=PORCUPINE_ACCESS_KEY,
                keywords=["friday"],
                sensitivities=[WAKE_WORD_SENSITIVITY]
            )
            self._recorder = PvRecorder(
                device_index=-1,                       # default mic
                frame_length=self._porcupine.frame_length
            )
            self._recorder.start()
            print("[WakeWord]: Listening for 'Friday'...")

            while self._running:
                pcm = self._recorder.read()
                result = self._porcupine.process(pcm)
                if result >= 0:
                    print("[WakeWord]: ✅ Wake word detected!")
                    if self._callback:
                        self._callback()

        except pvporcupine.PorcupineInvalidArgumentError as e:
            print(f"[WakeWord]: Invalid access key — {e}")
        except Exception as e:
            print(f"[WakeWord]: Error — {e}")
        finally:
            if self._recorder:
                self._recorder.delete()
            if self._porcupine:
                self._porcupine.delete()
            print("[WakeWord]: Porcupine stopped.")


# ─────────────────────────────────────────────────────────
# STT Fallback Wake Word Detector
# ─────────────────────────────────────────────────────────

class STTWakeWord:
    """
    Fallback wake word detector using Google STT.
    Listens continuously and fires callback when 'friday' is spoken.
    Slower and requires internet, but needs no API key.
    """

    TRIGGER_WORDS = ["friday", "hey friday", "ok friday", "yo friday"]

    def __init__(self, callback=None):
        self._callback = callback
        self._running  = False
        self._thread   = None

    def set_callback(self, fn):
        self._callback = fn

    def start(self) -> None:
        if not SR_AVAILABLE:
            print("[WakeWord]: SpeechRecognition not installed.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[WakeWord]: STT fallback started — say "Friday" to activate.')

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 250
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.5

        while self._running:
            try:
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=3)
                text = recognizer.recognize_google(audio).lower()
                print(f"[WakeWord]: Heard: '{text}'")
                if any(trigger in text for trigger in self.TRIGGER_WORDS):
                    print("[WakeWord]: ✅ Wake word detected (STT fallback)!")
                    if self._callback:
                        self._callback()
            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"[WakeWord]: STT error — {e}")
                time.sleep(3)
            except Exception as e:
                print(f"[WakeWord]: Unexpected error — {e}")
                time.sleep(1)


# ─────────────────────────────────────────────────────────
# Unified Wake Word Manager
# ─────────────────────────────────────────────────────────

class WakeWordManager:
    """
    Auto-selects the best available wake word engine:
      1. Porcupine (offline, fast) — if pvporcupine installed + access key set
      2. STT fallback (Google STT) — if only speech_recognition is available

    Usage:
        ww = WakeWordManager()
        ww.set_callback(lambda: print("Wake word heard!"))
        ww.start()
    """

    def __init__(self, callback=None):
        self._callback = callback
        key = PORCUPINE_ACCESS_KEY

        if PORCUPINE_AVAILABLE and key and not key.startswith("YOUR_"):
            self._engine = PorcupineWakeWord(callback)
            self._mode   = "porcupine"
        elif SR_AVAILABLE:
            self._engine = STTWakeWord(callback)
            self._mode   = "stt_fallback"
        else:
            self._engine = None
            self._mode   = "none"
            print("[WakeWord]: No wake word engine available.")

    def set_callback(self, fn):
        self._callback = fn
        if self._engine:
            self._engine.set_callback(fn)

    def start(self) -> None:
        if self._engine:
            self._engine.start()
        else:
            print("[WakeWord]: Cannot start — no engine available.")

    def stop(self) -> None:
        if self._engine:
            self._engine.stop()

    @property
    def mode(self) -> str:
        return self._mode


# ─────────────────────────────────────────────────────────
# Standalone entry point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  FRIDAY Wake Word — Standalone Test")
    print("=" * 50)

    detected_count = 0

    def on_wake():
        global detected_count
        detected_count += 1
        print(f'[Test]: Wake word #{detected_count} detected! FRIDAY is listening...')

    ww = WakeWordManager(callback=on_wake)
    print(f"[Test]: Using engine: {ww.mode}")
    ww.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ww.stop()
        print(f"\n[Test]: Stopped. Detected {detected_count} wake word(s).")
