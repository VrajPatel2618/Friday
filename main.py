"""
main.py - FRIDAY AI Assistant — Main Loop
Orchestrates all modules: voice, brain, memory, emotion, gesture, vision.
"""

import sys
import time
import threading

# Force UTF-8 output on Windows terminals to prevent UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Module imports ────────────────────────────────────────
import config
import memory as mem
import brain
import voice as v
from emotion import EmotionManager
from gesture import GestureController, GESTURE_AVAILABLE
from head import HeadController, HEAD_AVAILABLE
from vision import load_known_faces, FaceRecognitionManager, VISION_AVAILABLE
from commands import CommandHandler
from wakeword import WakeWordManager
from dashboard import FridayDashboard
from reminders import reminder_manager
from telegram_notif import telegram_poller
import config



# ─────────────────────────────────────────────────────────
# FRIDAY Core
# ─────────────────────────────────────────────────────────

class FRIDAY:
    """
    Central orchestrator.

    Startup sequence:
      1. Load known faces -> identify user
      2. Load user memory
      3. Start emotion detector
      4. Start voice listener
      5. Greet user
      6. Enter main listen -> process -> respond loop
    """

    def __init__(self):
        self._running = False
        self._current_user = "User"
        self._wake_word_active = threading.Event()

        # Modules
        self._listener = v.VoiceListener()
        self._emotion  = EmotionManager(use_face=False)
        self._gesture  = GestureController() if GESTURE_AVAILABLE else None
        self._head     = HeadController()    if HEAD_AVAILABLE    else None
        self._gesture_active = False
        self._head_active    = False
        self._cmd_handler = CommandHandler()

        # Dashboard
        self._dashboard: FridayDashboard | None = None
        if config.USE_DASHBOARD:
            self._dashboard = FridayDashboard(
                on_close_callback=lambda: print("[Dashboard]: Window closed.")
            )

        # Wake word
        self._wake_word = WakeWordManager(
            callback=self._on_wake_word
        )

        # Register callbacks
        self._cmd_handler.register(
            on_gesture_start=self._start_gesture,
            on_gesture_stop=self._stop_gesture,
            on_head_start=self._start_head,
            on_head_stop=self._stop_head,
            on_clear_memory=self._clear_memory,
            on_quit=self._quit
        )

        # Face recognition
        self._known_encodings, self._known_names = load_known_faces()
        self._face_manager: FaceRecognitionManager | None = None

    # ── Gesture helpers ───────────────────────────────────

    def _start_gesture(self):
        if self._gesture and not self._gesture_active:
            self._gesture.start()
            self._gesture_active = True

    def _stop_gesture(self):
        if self._gesture and self._gesture_active:
            self._gesture.stop()
            self._gesture_active = False

    def _start_head(self):
        if self._head and not self._head_active:
            self._head.start()
            self._head_active = True

    def _stop_head(self):
        if self._head and self._head_active:
            self._head.stop()
            self._head_active = False

    def _clear_memory(self):
        mem.clear_conversation(self._current_user)

    def _quit(self):
        self._running = False

    # ── Wake word callback ────────────────────────────────────

    def _on_wake_word(self):
        """Called by WakeWordManager when wake word is detected."""
        if not self._listener._is_speaking:
            print("[FRIDAY]: Wake word detected — listening for command.")
            self._wake_word_active.set()
            # Play a short audio cue via TTS
            v.speak("Yes?")
            self._wake_word_active.clear()

    # ── Speak helper ──────────────────────────────────────

    def _say(self, text: str):
        """Speak and print, pausing the listener to avoid self-hearing."""
        if self._dashboard:
            self._dashboard.log("FRIDAY", text)
        v.speak_with_listener(text, self._listener)

    # ── User identification ───────────────────────────────

    def _identify_user(self) -> str:
        """
        Attempt face recognition; fall back to voice introduction.
        """
        if VISION_AVAILABLE and self._known_encodings:
            print("[FRIDAY]: Scanning for known faces...")
            self._say("One moment while I identify you.")
            from vision import recognize_user
            name = recognize_user(self._known_encodings, self._known_names)
            if name != "Unknown":
                return name

        # Fallback: ask for name
        self._say("I don't recognize you yet. What's your name?")
        for _ in range(3):
            raw = v.listen_once()
            if raw:
                # Extract first capitalized word as name
                words = raw.strip().split()
                for word in words:
                    if len(word) > 1:
                        name = word.capitalize()
                        mem.save_preference(name, "preferred_name", name)
                        return name
        return "User"

    # ── Main startup ──────────────────────────────────────

    def run(self):
        """Start FRIDAY and enter the main loop."""
        print(f"\n{'='*50}")
        print(f"  {config.ASSISTANT_NAME} — AI Personal Assistant")
        print(f"  Backend: {config.AI_BACKEND.upper()}")
        print(f"{'='*50}\n")

        self._running = True

        # Step 1: Identify user
        self._current_user = self._identify_user()
        print(f"[FRIDAY]: Active user -> {self._current_user}")

        # Step 2: Detect AI backend (online/offline)
        ai_status = brain.get_status()
        print(f"[FRIDAY]: AI backend  -> {ai_status}")

        # Step 3: Load memory
        user_memory = mem.load_memory(self._current_user)
        print(f"[FRIDAY]: Memory loaded for '{self._current_user}'")

        # Step 3: Start emotion detection
        self._emotion.start()

        # Step 4: Start background face recognition (updates every 30s)
        if VISION_AVAILABLE and self._known_encodings:
            self._face_manager = FaceRecognitionManager(
                self._known_encodings, self._known_names, interval=30.0
            )
            self._face_manager.start()

        # Step 5: Start background voice listener
        self._listener.start()

        # Step 5b: Start wake word detector (if configured)
        if config.USE_WAKE_WORD:
            self._wake_word.start()
            print(f"[FRIDAY]: Wake word engine -> {self._wake_word.mode}")

        # Step 5c: Launch dashboard
        if self._dashboard:
            self._dashboard.start()
            self._dashboard.log("SYSTEM", "FRIDAY dashboard online.")
            self._dashboard.set_status(
                user=self._current_user,
                backend=ai_status
            )

        # Step 5d: Wire reminder manager speak callback
        reminder_manager.set_speak(self._say)
        print("[FRIDAY]: Reminder system ready.")

        # Step 5e: Start Telegram poller (if configured)
        if config.TELEGRAM_POLLING:
            telegram_poller.set_callback(
                lambda text: self._listener._queue.put(text)
            )
            telegram_poller.start()

        # Step 5f: Start gesture and head tracking automatically
        self._start_gesture()
        self._start_head()

        # Step 6: Greet user
        greeting = self._build_greeting(user_memory)
        self._say(greeting)

        # ── Main loop ─────────────────────────────────────
        print("\n[FRIDAY]: Listening... (say 'Exit FRIDAY' to quit)\n")

        while self._running:
            try:
                text = self._listener.get(timeout=0.2)
                if not text:
                    # Periodically sync face-recognized user
                    if self._face_manager:
                        recognized = self._face_manager.get_current_user()
                        if recognized != "Unknown" and recognized != self._current_user:
                            self._current_user = recognized
                            self._say(f"Hello {self._current_user}! Switching to your profile.")
                            mem.load_memory(self._current_user)
                    continue

                emotion = self._emotion.get_emotion()
                print(f"[State]: User={self._current_user}  Emotion={emotion}")

                # Update dashboard state
                if self._dashboard:
                    self._dashboard.set_status(
                        user=self._current_user,
                        emotion=emotion,
                        gesture=self._gesture_active,
                        head=self._head_active,
                        vision=bool(self._face_manager),
                    )

                self._process_input(text, emotion)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[FRIDAY]: Unexpected error — {e}")
                time.sleep(0.5)

        self._shutdown()

    # ── Input processing ──────────────────────────────────

    def _process_input(self, text: str, emotion: str):
        """
        Route input through:
          1. Hardcoded command handler
          2. Memory recall shortcut
          3. AI brain
        """
        # 1. Hardcoded commands
        matched, cmd_response = self._cmd_handler.handle(text, self._current_user)
        if matched:
            if cmd_response:
                self._say(cmd_response)
            return

        # 2. Memory recall shortcut
        if brain.is_recall_query(text):
            recall = mem.recall_memory(self._current_user)
            self._say(recall)
            return

        # 3. Route to AI
        response = brain.ask_ai(
            prompt=text,
            user=self._current_user,
            emotion=emotion
        )
        self._say(response)

    # ── Greeting builder ──────────────────────────────────

    def _build_greeting(self, user_memory: dict) -> str:
        """Build a personalized greeting using stored memory."""
        from datetime import datetime
        hour = datetime.now().hour

        if hour < 12:
            period = "Good morning"
        elif hour < 17:
            period = "Good afternoon"
        else:
            period = "Good evening"

        name = self._current_user
        prefs = user_memory.get("preferences", {})
        occupation = prefs.get("occupation", "")

        if occupation:
            return (f"{period}, {name}! FRIDAY online and fully operational. "
                    f"Ready to assist you with your work as a {occupation}.")
        elif user_memory.get("facts"):
            return (f"{period}, {name}! Great to see you again. "
                    f"I have your profile loaded. How can I assist you today?")
        else:
            return (f"{period}! I'm {config.ASSISTANT_NAME}, your AI assistant. "
                    f"I'm online and ready to help. What can I do for you?")

    # ── Graceful shutdown ─────────────────────────────────

    def _shutdown(self):
        """Clean up all modules before exiting."""
        print("\n[FRIDAY]: Shutting down...")
        self._listener.stop()
        self._emotion.stop()
        if self._wake_word:
            self._wake_word.stop()
        if self._gesture and self._gesture_active:
            self._gesture.stop()
        if self._face_manager:
            self._face_manager.stop()
        if self._dashboard:
            self._dashboard.stop()
        print("[FRIDAY]: All systems offline. Goodbye.")


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    assistant = FRIDAY()
    assistant.run()
