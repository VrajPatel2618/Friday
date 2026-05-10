"""
memory.py - Smart contextual memory system for FRIDAY
Stores user facts, preferences, and conversation context using JSON.
"""

import json
import os
import time
from datetime import datetime
from config import MEMORY_FILE, MAX_MEMORY_FACTS, MAX_CONTEXT_TURNS


# ─────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────

def _load_db() -> dict:
    """Load the full memory database from disk."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_db(db: dict) -> None:
    """Persist the memory database to disk."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def _get_user_record(db: dict, user: str) -> dict:
    """Return or create a user record inside the database."""
    if user not in db:
        db[user] = {
            "name": user,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "preferences": {},
            "facts": [],          # List[{key, value, timestamp}]
            "conversation": []    # Recent turns for multi-turn context
        }
    return db[user]


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────

def load_memory(user: str) -> dict:
    """
    Load and return the memory profile for a given user.
    Creates a new profile if the user is unknown.
    """
    db = _load_db()
    record = _get_user_record(db, user)
    record["last_seen"] = datetime.now().isoformat()
    _save_db(db)
    return record


def save_fact(user: str, key: str, value: str) -> None:
    """
    Store a meaningful fact about the user.
    Duplicate keys are overwritten; oldest entries pruned if over limit.
    """
    db = _load_db()
    record = _get_user_record(db, user)

    # Remove existing fact with same key (update)
    record["facts"] = [f for f in record["facts"] if f["key"] != key]

    # Append new fact
    record["facts"].append({
        "key": key,
        "value": value,
        "timestamp": datetime.now().isoformat()
    })

    # Prune oldest facts if over limit
    if len(record["facts"]) > MAX_MEMORY_FACTS:
        record["facts"] = record["facts"][-MAX_MEMORY_FACTS:]

    _save_db(db)


def save_preference(user: str, pref_key: str, pref_value: str) -> None:
    """Store a user preference (e.g., music = jazz, language = English)."""
    db = _load_db()
    record = _get_user_record(db, user)
    record["preferences"][pref_key] = pref_value
    _save_db(db)


def get_facts(user: str) -> list:
    """Return all stored facts for a user."""
    db = _load_db()
    record = _get_user_record(db, user)
    return record.get("facts", [])


def get_preferences(user: str) -> dict:
    """Return all stored preferences for a user."""
    db = _load_db()
    record = _get_user_record(db, user)
    return record.get("preferences", {})


def build_context_summary(user: str) -> str:
    """
    Build a concise memory context string to inject into AI prompts.
    Includes name, preferences, and key facts.
    """
    db = _load_db()
    record = _get_user_record(db, user)

    lines = [f"User's name: {user}"]

    prefs = record.get("preferences", {})
    if prefs:
        pref_str = ", ".join(f"{k}={v}" for k, v in prefs.items())
        lines.append(f"Preferences: {pref_str}")

    facts = record.get("facts", [])
    if facts:
        fact_str = "; ".join(f"{f['key']}: {f['value']}" for f in facts[-10:])
        lines.append(f"Known facts: {fact_str}")

    return "\n".join(lines)


def add_conversation_turn(user: str, role: str, content: str) -> None:
    """
    Append a message turn to the user's conversation history.
    Trims to the last MAX_CONTEXT_TURNS turns to avoid prompt bloat.
    """
    db = _load_db()
    record = _get_user_record(db, user)
    record["conversation"].append({"role": role, "content": content})

    # Keep only recent turns
    if len(record["conversation"]) > MAX_CONTEXT_TURNS * 2:
        record["conversation"] = record["conversation"][-(MAX_CONTEXT_TURNS * 2):]

    _save_db(db)


def get_conversation_history(user: str) -> list:
    """Return the recent conversation history (list of {role, content} dicts)."""
    db = _load_db()
    record = _get_user_record(db, user)
    return record.get("conversation", [])


def clear_conversation(user: str) -> None:
    """Clear the in-memory conversation context (keeps facts and preferences)."""
    db = _load_db()
    record = _get_user_record(db, user)
    record["conversation"] = []
    _save_db(db)


def extract_and_store_facts(user: str, user_input: str, ai_response: str) -> None:
    """
    Selectively extract meaningful facts from a conversation turn.
    Uses simple keyword heuristics — no heavy NLP dependency required.
    """
    text = user_input.lower()

    # Detect name disclosure
    for phrase in ["my name is", "i am called", "call me"]:
        if phrase in text:
            name_candidate = text.split(phrase)[-1].strip().split()[0].capitalize()
            if len(name_candidate) > 1:
                save_fact(user, "preferred_name", name_candidate)
                break

    # Detect likes / interests
    for phrase in ["i like", "i love", "i enjoy", "i prefer", "i'm into"]:
        if phrase in text:
            interest = text.split(phrase)[-1].strip().rstrip(".")
            if 2 < len(interest) < 80:
                save_fact(user, f"interest_{int(time.time())}", interest)
                break

    # Detect dislikes
    for phrase in ["i hate", "i dislike", "i don't like", "i do not like"]:
        if phrase in text:
            dislike = text.split(phrase)[-1].strip().rstrip(".")
            if 2 < len(dislike) < 80:
                save_fact(user, f"dislike_{int(time.time())}", dislike)
                break

    # Detect occupation / role
    for phrase in ["i work as", "i am a", "i'm a", "my job is"]:
        if phrase in text:
            job = text.split(phrase)[-1].strip().split(".")[0]
            if 2 < len(job) < 60:
                save_preference(user, "occupation", job)
                break


def recall_memory(user: str, query: str) -> str:
    """
    Simple recall: return a formatted summary of what FRIDAY knows about the user.
    Called when the user asks things like 'What do you know about me?'
    """
    facts = get_facts(user)
    prefs = get_preferences(user)

    if not facts and not prefs:
        return f"I don't have much information stored about you yet, {user}."

    parts = [f"Here's what I remember about you, {user}:"]
    if prefs:
        for k, v in prefs.items():
            parts.append(f"  • {k.replace('_', ' ').title()}: {v}")
    if facts:
        for f in facts[-10:]:
            parts.append(f"  • {f['key'].replace('_', ' ').title()}: {f['value']}")

    return "\n".join(parts)
