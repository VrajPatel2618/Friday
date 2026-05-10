"""
vision.py - Face recognition module for FRIDAY user identification
Uses face_recognition + OpenCV to identify known users.
Maps identified users to the memory system.
"""

import os
import time
import threading
import numpy as np
from config import KNOWN_FACES_DIR, CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT

try:
    import face_recognition
    import cv2
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    print("[Vision]: face_recognition or OpenCV not installed — vision disabled.")


# ─────────────────────────────────────────────────────────
# Face Database Loader
# ─────────────────────────────────────────────────────────

def load_known_faces(faces_dir: str = KNOWN_FACES_DIR) -> tuple[list, list]:
    """
    Load all face encodings from the known_faces directory.

    Directory structure:
        known_faces/
            Alice.jpg       ← filename (without extension) = user name
            Bob.png
            ...

    Returns:
        (encodings_list, names_list)
    """
    encodings = []
    names = []

    if not VISION_AVAILABLE:
        return encodings, names

    if not os.path.isdir(faces_dir):
        os.makedirs(faces_dir, exist_ok=True)
        print(f"[Vision]: Created '{faces_dir}'. Add user face images there.")
        return encodings, names

    for filename in os.listdir(faces_dir):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        name = os.path.splitext(filename)[0]
        path = os.path.join(faces_dir, filename)
        try:
            image = face_recognition.load_image_file(path)
            face_encs = face_recognition.face_encodings(image)
            if face_encs:
                encodings.append(face_encs[0])
                names.append(name)
                print(f"[Vision]: Loaded face for '{name}'")
            else:
                print(f"[Vision]: No face detected in '{filename}' — skipping.")
        except Exception as e:
            print(f"[Vision]: Error loading '{filename}' — {e}")

    return encodings, names


# ─────────────────────────────────────────────────────────
# Single-frame Recognition
# ─────────────────────────────────────────────────────────

def recognize_user(
    known_encodings: list,
    known_names: list,
    tolerance: float = 0.55,
    attempts: int = 5,
    camera_index: int = CAMERA_INDEX
) -> str:
    """
    Capture frames from the camera and attempt to identify the user.

    Args:
        known_encodings: Pre-loaded face encodings.
        known_names:     Corresponding user names.
        tolerance:       Lower = stricter matching (0.4–0.6 typical).
        attempts:        Number of frames to analyze before giving up.
        camera_index:    OpenCV camera device index.

    Returns:
        Identified user name, or "Unknown" if no match found.
    """
    if not VISION_AVAILABLE:
        return "Unknown"

    if not known_encodings:
        print("[Vision]: No known faces loaded — returning 'Unknown'.")
        return "Unknown"

    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    detected_name = "Unknown"
    name_votes: dict[str, int] = {}

    for attempt in range(attempts):
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        # Downscale for faster processing
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb, model="hog")
        encodings = face_recognition.face_encodings(rgb, locations)

        for enc in encodings:
            matches = face_recognition.compare_faces(known_encodings, enc, tolerance=tolerance)
            distances = face_recognition.face_distance(known_encodings, enc)

            if True in matches:
                best_idx = int(np.argmin(distances))
                name = known_names[best_idx]
                name_votes[name] = name_votes.get(name, 0) + 1

        time.sleep(0.1)

    cap.release()

    # Majority vote across attempts
    if name_votes:
        detected_name = max(name_votes, key=name_votes.get)

    print(f"[Vision]: Recognized user -> '{detected_name}'")
    return detected_name


# ─────────────────────────────────────────────────────────
# Continuous Background Recognition
# ─────────────────────────────────────────────────────────

class FaceRecognitionManager:
    """
    Runs face recognition continuously in a background thread.
    Useful for dynamic user switching during a session.
    """

    def __init__(self, known_encodings: list, known_names: list, interval: float = 5.0):
        self._encodings = known_encodings
        self._names = known_names
        self._interval = interval          # Seconds between recognition attempts
        self._current_user = "Unknown"
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Vision]: Continuous recognition started.")

    def stop(self) -> None:
        self._running = False

    def get_current_user(self) -> str:
        with self._lock:
            return self._current_user

    def set_user_override(self, name: str) -> None:
        """Manually set the current user (e.g., after voice introduction)."""
        with self._lock:
            self._current_user = name

    def _loop(self) -> None:
        while self._running:
            try:
                name = recognize_user(self._encodings, self._names)
                with self._lock:
                    if name != "Unknown":
                        self._current_user = name
            except Exception as e:
                print(f"[Vision]: Recognition error — {e}")
            time.sleep(self._interval)
