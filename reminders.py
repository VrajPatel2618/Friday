"""
reminders.py - Alarm & Reminder System for FRIDAY
No extra packages needed — uses Python threading.Timer.

Voice commands (handled in commands.py):
  "Remind me in 10 minutes to take a break"
  "Set an alarm for 5 minutes"
  "Remind me in 1 hour to call mom"
  "Set reminder for 30 seconds to check the oven"
  "What are my reminders?"
  "Cancel all reminders"
  "Cancel reminder 1"
"""

import threading
import time
import re
from datetime import datetime, timedelta
from typing import Callable


# ─────────────────────────────────────────────────────────
# Reminder Store
# ─────────────────────────────────────────────────────────

class ReminderManager:
    """
    Manages timed reminders. Fires a callback (FRIDAY speaks the reminder)
    when the timer expires.
    """

    def __init__(self, speak_callback: Callable[[str], None] = None):
        self._speak   = speak_callback or print
        self._reminders: dict[int, dict] = {}   # id -> {timer, message, due}
        self._lock    = threading.Lock()
        self._next_id = 1

    def set_speak(self, fn: Callable[[str], None]):
        """Register the FRIDAY speak function."""
        self._speak = fn

    # ── Public API ────────────────────────────────────────

    def add(self, message: str, seconds: float) -> str:
        """
        Schedule a reminder.
        Returns a confirmation string e.g. "Reminder set for 10 minutes."
        """
        due = datetime.now() + timedelta(seconds=seconds)

        with self._lock:
            rid = self._next_id
            self._next_id += 1

        timer = threading.Timer(seconds, self._fire, args=(rid, message))
        timer.daemon = True
        timer.start()

        with self._lock:
            self._reminders[rid] = {
                "timer":   timer,
                "message": message,
                "due":     due,
                "id":      rid
            }

        human_time = _seconds_to_human(seconds)
        msg = f"Reminder set for {human_time}: {message}."
        print(f"[Reminder #{rid}]: {msg}")
        return msg

    def list_reminders(self) -> str:
        """Return a spoken list of all pending reminders."""
        with self._lock:
            active = {k: v for k, v in self._reminders.items()}

        if not active:
            return "You have no pending reminders."

        lines = [f"You have {len(active)} reminder(s)."]
        for rid, r in sorted(active.items()):
            due_str = r["due"].strftime("%H:%M:%S")
            lines.append(f"Reminder {rid}: {r['message']} at {due_str}.")

        return " ".join(lines)

    def cancel(self, rid: int) -> str:
        """Cancel a specific reminder by ID."""
        with self._lock:
            r = self._reminders.pop(rid, None)

        if not r:
            return f"No reminder found with ID {rid}."

        r["timer"].cancel()
        return f"Reminder {rid} cancelled: {r['message']}."

    def cancel_all(self) -> str:
        """Cancel all pending reminders."""
        with self._lock:
            reminders = dict(self._reminders)
            self._reminders.clear()

        for r in reminders.values():
            r["timer"].cancel()

        if not reminders:
            return "No reminders to cancel."
        return f"Cancelled {len(reminders)} reminder(s)."

    def count(self) -> int:
        with self._lock:
            return len(self._reminders)

    # ── Internal ──────────────────────────────────────────

    def _fire(self, rid: int, message: str):
        """Called by timer when reminder is due."""
        with self._lock:
            self._reminders.pop(rid, None)

        alert = f"Reminder alert! {message}"
        print(f"\n[REMINDER #{rid}]: {alert}")
        self._speak(alert)


# ─────────────────────────────────────────────────────────
# Time Parsing
# ─────────────────────────────────────────────────────────

def parse_reminder(text: str) -> tuple[str | None, float | None]:
    """
    Parse voice text to extract (message, seconds).

    Examples:
      "remind me in 10 minutes to take a break"
        -> ("take a break", 600)
      "set alarm for 5 minutes"
        -> ("Alarm", 300)
      "remind me in 1 hour 30 minutes to call mom"
        -> ("call mom", 5400)
      "remind me in 30 seconds to check oven"
        -> ("check oven", 30)
    """
    t = text.lower()

    # Extract total seconds
    seconds = 0.0
    found_time = False

    # Hours
    m = re.search(r'(\d+)\s*hour', t)
    if m:
        seconds    += int(m.group(1)) * 3600
        found_time  = True

    # Minutes
    m = re.search(r'(\d+)\s*min', t)
    if m:
        seconds    += int(m.group(1)) * 60
        found_time  = True

    # Seconds
    m = re.search(r'(\d+)\s*sec', t)
    if m:
        seconds    += int(m.group(1))
        found_time  = True

    if not found_time:
        return None, None

    # Extract message (after "to" keyword)
    message = "Reminder"
    if " to " in t:
        # Take everything after the last "to"
        message = t.split(" to ")[-1].strip().capitalize()
    elif "alarm" in t:
        message = "Alarm"

    return message, seconds


def _seconds_to_human(seconds: float) -> str:
    """Convert seconds to human-readable string."""
    s = int(seconds)
    parts = []
    if s >= 3600:
        h = s // 3600
        s %= 3600
        parts.append(f"{h} hour{'s' if h > 1 else ''}")
    if s >= 60:
        m = s // 60
        s %= 60
        parts.append(f"{m} minute{'s' if m > 1 else ''}")
    if s > 0:
        parts.append(f"{s} second{'s' if s > 1 else ''}")
    return " and ".join(parts) if parts else "now"


# ─────────────────────────────────────────────────────────
# Global instance (shared across modules)
# ─────────────────────────────────────────────────────────

reminder_manager = ReminderManager()


if __name__ == "__main__":
    def say(text): print(f"[FRIDAY]: {text}")
    reminder_manager.set_speak(say)

    # Test
    reminder_manager.add("Take a break", 5)
    reminder_manager.add("Drink water", 8)
    print(reminder_manager.list_reminders())
    time.sleep(10)
    print("Done.")
