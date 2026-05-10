"""
volume_ctrl.py - System Volume Control for FRIDAY (Windows)
Uses pycaw for precise control, falls back to pyautogui keypress.

Voice commands (in commands.py):
  "Set volume to 50"  /  "Volume up"  /  "Volume down"
  "Mute"  /  "Unmute"  /  "What's the volume?"
"""

import re

PYCAW_AVAILABLE = False
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    pass

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


def _vol():
    devices   = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> str:
    if PYCAW_AVAILABLE:
        try:
            v   = _vol()
            pct = round(v.GetMasterVolumeLevelScalar() * 100)
            return f"{'Muted. Level at' if v.GetMute() else 'Volume is'} {pct} percent."
        except Exception as e:
            return f"Could not get volume: {e}"
    return "pycaw not installed — volume read unavailable."


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))
    if PYCAW_AVAILABLE:
        try:
            v = _vol()
            v.SetMasterVolumeLevelScalar(percent / 100.0, None)
            if v.GetMute(): v.SetMute(0, None)
            return f"Volume set to {percent} percent."
        except Exception as e:
            return f"Volume error: {e}"
    if PYAUTOGUI_AVAILABLE:
        for _ in range(50): pyautogui.press("volumedown")
        for _ in range(percent // 2): pyautogui.press("volumeup")
        return f"Volume set to approximately {percent} percent."
    return "Volume control unavailable."


def volume_up(steps: int = 10) -> str:
    if PYCAW_AVAILABLE:
        try:
            v   = _vol()
            new = min(100, round(v.GetMasterVolumeLevelScalar() * 100) + steps)
            v.SetMasterVolumeLevelScalar(new / 100.0, None)
            if v.GetMute(): v.SetMute(0, None)
            return f"Volume increased to {new} percent."
        except Exception as e:
            return f"Volume up error: {e}"
    if PYAUTOGUI_AVAILABLE:
        for _ in range(steps // 2): pyautogui.press("volumeup")
        return "Volume increased."
    return "Volume control unavailable."


def volume_down(steps: int = 10) -> str:
    if PYCAW_AVAILABLE:
        try:
            v   = _vol()
            new = max(0, round(v.GetMasterVolumeLevelScalar() * 100) - steps)
            v.SetMasterVolumeLevelScalar(new / 100.0, None)
            return f"Volume decreased to {new} percent."
        except Exception as e:
            return f"Volume down error: {e}"
    if PYAUTOGUI_AVAILABLE:
        for _ in range(steps // 2): pyautogui.press("volumedown")
        return "Volume decreased."
    return "Volume control unavailable."


def mute() -> str:
    if PYCAW_AVAILABLE:
        try: _vol().SetMute(1, None); return "Muted."
        except Exception as e: return f"Mute error: {e}"
    if PYAUTOGUI_AVAILABLE:
        pyautogui.press("volumemute"); return "Muted."
    return "Volume control unavailable."


def unmute() -> str:
    if PYCAW_AVAILABLE:
        try:
            v = _vol(); v.SetMute(0, None)
            return f"Unmuted at {round(v.GetMasterVolumeLevelScalar()*100)} percent."
        except Exception as e: return f"Unmute error: {e}"
    if PYAUTOGUI_AVAILABLE:
        pyautogui.press("volumemute"); return "Unmuted."
    return "Volume control unavailable."


def parse_and_set(text: str) -> str:
    t = text.lower()
    if "what" in t and "volume" in t: return get_volume()
    if "unmute" in t:                 return unmute()
    if "mute" in t:                   return mute()
    if any(p in t for p in ["max volume", "full volume", "volume 100"]): return set_volume(100)
    if any(p in t for p in ["min volume", "volume 0", "silent"]):        return set_volume(0)
    if any(p in t for p in ["volume up", "louder", "turn up"]):
        m = re.search(r'(\d+)', t)
        return volume_up(int(m.group(1)) if m else 10)
    if any(p in t for p in ["volume down", "quieter", "lower volume", "turn down"]):
        m = re.search(r'(\d+)', t)
        return volume_down(int(m.group(1)) if m else 10)
    m = re.search(r'(\d{1,3})', t)
    if m and 0 <= int(m.group(1)) <= 100:
        return set_volume(int(m.group(1)))
    return "Please say a volume level, like 'set volume to 50'."


if __name__ == "__main__":
    print(get_volume())
    print(set_volume(60))
