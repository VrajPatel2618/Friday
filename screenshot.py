"""
screenshot.py - Screenshot & Screen Reader for FRIDAY

Voice commands (in commands.py):
  "Take a screenshot"
  "Read the screen"   -> OCR: reads all text visible on screen
  "What's on my screen?"
  "Screenshot"

Notes:
  - Screenshots saved to: screenshots/ folder in project dir
  - OCR requires Tesseract installed:
    Download: https://github.com/UB-Mannheim/tesseract/wiki
    Install to: C:/Program Files/Tesseract-OCR/
    Then it works automatically.
"""

import os
import time
from datetime import datetime

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Screenshot]: Pillow not installed — pip install pillow")

try:
    import pytesseract
    # Auto-detect Tesseract on Windows
    tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def take_screenshot(delay: float = 0.5) -> str:
    """Capture the full screen and save to screenshots/."""
    if not PIL_AVAILABLE:
        return "Pillow not installed. Run: pip install pillow"
    try:
        time.sleep(delay)   # brief delay so user can switch windows
        img  = ImageGrab.grab()
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"screenshot_{ts}.png")
        img.save(path)
        return f"Screenshot saved as screenshot_{ts}.png"
    except Exception as e:
        return f"Screenshot error: {e}"


def read_screen(max_chars: int = 400) -> str:
    """OCR the current screen and return readable text."""
    if not PIL_AVAILABLE:
        return "Pillow not installed. Run: pip install pillow"
    if not OCR_AVAILABLE:
        return ("OCR not available. Install pytesseract and Tesseract: "
                "https://github.com/UB-Mannheim/tesseract/wiki")

    try:
        img  = ImageGrab.grab()
        # Downscale for faster OCR
        w, h = img.size
        img  = img.resize((w // 2, h // 2), Image.LANCZOS)

        text = pytesseract.image_to_string(img).strip()
        if not text:
            return "No readable text found on screen."

        # Clean and truncate
        lines  = [l.strip() for l in text.splitlines() if l.strip()]
        result = " ".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "..."

        return f"I can see: {result}"
    except Exception as e:
        return f"Screen read error: {e}"


def screenshot_and_read() -> str:
    """Take screenshot AND read its text."""
    save_msg = take_screenshot()
    read_msg = read_screen()
    return f"{save_msg}. {read_msg}"


def open_screenshots_folder() -> str:
    """Open the screenshots folder in Explorer."""
    try:
        os.startfile(SCREENSHOT_DIR)
        return "Opening screenshots folder."
    except Exception:
        return f"Screenshots are saved in: {SCREENSHOT_DIR}"


if __name__ == "__main__":
    print(take_screenshot())
    print(read_screen())
