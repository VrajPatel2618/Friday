@echo off
TITLE FRIDAY AI Assistant — Setup

echo ==============================================
echo  Installing FRIDAY Core Dependencies
echo ==============================================

echo.
echo [1/5] Installing core AI + voice packages...
pip install openai SpeechRecognition pyttsx3 requests numpy

echo.
echo [2/5] Installing PyAudio (microphone support)...
pip install pipwin
pipwin install pyaudio

echo.
echo [3/5] Installing vision + gesture packages...
pip install opencv-python mediapipe pyautogui

echo.
echo [4/5] Installing face recognition (requires cmake + dlib)...
pip install cmake
pip install dlib
pip install face_recognition

echo.
echo [5/5] Running module check...
python test_modules.py

echo.
echo ==============================================
echo  Setup complete! Run FRIDAY with:
echo    python main.py
echo  Or gesture control only:
echo    python gesture.py
echo ==============================================
pause
