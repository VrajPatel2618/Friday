import cv2
import mediapipe as mp

BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.IMAGE,
    num_hands=1)

with HandLandmarker.create_from_options(options) as landmarker:
    # try dummy image
    import numpy as np
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=dummy)
    result = landmarker.detect(mp_image)
    print("Success, hand landmarks:", len(result.hand_landmarks))
