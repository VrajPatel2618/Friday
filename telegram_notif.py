"""
telegram_notif.py - Telegram Notifications for FRIDAY

Setup (one-time):
  1. Open Telegram -> search @BotFather -> send /newbot
  2. Follow steps -> copy your bot TOKEN
  3. Send a message to your bot (so it has your chat ID)
  4. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
     Find "chat":{"id":XXXXXXXXX} — that is your CHAT_ID
  5. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.py

Voice commands (in commands.py):
  "Send a message to Telegram: meeting at 3pm"
  "Send Telegram message: buy groceries"
  "Notify me: call mom at 5"
  "Send notification: server is down"

Incoming messages:
  FRIDAY checks Telegram every 30s for incoming messages
  and processes them as voice commands.
"""

import threading
import time
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _available() -> bool:
    return bool(
        TELEGRAM_BOT_TOKEN and not TELEGRAM_BOT_TOKEN.startswith("YOUR_")
        and TELEGRAM_CHAT_ID and str(TELEGRAM_CHAT_ID) != "0"
    )


def send_message(text: str) -> str:
    """Send a text message to your Telegram chat."""
    if not _available():
        return ("Telegram not configured. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.py.")
    try:
        resp = requests.post(
            f"{BASE}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=6
        )
        if resp.status_code == 200:
            return f"Message sent on Telegram: {text}"
        return f"Telegram error {resp.status_code}: {resp.text[:100]}"
    except requests.exceptions.ConnectionError:
        return "No internet connection for Telegram."
    except Exception as e:
        return f"Telegram send error: {e}"


def send_photo(image_path: str, caption: str = "") -> str:
    """Send a photo (e.g. screenshot) to your Telegram chat."""
    if not _available():
        return "Telegram not configured."
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{BASE}/sendPhoto",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"photo": f},
                timeout=10
            )
        if resp.status_code == 200:
            return "Photo sent on Telegram."
        return f"Telegram photo error {resp.status_code}."
    except Exception as e:
        return f"Telegram photo error: {e}"


# ─────────────────────────────────────────────────────────
# Incoming Message Poller (optional)
# ─────────────────────────────────────────────────────────

class TelegramPoller:
    """
    Polls Telegram for new messages and passes them to FRIDAY
    as if they were voice commands.
    """

    def __init__(self, command_callback=None, interval: float = 30.0):
        self._callback  = command_callback
        self._interval  = interval
        self._running   = False
        self._thread    = None
        self._offset    = 0

    def set_callback(self, fn):
        self._callback = fn

    def start(self):
        if not _available():
            print("[Telegram]: Not configured — polling disabled.")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[Telegram]: Polling for messages every {self._interval}s.")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                resp = requests.get(
                    f"{BASE}/getUpdates",
                    params={"offset": self._offset, "timeout": 5},
                    timeout=10
                )
                if resp.status_code == 200:
                    updates = resp.json().get("result", [])
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        msg = update.get("message", {})
                        chat_id = msg.get("chat", {}).get("id")
                        text    = msg.get("text", "").strip()
                        # Only process messages from our chat
                        if str(chat_id) == str(TELEGRAM_CHAT_ID) and text:
                            print(f"[Telegram]: Received: '{text}'")
                            if self._callback:
                                self._callback(text)
            except Exception as e:
                print(f"[Telegram]: Poll error — {e}")
            time.sleep(self._interval)


# Global poller instance
telegram_poller = TelegramPoller()


if __name__ == "__main__":
    print(send_message("FRIDAY is online and ready."))
