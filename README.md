# 🤖 FRIDAY — Modular AI Personal Assistant

A scalable, FRIDAY-like AI assistant built in Python with voice interaction, contextual memory, emotion detection, hand gesture control, and face recognition.

---

## 📁 Project Structure

```
Model/
├── main.py          # Main loop — orchestrates all modules
├── config.py        # Central configuration (API keys, thresholds)
├── voice.py         # Speech-to-text (STT) + Text-to-speech (TTS)
├── brain.py         # AI conversation engine (OpenAI / Ollama)
├── memory.py        # Smart memory system (JSON persistence)
├── emotion.py       # Emotion detection (voice energy + optional facial)
├── gesture.py       # Hand gesture control (MediaPipe + PyAutoGUI)
├── vision.py        # Face recognition (face_recognition + OpenCV)
├── commands.py      # Hardcoded system command handler
├── requirements.txt # Python dependencies
└── known_faces/     # Add user face images here (Alice.jpg, Bob.png ...)
```

---

## ⚡ Quick Start

### 1. Install Dependencies

```bash
# Core packages
pip install openai SpeechRecognition pyttsx3 requests numpy

# Vision & Gesture
pip install opencv-python mediapipe pyautogui

# PyAudio (Windows — use one of these methods)
pip install pipwin
pipwin install pyaudio
# OR download .whl from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

# Face recognition (requires dlib → needs Visual C++ Build Tools)
pip install cmake dlib
pip install face_recognition
```

### 2. Configure API Key

Edit `config.py`:
```python
OPENAI_API_KEY = "sk-your-key-here"
AI_BACKEND = "openai"      # or "ollama" for local LLM
```

Or set an environment variable:
```bash
set OPENAI_API_KEY=sk-your-key-here   # Windows
```

### 3. Add Known Faces (Optional)

Place face images in the `known_faces/` folder:
```
known_faces/
    Alice.jpg    ← the filename (without extension) becomes the user name
    Bob.png
```

### 4. Run FRIDAY

```bash
python main.py
```

### 5. Run Gesture Control Standalone

```bash
python gesture.py
```

---

## 🗣️ Voice Commands

| Command | Action |
|---------|--------|
| `Open Chrome` | Launches Google Chrome |
| `Open Notepad` | Opens Notepad |
| `Shutdown the computer` | System shutdown in 5s |
| `Restart the system` | System restart in 5s |
| `Start gesture control` | Activates hand gesture mode |
| `Stop gesture control` | Deactivates gesture mode |
| `What do you know about me?` | Recalls stored memory |
| `Clear conversation` | Clears conversation history |
| `Exit FRIDAY` | Graceful shutdown |
| *Anything else* | Sent to AI for a smart response |

---

## 🖐️ Gesture Controls

| Gesture | Action |
|---------|--------|
| Index finger raised | Move mouse cursor |
| Pinch (thumb + index) | Left click |

> Press **Q** in the gesture window to close it.

---

## 🧠 Memory System

The memory system (`memory.py`) automatically:
- Stores your **name**, **preferences**, and **interests** from conversation
- Injects stored facts into every AI prompt as context
- Limits storage to the **30 most recent facts** (configurable)
- Keeps the last **10 conversation turns** for multi-turn context
- Persists everything to `friday_memory.json`

---

## 🎭 Emotion Detection

| Emotion | Trigger |
|---------|---------|
| `angry` | Very loud voice (high RMS energy) |
| `happy` | Moderately loud voice |
| `sad` | Very quiet voice |
| `neutral` | Normal voice level |

FRIDAY adjusts its **tone and style** based on detected emotion.

**Upgrade to facial emotion detection:**
```bash
pip install deepface
```
Then uncomment the DeepFace block in `emotion.py` and set `use_face=True` in `main.py`.

---

## 🤖 AI Backends

### OpenAI (default)
```python
AI_BACKEND = "openai"
OPENAI_MODEL = "gpt-4o-mini"   # or "gpt-4o", "gpt-3.5-turbo"
```

### Ollama (local LLM — free, no API key needed)
```bash
# 1. Install Ollama: https://ollama.ai
# 2. Pull a model:
ollama pull llama3
# 3. Update config.py:
AI_BACKEND = "ollama"
OLLAMA_MODEL = "llama3"
```

---

## ⚙️ Configuration Reference (`config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `AI_BACKEND` | `"openai"` | `"openai"` or `"ollama"` |
| `OPENAI_MODEL` | `"gpt-4o-mini"` | OpenAI model name |
| `VOICE_RATE` | `175` | TTS words per minute |
| `ENERGY_THRESHOLD` | `300` | Mic sensitivity |
| `MAX_MEMORY_FACTS` | `30` | Facts stored per user |
| `MAX_CONTEXT_TURNS` | `10` | Conversation turns in context |
| `PINCH_THRESHOLD` | `40` | Pixel distance for pinch click |
| `CLICK_COOLDOWN` | `1.0` | Seconds between clicks |
| `SMOOTHING_BUFFER` | `5` | Cursor smoothing frames |
| `GESTURE_FPS_LIMIT` | `20` | Max gesture processing FPS |

---

## 🔧 Troubleshooting

**No microphone detected:**
```bash
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"
```

**PyAudio install fails on Windows:**
```bash
pip install pipwin && pipwin install pyaudio
```

**face_recognition install fails:**
```bash
# Install Visual C++ Build Tools first, then:
pip install cmake dlib face_recognition
```

**Gesture window doesn't open:**
Make sure `opencv-python` and `mediapipe` are installed and no other camera app is using the webcam.

**OpenAI returns auth error:**
Verify your API key is set correctly in `config.py` or as environment variable `OPENAI_API_KEY`.

---

## 🚀 Extending FRIDAY

| Feature | How to Add |
|---------|-----------|
| New gesture | Add elif block in `gesture.py → _loop()` |
| New app shortcut | Add entry to `APP_MAP` in `commands.py` |
| Advanced emotion | Uncomment DeepFace in `emotion.py` |
| Smart home control | Add MQTT/Home Assistant calls in `commands.py` |
| Dashboard UI | Create `dashboard.py` using tkinter or Flask |
| Wake word | Add `pvporcupine` for "Hey FRIDAY" detection |
