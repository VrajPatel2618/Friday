"""
gesture.py - Advanced Hand Gesture Control for FRIDAY
Uses MediaPipe + OpenCV for hand tracking and PyAutoGUI for system control.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GESTURE MAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☝️  1 finger  (Index only)        -> Move cursor
✌️  2 fingers (Index + Middle)    -> Right click
🤟  3 fingers (Index+Mid+Ring)    -> Scroll UP
🖖  4 fingers (all except thumb)  -> Scroll DOWN
✋  5 fingers (all open / fist)   -> Open Start Menu
🤏  Pinch    (Thumb + Index)      -> Left Click
👌  Thumb + Middle pinch          -> Double Click
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run standalone:           python gesture.py
Activate via FRIDAY:      "start gesture control"
Deactivate via FRIDAY:    "stop gesture control"
"""

import os
import time
import threading
import collections
import sys

try:
    import cv2
    import mediapipe as mp
    _ = mp.tasks.vision.HandLandmarker
    import pyautogui
    import numpy as np
    GESTURE_AVAILABLE = True
except (ImportError, AttributeError) as e:
    GESTURE_AVAILABLE = False
    print(f"[Gesture]: Missing dependency or solutions API ({e}). Gesture control disabled.")

from config import (
    CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT,
    SMOOTHING_BUFFER, CLICK_COOLDOWN, PINCH_THRESHOLD,
    GESTURE_SCALE_X, GESTURE_SCALE_Y, GESTURE_FPS_LIMIT
)


# ─────────────────────────────────────────────────────────
# MediaPipe Landmark Indices
# ─────────────────────────────────────────────────────────

WRIST      = 0
THUMB_TIP  = 4;  THUMB_IP   = 3;  THUMB_MCP  = 2
INDEX_TIP  = 8;  INDEX_PIP  = 6;  INDEX_MCP  = 5
MIDDLE_TIP = 12; MIDDLE_PIP = 10; MIDDLE_MCP = 9
RING_TIP   = 16; RING_PIP   = 14; RING_MCP   = 13
PINKY_TIP  = 20; PINKY_PIP  = 18; PINKY_MCP  = 17


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _dist(lm, a: int, b: int) -> float:
    """Euclidean pixel distance between two landmarks."""
    ax, ay = lm[a]; bx, by = lm[b]
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _finger_up(lm, tip: int, pip: int) -> bool:
    """True if finger is extended (tip above PIP joint)."""
    return lm[tip][1] < lm[pip][1]


def _thumb_up(lm) -> bool:
    """True if thumb is extended (tip to the left of IP joint for right hand)."""
    return lm[THUMB_TIP][0] < lm[THUMB_IP][0]


def _count_fingers(lm) -> tuple[int, list[bool]]:
    """
    Count how many fingers are raised.
    Returns (count, [thumb, index, middle, ring, pinky])
    """
    fingers = [
        _thumb_up(lm),
        _finger_up(lm, INDEX_TIP,  INDEX_PIP),
        _finger_up(lm, MIDDLE_TIP, MIDDLE_PIP),
        _finger_up(lm, RING_TIP,   RING_PIP),
        _finger_up(lm, PINKY_TIP,  PINKY_PIP),
    ]
    return sum(fingers), fingers


# ─────────────────────────────────────────────────────────
# Gesture Label -> HUD colours
# ─────────────────────────────────────────────────────────

GESTURE_COLORS = {
    "Move Cursor":    (0,   255, 100),
    "Left Click":     (0,   255, 0),
    "Right Click":    (255, 165, 0),
    "Double Click":   (0,   200, 255),
    "Scroll Up":      (100, 100, 255),
    "Scroll Down":    (255, 100, 100),
    "Start Menu":     (255, 215, 0),
    "No hand":        (0,   0,   200),
    "PAUSED":         (0,   100, 255),
}


# ─────────────────────────────────────────────────────────
# Gesture Controller
# ─────────────────────────────────────────────────────────

class GestureController:
    """
    Full-featured gesture controller with:
      - Cursor movement (index finger)
      - Left click   (pinch: thumb + index)
      - Right click  (2 fingers: index + middle up)
      - Double click (thumb + middle pinch)
      - Scroll up    (3 fingers up)
      - Scroll down  (4 fingers up)
      - Start Menu   (all 5 fingers / open palm)
      - Cursor smoothing (moving average)
      - Cooldown timers to prevent accidental triggers
    """

    SCROLL_AMOUNT  = 5       # lines per scroll gesture
    GESTURE_HOLD   = 0.4     # seconds a gesture must be held to trigger

    def __init__(self):
        self._running       = False
        self._thread        = None
        self._active        = threading.Event()

        # Cursor smoothing
        self._x_buf = collections.deque(maxlen=SMOOTHING_BUFFER)
        self._y_buf = collections.deque(maxlen=SMOOTHING_BUFFER)

        # Cooldown timers (action -> last trigger time)
        self._cooldowns: dict[str, float] = {}

        self._screen_w, self._screen_h = (
            pyautogui.size() if GESTURE_AVAILABLE else (1920, 1080)
        )
        pyautogui.FAILSAFE = False

        # Gesture hold tracking
        self._gesture_start: dict[str, float] = {}

    # ── Public API ─────────────────────────────────────────

    def start(self) -> None:
        if not GESTURE_AVAILABLE:
            print("[Gesture]: Dependencies missing — cannot start.")
            return
        if self._thread and self._thread.is_alive():
            print("[Gesture]: Already running.")
            return
        self._running = True
        self._active.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Gesture]: Controller started.")

    def stop(self) -> None:
        self._running = False
        self._active.clear()
        print("[Gesture]: Controller stopped.")

    def enable(self) -> None:
        self._active.set()
        print("[Gesture]: Enabled.")

    def disable(self) -> None:
        self._active.clear()
        print("[Gesture]: Disabled.")

    def is_active(self) -> bool:
        return self._active.is_set()

    # ── Cooldown helper ────────────────────────────────────

    def _cooled(self, action: str, cooldown: float = None) -> bool:
        """Return True if enough time has passed since the last action trigger."""
        cd = cooldown if cooldown is not None else CLICK_COOLDOWN
        now = time.time()
        if now - self._cooldowns.get(action, 0) > cd:
            self._cooldowns[action] = now
            return True
        return False

    # ── Gesture hold helper ────────────────────────────────

    def _held(self, gesture: str, required: float = None) -> bool:
        """
        Return True if the gesture has been continuously held for `required` seconds.
        Resets timer when a different gesture is seen.
        """
        req = required if required is not None else self.GESTURE_HOLD
        now = time.time()
        if gesture not in self._gesture_start:
            self._gesture_start = {gesture: now}   # reset all others
            return False
        return (now - self._gesture_start[gesture]) >= req

    def _update_hold(self, gesture: str) -> None:
        if gesture not in self._gesture_start:
            self._gesture_start = {gesture: time.time()}

    # ── Main loop ──────────────────────────────────────────

    def _loop(self) -> None:
        if not os.path.exists("hand_landmarker.task"):
            print("[Gesture]: Downloading HandLandmarker model...")
            import urllib.request
            urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task', 'hand_landmarker.task')

        BaseOptions = mp.tasks.BaseOptions
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
            running_mode=VisionRunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.75,
            min_hand_presence_confidence=0.75,
            min_tracking_confidence=0.75
        )
        hands = HandLandmarker.create_from_options(options)
        
        HAND_CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4),
            (0, 5), (5, 6), (6, 7), (7, 8),
            (5, 9), (9, 10), (10, 11), (11, 12),
            (9, 13), (13, 14), (14, 15), (15, 16),
            (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)
        ]

        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS,          GESTURE_FPS_LIMIT)

        frame_interval = 1.0 / GESTURE_FPS_LIMIT
        prev_time      = 0.0
        current_gesture = "No hand"

        print("[Gesture]: Camera opened. Press Q to quit.")

        while self._running:
            now = time.time()
            if now - prev_time < frame_interval:
                time.sleep(0.005)
                continue
            prev_time = now

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)
            h, w  = frame.shape[:2]

            # ── Paused overlay ─────────────────────────────
            if not self._active.is_set():
                self._draw_hud(frame, "PAUSED", 0, 0)
                cv2.imshow("FRIDAY Gesture Control", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            # ── MediaPipe processing ───────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(time.time() * 1000)
            result = hands.detect_for_video(mp_image, timestamp_ms)

            if result.hand_landmarks:
                hand_lm = result.hand_landmarks[0]
                lm      = [(int(l.x * w), int(l.y * h)) for l in hand_lm]

                count, fingers = _count_fingers(lm)
                thumb, index, middle, ring, pinky = fingers

                # ── Smooth cursor position (index tip) ────
                ix, iy = lm[INDEX_TIP]
                sx = int(np.interp(ix, [0, w],
                         [0, self._screen_w * GESTURE_SCALE_X]) / GESTURE_SCALE_X)
                sy = int(np.interp(iy, [0, h],
                         [0, self._screen_h * GESTURE_SCALE_Y]) / GESTURE_SCALE_Y)
                sx = max(0, min(sx, self._screen_w - 1))
                sy = max(0, min(sy, self._screen_h - 1))
                self._x_buf.append(sx)
                self._y_buf.append(sy)
                smooth_x = int(sum(self._x_buf) / len(self._x_buf))
                smooth_y = int(sum(self._y_buf) / len(self._y_buf))

                # ─────────────────────────────────────────
                # GESTURE RECOGNITION (priority ordered)
                # ─────────────────────────────────────────

                pinch_dist  = _dist(lm, THUMB_TIP, INDEX_TIP)
                m_pinch_dist = _dist(lm, THUMB_TIP, MIDDLE_TIP)

                # 🤏 PINCH -> Left Click (thumb + index close)
                if pinch_dist < PINCH_THRESHOLD and count <= 2:
                    current_gesture = "Left Click"
                    pyautogui.moveTo(smooth_x, smooth_y)
                    self._update_hold("Left Click")
                    if self._held("Left Click", 0.2) and self._cooled("Left Click"):
                        pyautogui.click()
                        cv2.circle(frame, (ix, iy), 18, (0, 255, 0), -1)
                        print(f"[Gesture]: Left Click ({smooth_x},{smooth_y})")

                # 👌 THUMB + MIDDLE PINCH -> Double Click
                elif m_pinch_dist < PINCH_THRESHOLD and not index:
                    current_gesture = "Double Click"
                    self._update_hold("Double Click")
                    if self._held("Double Click", 0.3) and self._cooled("Double Click", 1.5):
                        pyautogui.doubleClick(smooth_x, smooth_y)
                        print(f"[Gesture]: Double Click ({smooth_x},{smooth_y})")

                # ✋ ALL 5 FINGERS -> Open / Close Start Menu
                elif count == 5:
                    current_gesture = "Start Menu"
                    self._update_hold("Start Menu")
                    if self._held("Start Menu", 0.6) and self._cooled("Start Menu", 2.0):
                        pyautogui.press("win")
                        print("[Gesture]: Start Menu opened")

                # 🖖 4 FINGERS (no thumb) -> Scroll Down
                elif count == 4 and not thumb:
                    current_gesture = "Scroll Down"
                    pyautogui.moveTo(smooth_x, smooth_y)
                    self._update_hold("Scroll Down")
                    if self._held("Scroll Down", 0.3) and self._cooled("Scroll Down", 0.15):
                        pyautogui.scroll(-self.SCROLL_AMOUNT)
                        print("[Gesture]: Scroll Down")

                # 🤟 3 FINGERS (index+middle+ring) -> Scroll Up
                elif count == 3 and index and middle and ring and not pinky:
                    current_gesture = "Scroll Up"
                    pyautogui.moveTo(smooth_x, smooth_y)
                    self._update_hold("Scroll Up")
                    if self._held("Scroll Up", 0.3) and self._cooled("Scroll Up", 0.15):
                        pyautogui.scroll(self.SCROLL_AMOUNT)
                        print("[Gesture]: Scroll Up")

                # ✌️ 2 FINGERS (index + middle) -> Right Click
                elif count == 2 and index and middle and not ring and not pinky:
                    current_gesture = "Right Click"
                    pyautogui.moveTo(smooth_x, smooth_y)
                    self._update_hold("Right Click")
                    if self._held("Right Click", 0.4) and self._cooled("Right Click", 1.5):
                        pyautogui.rightClick(smooth_x, smooth_y)
                        print(f"[Gesture]: Right Click ({smooth_x},{smooth_y})")

                # ☝️ 1 FINGER (index only) -> Move Cursor
                elif count == 1 and index:
                    current_gesture = "Move Cursor"
                    self._gesture_start = {}   # reset hold timers
                    pyautogui.moveTo(smooth_x, smooth_y)

                else:
                    current_gesture = "Move Cursor"
                    pyautogui.moveTo(smooth_x, smooth_y)

                # Draw hand skeleton
                for connection in HAND_CONNECTIONS:
                    pt1 = lm[connection[0]]
                    pt2 = lm[connection[1]]
                    cv2.line(frame, pt1, pt2, (121, 44, 250), 2)
                for pt in lm:
                    cv2.circle(frame, pt, 4, (121, 22, 76), -1)

                self._draw_hud(frame, current_gesture, smooth_x, smooth_y,
                               count=count, pinch=pinch_dist)

            else:
                current_gesture = "No hand"
                self._gesture_start = {}
                self._draw_hud(frame, "No hand", 0, 0)

            cv2.imshow("FRIDAY Gesture Control", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        hands.close()
        print("[Gesture]: Loop exited.")

    # ── HUD renderer ───────────────────────────────────────

    def _draw_hud(self, frame, gesture: str, cx: int, cy: int,
                  count: int = 0, pinch: float = 999):
        """Draw on-screen overlay with gesture name and cursor info."""
        color = GESTURE_COLORS.get(gesture, (200, 200, 200))

        # Semi-transparent background bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], 60), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        cv2.putText(frame, f"Gesture: {gesture}",
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        if gesture not in ("No hand", "PAUSED"):
            cv2.putText(frame,
                f"Fingers: {count}  |  Pinch: {int(pinch)}px  |  Cursor: ({cx},{cy})",
                (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Gesture cheat-sheet (bottom right corner)
        tips = [
            "1 finger  = Move",
            "Pinch     = Click",
            "2 fingers = R-Click",
            "3 fingers = Scroll Up",
            "4 fingers = Scroll Dn",
            "5 fingers = Start Menu",
        ]
        fh = frame.shape[0]
        fw = frame.shape[1]
        for i, tip in enumerate(tips):
            cv2.putText(frame, tip,
                        (fw - 220, fh - 110 + i * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1)


# ─────────────────────────────────────────────────────────
# Standalone entry point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not GESTURE_AVAILABLE:
        print("Install: pip install opencv-python mediapipe pyautogui")
        sys.exit(1)

    print("=" * 50)
    print("  FRIDAY Gesture Control — Standalone Mode")
    print("=" * 50)
    print("  1 finger  -> Move cursor")
    print("  Pinch     -> Left click")
    print("  2 fingers -> Right click")
    print("  3 fingers -> Scroll up")
    print("  4 fingers -> Scroll down")
    print("  5 fingers -> Open Start Menu")
    print("  Press Q in camera window to quit")
    print("=" * 50)

    controller = GestureController()
    controller.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()
        print("Gesture control stopped.")
