"""
head.py - Head Movement Control for FRIDAY
Uses MediaPipe Face Mesh to track head position via webcam.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HEAD MOVEMENT MAP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
↑ Head UP          -> Scroll Up
↓ Head DOWN        -> Scroll Down
← Head LEFT        -> Move cursor left / Alt+Tab
-> Head RIGHT       -> Move cursor right
↗ Tilt RIGHT       -> Volume Up
↖ Tilt LEFT        -> Volume Down
😑 Mouth OPEN       -> Left Click (hold open = hold click)
😤 Double nod       -> Double Click
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run standalone:         python head.py
Activate via FRIDAY:    "start head control"
Deactivate via FRIDAY:  "stop head control"
"""

import time
import threading
import collections
import sys

try:
    import cv2
    import mediapipe as mp
    _ = mp.tasks.vision.FaceLandmarker
    import pyautogui
    import numpy as np
    HEAD_AVAILABLE = True
except (ImportError, AttributeError) as e:
    HEAD_AVAILABLE = False
    print(f"[Head]: Missing dependency or API ({e}). Head control disabled.")


# ─────────────────────────────────────────────────────────
# MediaPipe Face Mesh Landmark Indices (selected)
# ─────────────────────────────────────────────────────────

NOSE_TIP      = 4      # centre of nose (main tracking point)
FOREHEAD      = 10     # top of head
CHIN          = 152    # bottom of chin
LEFT_EAR      = 234    # left side of face
RIGHT_EAR     = 454    # right side of face
MOUTH_TOP     = 13     # upper lip
MOUTH_BOTTOM  = 14     # lower lip
LEFT_EYE_TOP  = 159   # left eye lid top
LEFT_EYE_BOT  = 145   # left eye lid bottom


# ─────────────────────────────────────────────────────────
# Head Controller
# ─────────────────────────────────────────────────────────

class HeadController:
    """
    Tracks head pose using MediaPipe Face Mesh.
    Maps movement deltas to system actions.
    """

    # ── Tuning parameters ──────────────────────────────────
    MOVE_THRESHOLD   = 12    # px delta before triggering movement
    TILT_THRESHOLD   = 15    # px tilt delta for volume control
    SCROLL_SPEED     = 3     # lines per scroll tick
    CURSOR_SPEED     = 20    # pixels cursor moves per head-move tick
    MOUTH_THRESHOLD  = 18    # px gap between lips to detect open mouth
    CLICK_COOLDOWN   = 1.2   # seconds between mouth-open clicks
    ACTION_COOLDOWN  = 0.25  # seconds between scroll/cursor actions
    FPS_LIMIT        = 20    # max frames/sec for head tracking

    # How many frames to average nose position (smoothing)
    SMOOTH_FRAMES    = 6

    def __init__(self, camera_index: int = 0):
        self._camera_index  = camera_index
        self._running       = False
        self._active        = threading.Event()
        self._thread        = None

        # Rolling average for smoothing
        self._nx_buf = collections.deque(maxlen=self.SMOOTH_FRAMES)
        self._ny_buf = collections.deque(maxlen=self.SMOOTH_FRAMES)

        # Neutral / calibration position
        self._origin_x: float | None = None
        self._origin_y: float | None = None
        self._origin_roll: float | None = None   # for tilt

        # Cooldown timers per action
        self._last_action: dict[str, float] = {}

        self._screen_w, self._screen_h = (
            pyautogui.size() if HEAD_AVAILABLE else (1920, 1080)
        )
        pyautogui.FAILSAFE = False

    # ── Public API ─────────────────────────────────────────

    def start(self) -> None:
        if not HEAD_AVAILABLE:
            print("[Head]: Dependencies missing — cannot start.")
            return
        if self._thread and self._thread.is_alive():
            print("[Head]: Already running.")
            return
        self._running = True
        self._active.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Head]: Head controller started.")

    def stop(self) -> None:
        self._running = False
        self._active.clear()
        print("[Head]: Head controller stopped.")

    def enable(self) -> None:
        self._active.set()
        self._origin_x = None    # recalibrate on re-enable
        print("[Head]: Enabled — hold head still to calibrate...")

    def disable(self) -> None:
        self._active.clear()
        print("[Head]: Disabled.")

    def is_active(self) -> bool:
        return self._active.is_set()

    # ── Cooldown helper ────────────────────────────────────

    def _cooled(self, action: str, cd: float = None) -> bool:
        c = cd if cd else self.ACTION_COOLDOWN
        now = time.time()
        if now - self._last_action.get(action, 0) > c:
            self._last_action[action] = now
            return True
        return False

    # ── Main loop ──────────────────────────────────────────

    def _loop(self) -> None:
        import os
        if not os.path.exists("face_landmarker.task"):
            print("[Head]: Downloading FaceLandmarker model...")
            import urllib.request
            urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'face_landmarker.task')

        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path='face_landmarker.task'),
            running_mode=VisionRunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.7,
            min_face_presence_confidence=0.7,
            min_tracking_confidence=0.7
        )
        face_mesh = FaceLandmarker.create_from_options(options)

        cap = cv2.VideoCapture(self._camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, self.FPS_LIMIT)

        frame_interval = 1.0 / self.FPS_LIMIT
        prev_time = 0.0

        calibration_frames = 0
        calib_x_buf, calib_y_buf, calib_r_buf = [], [], []

        print("[Head]: Camera ready. Hold head STILL for 2 seconds to calibrate.")

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

            # ── Pause overlay ─────────────────────────────
            if not self._active.is_set():
                self._draw_hud(frame, "PAUSED", None, None, None)
                cv2.imshow("FRIDAY Head Control", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            # ── Face Mesh processing ───────────────────────
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(time.time() * 1000)
            result = face_mesh.detect_for_video(mp_image, timestamp_ms)

            if result.face_landmarks:
                fl = result.face_landmarks[0]

                # Pixel positions of key points
                def px(idx):
                    return int(fl[idx].x * w), int(fl[idx].y * h)

                nose    = px(NOSE_TIP)
                forehead = px(FOREHEAD)
                chin    = px(CHIN)
                left_e  = px(LEFT_EAR)
                right_e = px(RIGHT_EAR)
                m_top   = px(MOUTH_TOP)
                m_bot   = px(MOUTH_BOTTOM)

                nx, ny  = float(nose[0]), float(nose[1])

                # Head roll (tilt) = angle of ear-to-ear line
                roll = float(np.degrees(
                    np.arctan2(right_e[1] - left_e[1],
                               right_e[0] - left_e[0])
                ))

                # Mouth openness
                mouth_open = abs(m_bot[1] - m_top[1])

                # ── Calibration (first 40 frames) ─────────
                if self._origin_x is None:
                    calib_x_buf.append(nx)
                    calib_y_buf.append(ny)
                    calib_r_buf.append(roll)
                    calibration_frames += 1

                    pct = int(calibration_frames / 40 * 100)
                    self._draw_hud(frame, f"Calibrating... {pct}%",
                                   None, None, None)
                    cv2.imshow("FRIDAY Head Control", frame)
                    cv2.waitKey(1)

                    if calibration_frames >= 40:
                        self._origin_x    = float(np.mean(calib_x_buf))
                        self._origin_y    = float(np.mean(calib_y_buf))
                        self._origin_roll = float(np.mean(calib_r_buf))
                        print(f"[Head]: Calibrated. Origin = "
                              f"({self._origin_x:.0f}, {self._origin_y:.0f})")
                    continue

                # Smooth nose position
                self._nx_buf.append(nx)
                self._ny_buf.append(ny)
                snx = float(np.mean(self._nx_buf))
                sny = float(np.mean(self._ny_buf))

                # Delta from calibration origin
                dx = snx - self._origin_x
                dy = sny - self._origin_y
                dr = roll - self._origin_roll  # roll delta

                action = "Still"

                # ─────────────────────────────────────────
                # ACTION MAPPING
                # ─────────────────────────────────────────

                # 😑 Mouth OPEN -> Left Click
                if mouth_open > self.MOUTH_THRESHOLD:
                    action = "Mouth Click"
                    if self._cooled("mouth_click", self.CLICK_COOLDOWN):
                        pyautogui.click()
                        print("[Head]: Mouth Click")

                # ↑ HEAD UP -> Scroll Up
                elif dy < -self.MOVE_THRESHOLD:
                    action = "Scroll Up"
                    if self._cooled("scroll_up"):
                        pyautogui.scroll(self.SCROLL_SPEED)

                # ↓ HEAD DOWN -> Scroll Down
                elif dy > self.MOVE_THRESHOLD:
                    action = "Scroll Down"
                    if self._cooled("scroll_down"):
                        pyautogui.scroll(-self.SCROLL_SPEED)

                # ↗ TILT RIGHT -> Volume Up
                elif dr > self.TILT_THRESHOLD:
                    action = "Volume Up"
                    if self._cooled("vol_up", 0.4):
                        pyautogui.press("volumeup")
                        print("[Head]: Volume Up")

                # ↖ TILT LEFT -> Volume Down
                elif dr < -self.TILT_THRESHOLD:
                    action = "Volume Down"
                    if self._cooled("vol_down", 0.4):
                        pyautogui.press("volumedown")
                        print("[Head]: Volume Down")

                # -> HEAD RIGHT -> Move cursor right
                elif dx > self.MOVE_THRESHOLD:
                    action = "Cursor Right"
                    if self._cooled("cursor_right", 0.05):
                        cx, cy = pyautogui.position()
                        speed  = min(int(abs(dx) * 2), 60)
                        pyautogui.moveTo(
                            min(cx + speed, self._screen_w - 1), cy,
                            duration=0.05
                        )

                # ← HEAD LEFT -> Move cursor left
                elif dx < -self.MOVE_THRESHOLD:
                    action = "Cursor Left"
                    if self._cooled("cursor_left", 0.05):
                        cx, cy = pyautogui.position()
                        speed  = min(int(abs(dx) * 2), 60)
                        pyautogui.moveTo(
                            max(cx - speed, 0), cy,
                            duration=0.05
                        )

                # Draw landmarks
                for idx in [NOSE_TIP, FOREHEAD, CHIN, LEFT_EAR,
                             RIGHT_EAR, MOUTH_TOP, MOUTH_BOTTOM]:
                    cv2.circle(frame, px(idx), 4, (0, 200, 255), -1)

                cv2.line(frame, left_e, right_e, (100, 100, 255), 1)
                cv2.line(frame, forehead, chin,  (100, 255, 100), 1)

                self._draw_hud(frame, action, dx, dy, mouth_open)

            else:
                self._draw_hud(frame, "No face detected", None, None, None)

            cv2.imshow("FRIDAY Head Control", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()
        face_mesh.close()
        print("[Head]: Loop exited.")

    # ── HUD ────────────────────────────────────────────────

    def _draw_hud(self, frame, action: str, dx, dy, mouth):
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], 65), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        colors = {
            "Scroll Up":    (100, 255, 100),
            "Scroll Down":  (100, 100, 255),
            "Cursor Left":  (255, 165, 0),
            "Cursor Right": (0,   200, 255),
            "Volume Up":    (0,   255, 200),
            "Volume Down":  (200, 0,   255),
            "Mouth Click":  (0,   255, 0),
            "Still":        (180, 180, 180),
            "PAUSED":       (0,   100, 255),
        }
        color = colors.get(action, (200, 200, 200))
        cv2.putText(frame, f"Head: {action}",
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        if dx is not None:
            cv2.putText(frame,
                f"dx={int(dx):+d}  dy={int(dy):+d}  mouth={int(mouth if mouth else 0)}px",
                (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 180, 180), 1)

        # Cheat sheet
        tips = [
            "Head UP   = Scroll Up",
            "Head DOWN = Scroll Dn",
            "Head LEFT = Cursor Lt",
            "Head RIGHT= Cursor Rt",
            "Tilt Left = Vol Down",
            "Tilt Right= Vol Up",
            "Open Mouth= Click",
        ]
        fw = frame.shape[1]; fh = frame.shape[0]
        for i, t in enumerate(tips):
            cv2.putText(frame, t, (fw - 210, fh - 120 + i * 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 140, 140), 1)


# ─────────────────────────────────────────────────────────
# Standalone entry point
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HEAD_AVAILABLE:
        print("Install: pip install opencv-python mediapipe pyautogui")
        sys.exit(1)

    print("=" * 50)
    print("  FRIDAY Head Control — Standalone Mode")
    print("=" * 50)
    print("  Hold head STILL for 2s to calibrate")
    print("  Head UP/DOWN  -> Scroll")
    print("  Head LEFT/RIGHT -> Move cursor")
    print("  Tilt LEFT/RIGHT -> Volume")
    print("  Open mouth    -> Click")
    print("  Press Q to quit")
    print("=" * 50)

    ctrl = HeadController()
    ctrl.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ctrl.stop()
        print("Head control stopped.")
