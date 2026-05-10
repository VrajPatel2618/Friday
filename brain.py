"""
brain.py - AI conversation engine for FRIDAY
Supports three modes (set in config.py):

  "auto"   -> detects internet/API availability at runtime:
               Online  + valid key  -> OpenAI
               Offline OR no key   -> Ollama (local LLM)
               Ollama unavailable  -> built-in offline replies

  "openai" -> always use OpenAI (error if offline)
  "ollama" -> always use local Ollama (100% offline)
"""

import socket
import requests
import time
from config import (
    AI_BACKEND, OPENAI_API_KEY, OPENAI_MODEL,
    OLLAMA_BASE_URL, OLLAMA_MODEL, SYSTEM_PROMPT,
    CONNECTIVITY_CHECK_HOST, CONNECTIVITY_CHECK_PORT, CONNECTIVITY_TIMEOUT
)
import memory as mem


# ─────────────────────────────────────────────────────────
# Runtime state  (cached per session to avoid repeated checks)
# ─────────────────────────────────────────────────────────

_resolved_backend: str | None = None   # "openai" | "ollama" | "offline"
_last_check_time: float = 0.0
_CHECK_INTERVAL = 30.0                 # re-check connectivity every 30 s


# ─────────────────────────────────────────────────────────
# Connectivity helpers
# ─────────────────────────────────────────────────────────

def _is_online() -> bool:
    """
    Fast TCP check: can we reach api.openai.com:443?
    Returns True in < CONNECTIVITY_TIMEOUT seconds if online.
    """
    try:
        socket.setdefaulttimeout(CONNECTIVITY_TIMEOUT)
        with socket.create_connection(
            (CONNECTIVITY_CHECK_HOST, CONNECTIVITY_CHECK_PORT),
            timeout=CONNECTIVITY_TIMEOUT
        ):
            return True
    except (OSError, socket.timeout):
        return False


def _has_valid_api_key() -> bool:
    """Return True if the API key looks like a real key (not the placeholder)."""
    key = OPENAI_API_KEY.strip()
    return bool(key) and not key.startswith("your-")


def _is_ollama_running() -> bool:
    """Check if a local Ollama server is responding."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _resolve_backend() -> str:
    """
    Determine which backend to use right now.
    Result is cached for _CHECK_INTERVAL seconds.

    Resolution order (auto mode):
      1. OpenAI   — if online AND valid API key
      2. Ollama   — if Ollama server is running locally
      3. offline  — built-in canned responses (no AI)
    """
    global _resolved_backend, _last_check_time

    # Use cache if recent enough
    if _resolved_backend and (time.time() - _last_check_time < _CHECK_INTERVAL):
        return _resolved_backend

    if AI_BACKEND == "openai":
        _resolved_backend = "openai"
    elif AI_BACKEND == "ollama":
        _resolved_backend = "ollama"
    else:  # "auto"
        if _has_valid_api_key() and _is_online():
            backend = "openai"
            print("[Brain]: Online — using OpenAI.")
        elif _is_ollama_running():
            backend = "ollama"
            print("[Brain]: Offline/no key — using local Ollama.")
        else:
            backend = "offline"
            print("[Brain]: Fully offline — using built-in responses.")
        _resolved_backend = backend

    _last_check_time = time.time()
    return _resolved_backend


# ─────────────────────────────────────────────────────────
# OpenAI Backend
# ─────────────────────────────────────────────────────────

def _ask_openai(messages: list) -> str:
    """Send a message list to OpenAI and return the assistant reply."""
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.75,
            max_tokens=512
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        err = str(e).lower()
        # If it's a connectivity/auth issue, downgrade to Ollama for this session
        if any(k in err for k in ["auth", "connect", "timeout", "network", "rate"]):
            print(f"[Brain]: OpenAI failed ({e}) — falling back to Ollama.")
            global _resolved_backend
            _resolved_backend = "ollama" if _is_ollama_running() else "offline"
            return ask_ai.__wrapped_call__  # signal re-route (handled in ask_ai)
        return f"Sorry, I had trouble reaching OpenAI: {e}"


def _ask_openai_safe(messages: list) -> tuple[str, bool]:
    """
    Returns (reply, success).
    If success=False, caller should try Ollama.
    """
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.75,
            max_tokens=512
        )
        return response.choices[0].message.content.strip(), True
    except Exception as e:
        print(f"[Brain]: OpenAI error — {e}")
        return "", False


# ─────────────────────────────────────────────────────────
# Ollama Backend (local LLM)
# ─────────────────────────────────────────────────────────

def _ask_ollama_safe(messages: list) -> tuple[str, bool]:
    """
    Returns (reply, success).
    If success=False, caller should use offline responses.
    """
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False
        }
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip(), True
    except requests.ConnectionError:
        print("[Brain]: Ollama server unreachable.")
        return "", False
    except Exception as e:
        print(f"[Brain]: Ollama error — {e}")
        return "", False


# ─────────────────────────────────────────────────────────
# Offline Fallback (no internet, no Ollama)
# ─────────────────────────────────────────────────────────

_OFFLINE_RESPONSES = {
    "hello":      "Hello! I'm running in offline mode right now.",
    "hi":         "Hi there! Note: I'm offline so my responses are limited.",
    "how are you":"I'm fully operational locally, though my AI brain is offline.",
    "time":       None,   # handled dynamically below
    "date":       None,
    "default":    (
        "I'm currently in offline mode — I can't reach my AI backend. "
        "I can still help with system commands, gestures, and memory recall. "
        "For full AI conversation, connect to the internet or start Ollama locally."
    )
}

def _offline_response(prompt: str) -> str:
    """Return a canned offline response based on keyword matching."""
    from datetime import datetime
    p = prompt.lower().strip()

    if any(w in p for w in ["time", "clock"]):
        return f"The current time is {datetime.now().strftime('%I:%M %p')}."
    if any(w in p for w in ["date", "today", "day"]):
        return f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."
    if any(w in p for w in ["hello", "hi", "hey"]):
        return _OFFLINE_RESPONSES["hello"]
    if "how are you" in p:
        return _OFFLINE_RESPONSES["how are you"]
    if any(w in p for w in ["weather"]):
        return "I need internet access to check the weather. I'm currently offline."
    if any(w in p for w in ["joke"]):
        return "Why don't scientists trust atoms? Because they make up everything!"

    return _OFFLINE_RESPONSES["default"]


# ─────────────────────────────────────────────────────────
# Core Public Function
# ─────────────────────────────────────────────────────────

def ask_ai(prompt: str, user: str = "User", emotion: str = "neutral") -> str:
    """
    Send a prompt to the best available AI backend.

    Resolution order (auto mode):
      Online + API key -> OpenAI
          ↓ fails
      Ollama running   -> Ollama
          ↓ fails
      Always           -> Offline built-in response

    Args:
        prompt:  The user's current message.
        user:    Identified user name (loads memory context).
        emotion: Detected emotion string.

    Returns:
        The assistant's response string.
    """
    backend = _resolve_backend()

    # Build memory context
    memory_context = mem.build_context_summary(user)

    emotion_note = {
        "happy":   "The user seems happy. Be enthusiastic and match their energy.",
        "sad":     "The user seems sad. Be empathetic, gentle, and supportive.",
        "angry":   "The user seems frustrated. Stay calm and de-escalating.",
        "neutral": "The user is calm. Be professional and helpful."
    }.get(emotion.lower(), "Be professional and helpful.")

    system_content = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- Memory Context ---\n{memory_context}\n\n"
        f"--- Emotional Context ---\n{emotion_note}"
    )

    history = mem.get_conversation_history(user)
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    reply = None

    # ── Try primary backend ───────────────────────────────
    if backend == "openai":
        reply_text, ok = _ask_openai_safe(messages)
        if ok:
            reply = reply_text
        else:
            # Downgrade: try Ollama
            print("[Brain]: OpenAI failed — trying Ollama...")
            global _resolved_backend
            if _is_ollama_running():
                _resolved_backend = "ollama"
                reply_text, ok = _ask_ollama_safe(messages)
                reply = reply_text if ok else None
            else:
                _resolved_backend = "offline"

    elif backend == "ollama":
        reply_text, ok = _ask_ollama_safe(messages)
        if ok:
            reply = reply_text
        else:
            # Downgrade: try OpenAI if we have a key + internet
            if _has_valid_api_key() and _is_online():
                print("[Brain]: Ollama failed — trying OpenAI...")
                _resolved_backend = "openai"
                reply_text, ok = _ask_openai_safe(messages)
                reply = reply_text if ok else None
            else:
                _resolved_backend = "offline"

    # ── Final fallback: offline canned response ───────────
    if reply is None:
        reply = _offline_response(prompt)

    # ── Persist to memory ─────────────────────────────────
    mem.add_conversation_turn(user, "user", prompt)
    mem.add_conversation_turn(user, "assistant", reply)
    mem.extract_and_store_facts(user, prompt, reply)

    return reply


# ─────────────────────────────────────────────────────────
# Status / Utility
# ─────────────────────────────────────────────────────────

def get_status() -> str:
    """Return a human-readable string of current backend status."""
    backend = _resolve_backend()
    mode_label = {
        "openai":  "Online  (OpenAI)",
        "ollama":  "Offline (Local Ollama)",
        "offline": "Offline (Built-in responses only)"
    }
    return mode_label.get(backend, backend)


def is_recall_query(text: str) -> bool:
    """
    Return True if the user is asking FRIDAY to recall stored information.
    Examples: 'What do I like?', 'What do you know about me?'
    """
    recall_phrases = [
        "what do i like", "what do you know about me",
        "what do you remember", "what have i told you",
        "recall", "remember about me", "my preferences",
        "what are my interests", "what do i hate"
    ]
    return any(phrase in text.lower() for phrase in recall_phrases)
