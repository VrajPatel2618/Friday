"""
emotion.py - Emotion detection for FRIDAY
Detects emotion from:
  1. Voice energy (amplitude) using sounddevice — always active
  2. Facial geometry using MediaPipe Face Mesh — no TensorFlow/DeepFace needed!
     Analyzes lip curve, eyebrow height, mouth openness to classify emotion.

Emotion states: happy | sad | angry | neutral

WHY NOT DEEPFACE?
  DeepFace requires TensorFlow which has NO build for Python 3.14.
  MediaPipe is already installed and gives reliable geometric emotion cues:
    - Smile score  (lip corners vs lip center height)
    - Brow score   (eyebrow height relative to eye)
    - Mouth open   (lip gap)
"""

import time
import threading
import numpy as np
from config import USE_DEEPFACE

# ── sounddevice (voice energy) ────────────────────────────
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("[Emotion]: sounddevice not found — voice energy detection disabled.")
    print("           Fix: pip install sounddevice")

# ── OpenCV + MediaPipe (facial geometry) ──────────────────
try:
    import cv2
    import mediapipe as mp
    _ = mp.tasks.vision.FaceLandmarker
    MP_AVAILABLE = True
except (ImportError, AttributeError):
    MP_AVAILABLE = False
    print("[Emotion]: MediaPipe solutions API missing — facial emotion disabled.")


# ─────────────────────────────────────────────────────────
# MediaPipe Face Mesh Landmark Indices
# ─────────────────────────────────────────────────────────

# Mouth
MOUTH_LEFT   = 61    # left mouth corner
MOUTH_RIGHT  = 291   # right mouth corner
UPPER_LIP    = 13    # upper lip center
LOWER_LIP    = 14    # lower lip center
LIP_CENTER_Y = 0     # placeholder, computed dynamically

# Eyebrows (left & right)
LEFT_BROW_CENTER  = 105   # left eyebrow top-center
RIGHT_BROW_CENTER = 334   # right eyebrow top-center
LEFT_EYE_TOP      = 159   # left eye top
RIGHT_EYE_TOP     = 386   # right eye top

# Nose bridge (reference point for vertical normalization)
NOSE_TIP = 4


# ─────────────────────────────────────────────────────────
# Voice Energy–Based Emotion Detector
# ─────────────────────────────────────────────────────────

class VoiceEmotionDetector:
    """
    Classifies emotion from microphone energy (RMS loudness).

    Thresholds (tune to your mic):
      Very loud  -> angry
      Loud       -> happy
      Very quiet -> sad
      Normal     -> neutral
    """

    CHUNK    = 1024
    RATE     = 44100
    CHANNELS = 1

    ANGRY_THRESHOLD = 0.25
    HAPPY_THRESHOLD = 0.08
    SAD_THRESHOLD   = 0.01

    def __init__(self):
        self._emotion = "neutral"
        self._lock    = threading.Lock()
        self._running = False
        self._thread  = None

    def start(self) -> None:
        if not AUDIO_AVAILABLE or self._running:
            if not AUDIO_AVAILABLE:
                print("[Emotion]: sounddevice unavailable — emotion fixed at 'neutral'.")
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Emotion]: Voice energy detector started (sounddevice).")

    def stop(self) -> None:
        self._running = False

    def get_emotion(self) -> str:
        with self._lock:
            return self._emotion

    def _loop(self) -> None:
        try:
            while self._running:
                audio = sd.rec(self.CHUNK, samplerate=self.RATE,
                               channels=self.CHANNELS, dtype='float32',
                               blocking=True)
                rms = float(np.sqrt(np.mean(audio ** 2)))
                with self._lock:
                    self._emotion = self._classify(rms)
                time.sleep(0.1)
        except Exception as e:
            print(f"[Emotion]: Audio stream error — {e}")

    def _classify(self, rms: float) -> str:
        if rms >= self.ANGRY_THRESHOLD:
            return "angry"
        elif rms >= self.HAPPY_THRESHOLD:
            return "happy"
        elif rms <= self.SAD_THRESHOLD:
            return "sad"
        return "neutral"


# ─────────────────────────────────────────────────────────
# MediaPipe Landmark–Based Facial Emotion Detector
# ─────────────────────────────────────────────────────────

class FacialEmotionDetector:
    """
    Detects emotion from facial geometry using MediaPipe Face Mesh.

    No TensorFlow / DeepFace required — works on Python 3.14.

    Algorithm:
      1. Smile score   = how much lip corners are raised vs lip midpoint
      2. Brow score    = how high eyebrows sit relative to eyes
                         (low brow -> angry/sad, high brow -> neutral/happy)
      3. Mouth open    = distance between upper and lower lip

    Decision rules (after normalization by face height):
      happy  : smile_score > SMILE_THRESHOLD
      angry  : smile_score < FROWN_THRESHOLD AND brow_score < LOW_BROW
      sad    : smile_score < FROWN_THRESHOLD AND brow_score >= LOW_BROW
      neutral: everything else
    """

    # ── Geometric thresholds (normalized 0–1 relative to face height) ──
    SMILE_THRESHOLD = 0.012   # positive lip-corner lift -> happy
    FROWN_THRESHOLD = -0.008  # negative lip-corner drop -> sad/angry
    LOW_BROW        = 0.25    # eyebrow very close to eye -> angry
    OPEN_MOUTH      = 0.04    # mouth open proportion -> stress/surprise

    FPS_LIMIT = 10            # max frames/sec for emotion analysis

    def __init__(self, camera_index: int = 0):
        self._camera_index = camera_index
        self._emotion  = "neutral"
        self._lock     = threading.Lock()
        self._running  = False
        self._thread   = None

    def start(self) -> None:
        if not MP_AVAILABLE:
            print("[Emotion]: MediaPipe/OpenCV not available — facial emotion disabled.")
            return
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Emotion]: MediaPipe facial emotion detector started (no TensorFlow needed).")

    def stop(self) -> None:
        self._running = False

    def get_emotion(self) -> str:
        with self._lock:
            return self._emotion

    # ── Geometric helpers ─────────────────────────────────

    @staticmethod
    def _pt(lm, idx, w, h):
        """Return (x, y) pixel coords of landmark idx."""
        p = lm[idx]
        return p.x * w, p.y * h

    def _smile_score(self, lm, w, h, face_h: float) -> float:
        """
        Positive -> corners raised (smile).
        Negative -> corners dropped (frown).
        Normalized by face height.
        """
        lx, ly  = self._pt(lm, MOUTH_LEFT,  w, h)
        rx, ry  = self._pt(lm, MOUTH_RIGHT, w, h)
        ux, uy  = self._pt(lm, UPPER_LIP,   w, h)
        lox, loy = self._pt(lm, LOWER_LIP,   w, h)

        lip_mid_y = (uy + loy) / 2
        corner_y  = (ly + ry) / 2
        # Positive when corners are ABOVE midpoint (screen coords: smaller y = higher)
        score = (lip_mid_y - corner_y) / (face_h + 1e-6)
        return score

    def _brow_score(self, lm, w, h, face_h: float) -> float:
        """
        Normalized distance between eyebrow and eye top.
        Small value -> brow lowered -> angry/intense.
        """
        _, lb_y = self._pt(lm, LEFT_BROW_CENTER,  w, h)
        _, rb_y = self._pt(lm, RIGHT_BROW_CENTER, w, h)
        _, le_y = self._pt(lm, LEFT_EYE_TOP,       w, h)
        _, re_y = self._pt(lm, RIGHT_EYE_TOP,      w, h)

        brow_y = (lb_y + rb_y) / 2
        eye_y  = (le_y + re_y) / 2
        # Positive when brow is ABOVE eye (screen coords: smaller y = higher)
        dist = (eye_y - brow_y) / (face_h + 1e-6)
        return dist

    def _mouth_open(self, lm, w, h, face_h: float) -> float:
        """Normalized mouth-open distance."""
        _, uy = self._pt(lm, UPPER_LIP,  w, h)
        _, ly = self._pt(lm, LOWER_LIP, w, h)
        return abs(ly - uy) / (face_h + 1e-6)

    def _classify(self, smile: float, brow: float, open_m: float) -> str:
        """Map geometric scores to emotion label."""
        if smile > self.SMILE_THRESHOLD:
            return "happy"
        if smile < self.FROWN_THRESHOLD:
            if brow < self.LOW_BROW:
                return "angry"
            return "sad"
        if open_m > self.OPEN_MOUTH:
            return "neutral"   # could be surprise; map to neutral
        return "neutral"

    # ── Main loop ─────────────────────────────────────────

    def _loop(self) -> None:
        import os
        if not os.path.exists("face_landmarker.task"):
            print("[Emotion]: Downloading FaceLandmarker model...")
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
            min_face_detection_confidence=0.6,
            min_face_presence_confidence=0.6,
            min_tracking_confidence=0.6
        )
        face_mesh = FaceLandmarker.create_from_options(options)

        cap = cv2.VideoCapture(self._camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

        interval  = 1.0 / self.FPS_LIMIT
        prev_time = 0.0

        print("[Emotion]: Camera open for facial emotion (MediaPipe).")

        while self._running:
            now = time.time()
            if now - prev_time < interval:
                time.sleep(0.02)
                continue
            prev_time = now

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.2)
                continue

            h, w = frame.shape[:2]
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int(time.time() * 1000)
            result = face_mesh.detect_for_video(mp_image, timestamp_ms)

            if result.face_landmarks:
                lm = result.face_landmarks[0]

                # Face height = vertical distance nose to chin proxy
                _, ny = self._pt(lm, NOSE_TIP, w, h)
                _, cy = self._pt(lm, 152,       w, h)   # chin landmark
                face_h = abs(cy - ny)

                smile  = self._smile_score(lm, w, h, face_h)
                brow   = self._brow_score(lm, w, h, face_h)
                open_m = self._mouth_open(lm, w, h, face_h)

                emotion = self._classify(smile, brow, open_m)
                with self._lock:
                    self._emotion = emotion

        cap.release()
        face_mesh.close()
        print("[Emotion]: Facial emotion loop exited.")


# ─────────────────────────────────────────────────────────
# Unified Emotion Manager
# ─────────────────────────────────────────────────────────

class EmotionManager:
    """
    Fuses voice energy + optional MediaPipe facial geometry.

    Priority:
      1. Voice emotion (if non-neutral) — fastest signal
      2. Facial emotion (if use_face=True)
      3. Default: 'neutral'

    Enable facial via config.py:
      USE_DEEPFACE = True   ← this flag now activates MediaPipe facial emotion
                              (DeepFace is NOT used; MediaPipe runs instead)
    """

    def __init__(self, use_face: bool = False, camera_index: int = 0):
        self._voice = VoiceEmotionDetector()

        # USE_DEEPFACE flag now means "use facial emotion" (via MediaPipe)
        _use_facial = use_face or USE_DEEPFACE
        self._face  = FacialEmotionDetector(camera_index) if _use_facial else None

        if USE_DEEPFACE and not use_face:
            print("[Emotion]: USE_DEEPFACE=True — activating MediaPipe facial emotion "
                  "(no TensorFlow required).")

    def start(self) -> None:
        self._voice.start()
        if self._face:
            self._face.start()

    def stop(self) -> None:
        self._voice.stop()
        if self._face:
            self._face.stop()

    def get_emotion(self) -> str:
        """Voice overrides when non-neutral; falls back to facial or neutral."""
        voice_e = self._voice.get_emotion()
        if voice_e != "neutral":
            return voice_e
        if self._face:
            return self._face.get_emotion()
        return "neutral"
