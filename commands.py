"""
commands.py - Voice Command Handler for FRIDAY
Handles all hardcoded system commands spoken by the user.
All other input is routed to the AI (brain.py).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE COMMANDS YOU CAN SAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APP CONTROL:
  "Open Chrome / Notepad / Calculator / Spotify..."
  "Close this window"
  "Minimize window"
  "Maximize window"
  "Switch window"  (Alt+Tab)

SYSTEM:
  "Shutdown the computer"
  "Restart the computer"
  "Lock the screen"
  "Take a screenshot"
  "Volume up / down / mute"
  "Increase brightness / decrease brightness"

MEDIA:
  "Play / Pause"
  "Next song"
  "Previous song"
  "Mute / Unmute"

MOUSE & KEYBOARD:
  "Click"
  "Right click"
  "Double click"
  "Scroll up / down"
  "Press Enter / Escape / Space / Tab"
  "Copy / Paste / Cut / Undo / Redo"
  "Select all"
  "Go back"

BROWSER:
  "Open YouTube"
  "Open Google"
  "Open GitHub"
  "New tab"
  "Close tab"
  "Refresh page"

FRIDAY CONTROL:
  "Start / Stop gesture control"
  "Start / Stop head control"
  "Clear conversation"
  "What do you know about me"
  "Exit FRIDAY"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import subprocess
import platform
import time
import webbrowser
import re
from typing import Callable

# ── New feature modules ───────────────────────────────────
from weather       import get_current_weather, get_forecast, will_it_rain
from news          import parse_and_fetch as fetch_news
from reminders     import reminder_manager, parse_reminder
from volume_ctrl   import parse_and_set as vol_cmd
from clipboard_mgr import (read_clipboard, write_clipboard,
                            clear_clipboard, save_clipboard, get_history)
from screenshot    import take_screenshot, read_screen, open_screenshots_folder
from telegram_notif import send_message as tg_send, telegram_poller

from config import HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN


# ─────────────────────────────────────────────────────────
# Smart Home Helpers (Home Assistant REST API)
# ─────────────────────────────────────────────────────────

# ── Entity discovery cache ────────────────────────────────
# Populated once on first smart home call; maps voice keywords -> entity_ids
_HA_ENTITY_CACHE: dict[str, list[str]] = {}   # domain -> [entity_id, ...]
_HA_NAME_MAP:     dict[str, str]       = {}   # friendly_name.lower() -> entity_id
_CACHE_LOADED = False

# ── Static overrides — edit to match YOUR device entity IDs ──────
# These take priority over auto-discovered entities.
# Find entity IDs at: http://<HA_IP>:8123/developer-tools/state
ENTITY_OVERRIDES: dict[str, str] = {
    # keyword       : entity_id
    # "living room" : "light.living_room",
    # "bedroom"     : "light.bedroom",
    # "ac"          : "switch.air_conditioner",
    # "fan"         : "switch.ceiling_fan",
    # "front_door"  : "lock.front_door",
    # "thermostat"  : "climate.home",
}


def _ha_available() -> bool:
    """Return True if Home Assistant is configured in config.py."""
    return bool(HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN)


def _ha_headers() -> dict:
    return {
        "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
        "Content-Type":  "application/json"
    }


def _load_entity_cache() -> None:
    """
    Fetch all HA states once and build:
      _HA_ENTITY_CACHE : domain -> list of entity_ids
      _HA_NAME_MAP     : friendly name -> entity_id
    """
    global _HA_ENTITY_CACHE, _HA_NAME_MAP, _CACHE_LOADED
    if _CACHE_LOADED or not _ha_available():
        return

    import requests as req
    try:
        resp = req.get(f"{HOME_ASSISTANT_URL}/api/states",
                       headers=_ha_headers(), timeout=6)
        if resp.status_code != 200:
            return

        for state in resp.json():
            eid    = state["entity_id"]
            domain = eid.split(".")[0]
            name   = state.get("attributes", {}).get("friendly_name", eid).lower()

            _HA_ENTITY_CACHE.setdefault(domain, []).append(eid)
            _HA_NAME_MAP[name] = eid
            # Also index by the entity slug (after dot)
            _HA_NAME_MAP[eid.split(".")[1].replace("_", " ")] = eid

        _CACHE_LOADED = True
        total = sum(len(v) for v in _HA_ENTITY_CACHE.values())
        print(f"[SmartHome]: Loaded {total} entities from Home Assistant.")

    except Exception as e:
        print(f"[SmartHome]: Could not load entity cache — {e}")


def _resolve_entity(keyword: str, domain: str) -> str:
    """
    Resolve a voice keyword to a real HA entity_id.
    Priority:
      1. ENTITY_OVERRIDES (manual)
      2. Exact friendly-name match
      3. Substring friendly-name match
      4. First entity in the domain (fallback)
      5. domain.keyword (last resort)
    """
    _load_entity_cache()
    keyword_l = keyword.lower().replace("_", " ")

    # 1. Manual override
    if keyword_l in ENTITY_OVERRIDES:
        return ENTITY_OVERRIDES[keyword_l]

    # 2. Exact name match
    if keyword_l in _HA_NAME_MAP:
        return _HA_NAME_MAP[keyword_l]

    # 3. Substring match in friendly names
    for name, eid in _HA_NAME_MAP.items():
        if keyword_l in name and eid.startswith(domain):
            return eid

    # 4. First entity in domain (if keyword is "all" or no match)
    if domain in _HA_ENTITY_CACHE and _HA_ENTITY_CACHE[domain]:
        if keyword_l in ("all", "lights", "switches"):
            # Return all entities of this domain as a list string
            return ",".join(_HA_ENTITY_CACHE[domain])
        return _HA_ENTITY_CACHE[domain][0]

    # 5. Last resort
    return f"{domain}.{keyword.replace(' ', '_')}"


def _call_ha(url: str, payload: dict) -> tuple[bool, str]:
    """Make a POST request to HA API. Returns (success, message)."""
    import requests as req
    try:
        resp = req.post(url, json=payload, headers=_ha_headers(), timeout=5)
        return resp.status_code in (200, 201), resp.text
    except req.exceptions.ConnectionError:
        return False, "Cannot reach Home Assistant. Is it running on your network?"
    except Exception as e:
        return False, f"Smart home error: {e}"


def _smart_home_call(domain: str, service: str, entity: str,
                     extra: dict = None) -> str | None:
    """
    Call a Home Assistant service for a resolved entity.

    Args:
        domain:  e.g. 'light', 'switch', 'lock'
        service: e.g. 'turn_on', 'turn_off', 'lock'
        entity:  voice keyword e.g. 'all', 'fan', 'bedroom', 'front_door'
        extra:   optional extra payload e.g. {'brightness_pct': 30}
    """
    if not _ha_available():
        return None

    entity_id = _resolve_entity(entity, domain)
    url       = f"{HOME_ASSISTANT_URL}/api/services/{domain}/{service}"
    payload   = {"entity_id": entity_id}
    if extra:
        payload.update(extra)

    ok, msg = _call_ha(url, payload)
    if ok:
        action = service.replace("_", " ").title()
        label  = entity.replace("_", " ").title()
        return f"{action}: {label} — done."
    return msg


def _smart_home_scene(scene_name: str) -> str | None:
    """Activate a Home Assistant scene by name or fuzzy match."""
    if not _ha_available():
        return None

    _load_entity_cache()

    # Try to find scene by keyword
    scene_id = _resolve_entity(scene_name, "scene")
    url  = f"{HOME_ASSISTANT_URL}/api/services/scene/turn_on"
    ok, _ = _call_ha(url, {"entity_id": scene_id})
    if ok:
        return f"Scene '{scene_name.replace('_', ' ').title()}' activated."
    return f"Could not activate scene '{scene_name}'."


def _smart_home_set_temp(temp_celsius: int) -> str | None:
    """Set climate/thermostat temperature."""
    if not _ha_available():
        return None

    _load_entity_cache()
    climate_id = _resolve_entity("thermostat", "climate")
    url  = f"{HOME_ASSISTANT_URL}/api/services/climate/set_temperature"
    ok, _ = _call_ha(url, {"entity_id": climate_id, "temperature": temp_celsius})
    if ok:
        return f"Thermostat set to {temp_celsius} degrees."
    return f"Could not set thermostat."


def _smart_home_status(keyword: str) -> str | None:
    """Get the current state of a device."""
    if not _ha_available():
        return None

    _load_entity_cache()
    import requests as req

    # Try to find matching entity
    keyword_l = keyword.lower()
    entity_id = None
    for name, eid in _HA_NAME_MAP.items():
        if keyword_l in name:
            entity_id = eid
            break

    if not entity_id:
        return f"Could not find device matching '{keyword}'."

    try:
        resp = req.get(f"{HOME_ASSISTANT_URL}/api/states/{entity_id}",
                       headers=_ha_headers(), timeout=5)
        if resp.status_code == 200:
            data  = resp.json()
            name  = data.get("attributes", {}).get("friendly_name", entity_id)
            state = data.get("state", "unknown")
            return f"{name} is currently {state}."
        return f"Could not get state for {entity_id}."
    except Exception as e:
        return f"Status check error: {e}"






# ─────────────────────────────────────────────────────────
# App name -> launch command
# ─────────────────────────────────────────────────────────


APP_MAP = {
    # Browsers
    "chrome":           "start chrome",
    "google chrome":    "start chrome",
    "firefox":          "start firefox",
    "edge":             "start msedge",
    "brave":            "start brave",
    # Office & Text
    "notepad":          "notepad.exe",
    "word":             "winword",
    "excel":            "excel",
    "powerpoint":       "powerpnt",
    "outlook":          "outlook",
    "paint":            "mspaint.exe",
    # Dev
    "vs code":          "code",
    "vscode":           "code",
    "visual studio code":"code",
    "terminal":         "start cmd",
    "command prompt":   "start cmd",
    "powershell":       "start powershell",
    "git bash":         "start git-bash",
    # System
    "calculator":       "calc.exe",
    "task manager":     "taskmgr.exe",
    "explorer":         "explorer.exe",
    "file explorer":    "explorer.exe",
    "control panel":    "control",
    "settings":         "start ms-settings:",
    "camera":           "start microsoft.windows.camera:",
    "snipping tool":    "SnippingTool.exe",
    # Media
    "vlc":              "vlc",
    "spotify":          "start spotify",
    "netflix":          "start netflix:",
    # Productivity
    "teams":            "start msteams",
    "zoom":             "start zoom",
    "discord":          "start discord",
    "slack":            "start slack",
    "whatsapp":         "start whatsapp:",
    "telegram":         "start telegram",
    # Utilities
    "clock":            "start ms-clock:",
    "maps":             "start maps:",
    "weather":          "start bingweather:",
}

# Website shortcuts
WEBSITE_MAP = {
    "youtube":   "https://youtube.com",
    "google":    "https://google.com",
    "github":    "https://github.com",
    "gmail":     "https://mail.google.com",
    "facebook":  "https://facebook.com",
    "twitter":   "https://twitter.com",
    "instagram": "https://instagram.com",
    "linkedin":  "https://linkedin.com",
    "amazon":    "https://amazon.in",
    "netflix":   "https://netflix.com",
    "reddit":    "https://reddit.com",
    "wikipedia": "https://wikipedia.org",
    "chatgpt":   "https://chat.openai.com",
    "maps":      "https://maps.google.com",
}


# ─────────────────────────────────────────────────────────
# System helpers
# ─────────────────────────────────────────────────────────

def _run(cmd: str) -> None:
    os.system(cmd)

def _open_app(name: str) -> str:
    n = name.lower().strip()
    for key, cmd in APP_MAP.items():
        if key in n:
            try:
                _run(cmd)
                return f"Opening {key}."
            except Exception as e:
                return f"Could not open {key}: {e}"
    return f"I don't have a shortcut for '{name}'. Want me to search for it online?"

def _open_website(name: str) -> str:
    n = name.lower().strip()
    for key, url in WEBSITE_MAP.items():
        if key in n:
            webbrowser.open(url)
            return f"Opening {key} in your browser."
    # Generic: open as search
    webbrowser.open(f"https://www.google.com/search?q={name}")
    return f"Searching Google for '{name}'."


# ─────────────────────────────────────────────────────────
# Command Handler
# ─────────────────────────────────────────────────────────

class CommandHandler:
    """
    Routes voice commands to the correct system action.
    Unrecognised commands return matched=False -> routed to AI.
    """

    def __init__(self):
        self._on_gesture_start  = None
        self._on_gesture_stop   = None
        self._on_head_start     = None
        self._on_head_stop      = None
        self._on_clear_memory   = None
        self._on_quit           = None

    def register(
        self,
        on_gesture_start : Callable = None,
        on_gesture_stop  : Callable = None,
        on_head_start    : Callable = None,
        on_head_stop     : Callable = None,
        on_clear_memory  : Callable = None,
        on_quit          : Callable = None,
    ) -> None:
        self._on_gesture_start = on_gesture_start
        self._on_gesture_stop  = on_gesture_stop
        self._on_head_start    = on_head_start
        self._on_head_stop     = on_head_stop
        self._on_clear_memory  = on_clear_memory
        self._on_quit          = on_quit

    # ── Main dispatcher ────────────────────────────────────

    def handle(self, text: str, user: str) -> tuple[bool, str]:
        """
        Match voice input against hardcoded commands.
        Returns (matched, response_text).
        If matched=False -> caller routes to AI.
        """
        t = text.lower().strip()

        # ── EXIT ───────────────────────────────────────────
        if any(p in t for p in ["exit friday", "quit friday",
                                  "goodbye friday", "shut down friday"]):
            if self._on_quit: self._on_quit()
            return True, f"Goodbye {user}! Shutting down FRIDAY."

        # ── OPEN APP ───────────────────────────────────────
        if t.startswith("open "):
            target = t[5:].strip()
            # Check website map first
            for key in WEBSITE_MAP:
                if key in target:
                    return True, _open_website(target)
            return True, _open_app(target)

        if t.startswith("launch "):
            return True, _open_app(t[7:].strip())

        if t.startswith("start ") and "gesture" not in t and "head" not in t:
            return True, _open_app(t[6:].strip())

        # ── WEBSITE SEARCH ─────────────────────────────────
        if t.startswith("go to ") or t.startswith("search for ") or t.startswith("search "):
            query = t.replace("go to","").replace("search for","").replace("search","").strip()
            return True, _open_website(query)

        if "open youtube" in t:
            return True, _open_website("youtube")
        if "open google" in t:
            return True, _open_website("google")
        if "open github" in t:
            return True, _open_website("github")

        # ── WINDOW MANAGEMENT ──────────────────────────────
        if any(p in t for p in ["close this window", "close window", "close app"]):
            import pyautogui; pyautogui.hotkey("alt", "f4")
            return True, "Closing the window."

        if any(p in t for p in ["minimize", "minimise"]):
            import pyautogui; pyautogui.hotkey("win", "down")
            return True, "Window minimized."

        if any(p in t for p in ["maximize", "maximise", "full screen"]):
            import pyautogui; pyautogui.hotkey("win", "up")
            return True, "Window maximized."

        if any(p in t for p in ["switch window", "alt tab", "next window"]):
            import pyautogui; pyautogui.hotkey("alt", "tab")
            return True, "Switching window."

        if "show desktop" in t:
            import pyautogui; pyautogui.hotkey("win", "d")
            return True, "Showing desktop."

        # ── SCREENSHOT ─────────────────────────────────────
        if any(p in t for p in ["screenshot", "take a screenshot", "capture screen"]):
            import pyautogui, datetime
            fname = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            pyautogui.screenshot(fname)
            return True, f"Screenshot saved as {fname}."

        # ── VOLUME ─────────────────────────────────────────
        if any(p in t for p in ["volume up", "increase volume", "louder"]):
            import pyautogui
            for _ in range(5): pyautogui.press("volumeup")
            return True, "Volume increased."

        if any(p in t for p in ["volume down", "decrease volume", "quieter", "lower volume"]):
            import pyautogui
            for _ in range(5): pyautogui.press("volumedown")
            return True, "Volume decreased."

        if any(p in t for p in ["mute", "unmute", "silence"]):
            import pyautogui; pyautogui.press("volumemute")
            return True, "Volume toggled."

        # ── MEDIA CONTROLS ─────────────────────────────────
        if any(p in t for p in ["play", "pause", "play pause"]):
            import pyautogui; pyautogui.press("playpause")
            return True, "Play / Pause toggled."

        if any(p in t for p in ["next song", "next track", "skip"]):
            import pyautogui; pyautogui.press("nexttrack")
            return True, "Next track."

        if any(p in t for p in ["previous song", "prev song", "previous track"]):
            import pyautogui; pyautogui.press("prevtrack")
            return True, "Previous track."

        # ── MOUSE ACTIONS ──────────────────────────────────
        if t in ("click", "left click", "mouse click"):
            import pyautogui; pyautogui.click()
            return True, "Clicked."

        if any(p in t for p in ["right click", "context menu"]):
            import pyautogui; pyautogui.rightClick()
            return True, "Right clicked."

        if any(p in t for p in ["double click", "double tap"]):
            import pyautogui; pyautogui.doubleClick()
            return True, "Double clicked."

        if any(p in t for p in ["scroll up", "scroll down"]):
            import pyautogui
            amt = 5 if "up" in t else -5
            pyautogui.scroll(amt)
            direction = "up" if amt > 0 else "down"
            return True, f"Scrolled {direction}."

        # ── KEYBOARD SHORTCUTS ─────────────────────────────
        if any(p in t for p in ["press enter", "hit enter", "enter"]):
            import pyautogui; pyautogui.press("enter")
            return True, "Pressed Enter."

        if any(p in t for p in ["press escape", "escape", "cancel"]):
            import pyautogui; pyautogui.press("escape")
            return True, "Pressed Escape."

        if any(p in t for p in ["press space", "spacebar"]):
            import pyautogui; pyautogui.press("space")
            return True, "Pressed Space."

        if any(p in t for p in ["press tab", "hit tab"]):
            import pyautogui; pyautogui.press("tab")
            return True, "Pressed Tab."

        if any(p in t for p in ["copy", "ctrl c"]):
            import pyautogui; pyautogui.hotkey("ctrl", "c")
            return True, "Copied."

        if any(p in t for p in ["paste", "ctrl v"]):
            import pyautogui; pyautogui.hotkey("ctrl", "v")
            return True, "Pasted."

        if any(p in t for p in ["cut", "ctrl x"]):
            import pyautogui; pyautogui.hotkey("ctrl", "x")
            return True, "Cut."

        if any(p in t for p in ["undo", "ctrl z"]):
            import pyautogui; pyautogui.hotkey("ctrl", "z")
            return True, "Undone."

        if any(p in t for p in ["redo", "ctrl y"]):
            import pyautogui; pyautogui.hotkey("ctrl", "y")
            return True, "Redone."

        if any(p in t for p in ["select all", "ctrl a"]):
            import pyautogui; pyautogui.hotkey("ctrl", "a")
            return True, "Selected all."

        if any(p in t for p in ["go back", "back", "previous page"]):
            import pyautogui; pyautogui.hotkey("alt", "left")
            return True, "Going back."

        if any(p in t for p in ["new tab", "open new tab"]):
            import pyautogui; pyautogui.hotkey("ctrl", "t")
            return True, "New tab opened."

        if any(p in t for p in ["close tab", "close this tab"]):
            import pyautogui; pyautogui.hotkey("ctrl", "w")
            return True, "Tab closed."

        if any(p in t for p in ["refresh", "reload"]):
            import pyautogui; pyautogui.press("f5")
            return True, "Page refreshed."

        if any(p in t for p in ["find", "search on page", "ctrl f"]):
            import pyautogui; pyautogui.hotkey("ctrl", "f")
            return True, "Search bar opened."

        if any(p in t for p in ["zoom in", "make bigger"]):
            import pyautogui; pyautogui.hotkey("ctrl", "+")
            return True, "Zoomed in."

        if any(p in t for p in ["zoom out", "make smaller"]):
            import pyautogui; pyautogui.hotkey("ctrl", "-")
            return True, "Zoomed out."

        # ── SYSTEM POWER ───────────────────────────────────
        if "shutdown" in t and any(p in t for p in ["computer","system","pc","laptop"]):
            if platform.system() == "Windows":
                _run("shutdown /s /t 5")
            return True, "Shutting down in 5 seconds."

        if "restart" in t and any(p in t for p in ["computer","system","pc","laptop"]):
            if platform.system() == "Windows":
                _run("shutdown /r /t 5")
            return True, "Restarting in 5 seconds."

        if any(p in t for p in ["lock screen", "lock computer", "lock pc"]):
            if platform.system() == "Windows":
                _run("rundll32.exe user32.dll,LockWorkStation")
            return True, "Screen locked."

        if any(p in t for p in ["sleep", "hibernate"]):
            if platform.system() == "Windows":
                _run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return True, "Going to sleep."

        # ── GESTURE CONTROL ────────────────────────────────
        if any(p in t for p in ["start gesture","enable gesture","gesture on","hand control on"]):
            if self._on_gesture_start: self._on_gesture_start()
            return True, "Gesture control activated. Control cursor with your hand."

        if any(p in t for p in ["stop gesture","disable gesture","gesture off","hand control off"]):
            if self._on_gesture_stop: self._on_gesture_stop()
            return True, "Gesture control deactivated."

        # ── HEAD CONTROL ───────────────────────────────────
        if any(p in t for p in ["start head","enable head","head control on","head tracking on"]):
            if self._on_head_start: self._on_head_start()
            return True, "Head control activated. Hold still to calibrate."

        if any(p in t for p in ["stop head","disable head","head control off","head tracking off"]):
            if self._on_head_stop: self._on_head_stop()
            return True, "Head control deactivated."

        # ── MEMORY / RECALL ────────────────────────────────
        if any(p in t for p in ["clear memory","forget everything","reset memory",
                                  "clear conversation","forget our conversation"]):
            if self._on_clear_memory: self._on_clear_memory()
            return True, f"Conversation cleared, {user}. Your profile is still saved."

        # ── TYPE TEXT ──────────────────────────────────────
        if t.startswith("type "):
            words = t[5:].strip()
            import pyautogui; pyautogui.typewrite(words, interval=0.05)
            return True, f"Typed: {words}"

        if t.startswith("write "):
            words = t[6:].strip()
            import pyautogui; pyautogui.typewrite(words, interval=0.05)
            return True, f"Typed: {words}"

        # ── DASHBOARD ──────────────────────────────────────
        if any(p in t for p in ["open dashboard", "show dashboard",
                                  "system dashboard", "friday dashboard"]):
            try:
                import subprocess
                subprocess.Popen(["python", "dashboard.py"])
                return True, "Opening FRIDAY dashboard."
            except Exception as e:
                return True, f"Could not open dashboard: {e}"

        # ── SMART HOME ─────────────────────────────────────
        if any(p in t for p in ["lights on", "turn on lights", "turn on the lights",
                                  "switch on lights", "light on"]):
            return True, _smart_home_call("light", "turn_on", "all") or \
                          "Turning on the lights."

        if any(p in t for p in ["lights off", "turn off lights", "turn off the lights",
                                  "switch off lights", "light off"]):
            return True, _smart_home_call("light", "turn_off", "all") or \
                          "Turning off the lights."

        if any(p in t for p in ["dim lights", "lights dim", "low lights"]):
            return True, _smart_home_call("light", "turn_on", "all",
                                          extra={"brightness_pct": 30}) or \
                          "Dimming the lights."

        if any(p in t for p in ["bright lights", "lights bright", "full brightness"]):
            return True, _smart_home_call("light", "turn_on", "all",
                                          extra={"brightness_pct": 100}) or \
                          "Setting lights to full brightness."

        if any(p in t for p in ["fan on", "turn on fan", "start fan"]):
            return True, _smart_home_call("switch", "turn_on", "fan") or \
                          "Turning on the fan."

        if any(p in t for p in ["fan off", "turn off fan", "stop fan"]):
            return True, _smart_home_call("switch", "turn_off", "fan") or \
                          "Turning off the fan."

        if any(p in t for p in ["air conditioning on", "ac on", "turn on ac",
                                  "turn on air conditioning"]):
            return True, _smart_home_call("switch", "turn_on", "ac") or \
                          "Turning on the air conditioning."

        if any(p in t for p in ["air conditioning off", "ac off", "turn off ac",
                                  "turn off air conditioning"]):
            return True, _smart_home_call("switch", "turn_off", "ac") or \
                          "Turning off the air conditioning."

        if any(p in t for p in ["lock the door", "lock door", "lock up"]):
            return True, _smart_home_call("lock", "lock", "front_door") or \
                          "Locking the door."

        if any(p in t for p in ["unlock the door", "unlock door"]):
            return True, _smart_home_call("lock", "unlock", "front_door") or \
                          "Unlocking the door."

        if any(p in t for p in ["movie mode", "cinema mode"]):
            return True, _smart_home_scene("movie_mode") or \
                          "Activating movie mode — lights dimmed."

        if any(p in t for p in ["sleep mode", "bedtime mode", "night mode"]):
            return True, _smart_home_scene("night_mode") or \
                          "Activating night mode — goodnight!"

        if any(p in t for p in ["good morning mode", "morning mode", "wake up mode"]):
            return True, _smart_home_scene("morning_mode") or \
                          "Good morning! Lights and climate set."

        if "temperature" in t or "thermostat" in t:
            import re
            nums = re.findall(r'\d+', t)
            if nums:
                temp = int(nums[0])
                return True, _smart_home_set_temp(temp) or \
                              f"Setting thermostat to {temp} degrees."
            return True, "Please say a temperature, like 'set temperature to 22'."

        # ── SMART HOME STATUS QUERY ─────────────────────────
        if t.startswith("is the ") and any(p in t for p in ["on", "off", "locked", "open"]):
            device = t.replace("is the ", "").replace(" on", "").replace(" off", "") \
                      .replace(" locked", "").replace(" open", "").strip()
            return True, _smart_home_status(device) or \
                          f"Could not check status of '{device}'."

        if t.startswith("what is the status of "):
            device = t.replace("what is the status of ", "").strip()
            return True, _smart_home_status(device) or \
                          f"Could not check status of '{device}'."

        # ── ROOM-SPECIFIC LIGHT CONTROL ─────────────────────
        # e.g. "turn on bedroom lights", "living room lights off"
        ROOMS = ["bedroom", "living room", "kitchen", "bathroom",
                 "office", "garage", "hall", "hallway", "dining"]
        for room in ROOMS:
            if room in t:
                if any(p in t for p in ["on", "turn on"]):
                    return True, _smart_home_call("light", "turn_on", room) or \
                                  f"Turning on {room} lights."
                if any(p in t for p in ["off", "turn off"]):
                    return True, _smart_home_call("light", "turn_off", room) or \
                                  f"Turning off {room} lights."

        # ── WEATHER ────────────────────────────────────────
        if any(p in t for p in ["weather", "temperature outside",
                                  "how hot", "how cold"]):
            if "forecast" in t or "next" in t:
                return True, get_forecast()
            if "rain" in t:
                return True, will_it_rain()
            return True, get_current_weather()

        # ── NEWS ───────────────────────────────────────────
        if any(p in t for p in ["news", "headlines", "what's happening",
                                  "what is happening"]):
            return True, fetch_news(t)

        # ── REMINDERS ──────────────────────────────────────
        if any(p in t for p in ["remind me", "set alarm", "set reminder",
                                  "set a reminder", "set an alarm"]):
            msg, secs = parse_reminder(t)
            if secs:
                return True, reminder_manager.add(msg, secs)
            return True, ("Please include a time, like "
                          "'remind me in 10 minutes to take a break'.")

        if any(p in t for p in ["my reminders", "list reminders",
                                  "what reminders", "show reminders"]):
            return True, reminder_manager.list_reminders()

        if any(p in t for p in ["cancel all reminders", "clear reminders",
                                  "delete all reminders"]):
            return True, reminder_manager.cancel_all()

        if t.startswith("cancel reminder"):
            nums = re.findall(r'\d+', t)
            if nums:
                return True, reminder_manager.cancel(int(nums[0]))
            return True, "Please say which reminder to cancel, like 'cancel reminder 1'."

        # ── VOLUME ─────────────────────────────────────────
        if any(p in t for p in ["volume", "mute", "unmute", "louder",
                                  "quieter", "turn up", "turn down"]):
            return True, vol_cmd(t)

        # ── CLIPBOARD ──────────────────────────────────────
        if any(p in t for p in ["what did i copy", "read clipboard",
                                  "what's in my clipboard", "show clipboard"]):
            return True, read_clipboard()

        if t.startswith("copy this"):
            text = t.replace("copy this", "").replace(":", "").strip()
            return True, write_clipboard(text) if text else \
                          (True, "What should I copy?")

        if any(p in t for p in ["clear clipboard", "empty clipboard"]):
            return True, clear_clipboard()

        if any(p in t for p in ["save clipboard", "save what i copied"]):
            return True, save_clipboard()

        if any(p in t for p in ["clipboard history", "show clipboard history"]):
            return True, get_history()

        # ── SCREENSHOT ─────────────────────────────────────
        if any(p in t for p in ["take a screenshot", "screenshot",
                                  "capture screen", "take screenshot"]):
            return True, take_screenshot()

        if any(p in t for p in ["read the screen", "read screen",
                                  "what's on my screen", "ocr screen"]):
            return True, read_screen()

        if any(p in t for p in ["open screenshots", "show screenshots",
                                  "screenshots folder"]):
            return True, open_screenshots_folder()

        # ── TELEGRAM ───────────────────────────────────────
        if any(p in t for p in ["send telegram", "send a telegram",
                                  "send notification", "notify me",
                                  "telegram message"]):
            # Extract message: "send telegram: hello mom"
            msg = ""
            for sep in [":", "saying", "that", "message"]:
                if sep in t:
                    msg = t.split(sep, 1)[-1].strip()
                    break
            if not msg:
                msg = t.replace("send telegram", "").replace(
                      "send notification", "").replace("notify me", "").strip()
            if msg:
                return True, tg_send(msg)
            return True, "What message should I send on Telegram?"

        # ── NO MATCH -> send to AI ──────────────────────────
        return False, ""


