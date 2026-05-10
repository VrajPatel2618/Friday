"""
clipboard_mgr.py - Clipboard Manager for FRIDAY

Voice commands (in commands.py):
  "What did I copy?"  /  "Read clipboard"
  "Copy this: meeting at 3pm"
  "Clear clipboard"
  "Save clipboard"    -> saves to clipboard_history.txt
  "Show clipboard history"
"""

import os
from datetime import datetime

try:
    import pyperclip
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    print("[Clipboard]: pyperclip not installed — pip install pyperclip")

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "clipboard_history.txt")


def read_clipboard() -> str:
    if not CLIP_AVAILABLE:
        return "Clipboard module not installed."
    try:
        text = pyperclip.paste()
        if not text or not text.strip():
            return "Clipboard is empty."
        text = text.strip()
        if len(text) > 300:
            return f"Clipboard contains: {text[:300]}... and more."
        return f"Clipboard contains: {text}"
    except Exception as e:
        return f"Clipboard read error: {e}"


def write_clipboard(text: str) -> str:
    if not CLIP_AVAILABLE:
        return "Clipboard module not installed."
    try:
        pyperclip.copy(text)
        return f"Copied to clipboard: {text}"
    except Exception as e:
        return f"Clipboard write error: {e}"


def clear_clipboard() -> str:
    if not CLIP_AVAILABLE:
        return "Clipboard module not installed."
    try:
        pyperclip.copy("")
        return "Clipboard cleared."
    except Exception as e:
        return f"Clear error: {e}"


def save_clipboard() -> str:
    """Save current clipboard content to history file."""
    if not CLIP_AVAILABLE:
        return "Clipboard module not installed."
    try:
        text = pyperclip.paste().strip()
        if not text:
            return "Clipboard is empty, nothing to save."
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]\n{text}\n{'─'*40}\n")
        return "Clipboard content saved to history."
    except Exception as e:
        return f"Save error: {e}"


def get_history(count: int = 5) -> str:
    """Read recent clipboard history entries."""
    if not os.path.exists(HISTORY_FILE):
        return "No clipboard history yet. Say 'save clipboard' to start saving."
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        entries = [e.strip() for e in content.split("─"*40) if e.strip()]
        if not entries:
            return "Clipboard history is empty."
        recent  = entries[-count:]
        return f"Last {len(recent)} clipboard entries: " + \
               " | ".join(e.split("\n")[1][:60] for e in recent if "\n" in e)
    except Exception as e:
        return f"History read error: {e}"


if __name__ == "__main__":
    write_clipboard("Hello from FRIDAY!")
    print(read_clipboard())
    save_clipboard()
