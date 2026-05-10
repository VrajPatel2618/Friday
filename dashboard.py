"""
dashboard.py - FRIDAY System Dashboard (tkinter)
A live monitoring window that shows:
  • AI Backend status          • Current user & emotion
  • Active modules             • Conversation log
  • System stats (CPU/RAM)     • Quick control buttons

Run standalone:    python dashboard.py
Or launch via:     "open dashboard" voice command
"""

import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, font as tkfont
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ─────────────────────────────────────────────────────────
# Colour Palette  (dark FRIDAY theme)
# ─────────────────────────────────────────────────────────

C = {
    "bg":        "#0a0e1a",   # deep navy black
    "panel":     "#0f1629",   # card background
    "border":    "#1e3a5f",   # blue border
    "accent":    "#00d4ff",   # FRIDAY cyan
    "accent2":   "#0066ff",   # secondary blue
    "green":     "#00ff88",   # online / active
    "yellow":    "#ffd700",   # warning
    "red":       "#ff4444",   # error / offline
    "text":      "#c8e6ff",   # primary text
    "dim":       "#4a7090",   # dimmed text
    "white":     "#ffffff",
}


# ─────────────────────────────────────────────────────────
# Reusable Card Widget
# ─────────────────────────────────────────────────────────

class Card(tk.Frame):
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent,
                         bg=C["panel"],
                         highlightbackground=C["border"],
                         highlightthickness=1,
                         padx=10, pady=8,
                         **kwargs)

        tk.Label(self, text=f"  {title}  ",
                 bg=C["border"], fg=C["accent"],
                 font=("Consolas", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 6))


# ─────────────────────────────────────────────────────────
# Status Indicator (circle + label)
# ─────────────────────────────────────────────────────────

class StatusRow(tk.Frame):
    def __init__(self, parent, label: str, initial_value: str = "—",
                 color: str = C["dim"]):
        super().__init__(parent, bg=C["panel"])
        self._dot = tk.Label(self, text="●", fg=color,
                             bg=C["panel"], font=("Arial", 10))
        self._dot.pack(side="left")
        tk.Label(self, text=f" {label}:  ", bg=C["panel"],
                 fg=C["dim"], font=("Consolas", 9)).pack(side="left")
        self._val = tk.Label(self, text=initial_value,
                             bg=C["panel"], fg=C["text"],
                             font=("Consolas", 9, "bold"))
        self._val.pack(side="left")
        self.pack(fill="x", pady=1)

    def update(self, value: str, color: str = None):
        self._val.config(text=value)
        if color:
            self._dot.config(fg=color)
            self._val.config(fg=color)


# ─────────────────────────────────────────────────────────
# Main Dashboard Window
# ─────────────────────────────────────────────────────────

class FridayDashboard:
    """
    Tkinter-based FRIDAY monitoring dashboard.

    Usage:
        dash = FridayDashboard()
        dash.start()                      # opens window in background thread

    Update from FRIDAY main loop:
        dash.set_status(user="Alice", emotion="happy", backend="OpenAI")
        dash.log("FRIDAY", "Good morning, Alice!")
        dash.set_module("Gesture", True)
    """

    def __init__(self, on_close_callback=None):
        self._on_close = on_close_callback
        self._root: tk.Tk | None = None
        self._thread = None
        self._running = False

        # Shared state (written from any thread, read by GUI thread)
        self._state_lock = threading.Lock()
        self._state = {
            "user":    "Unknown",
            "emotion": "neutral",
            "backend": "Checking...",
            "gesture": False,
            "head":    False,
            "vision":  False,
            "emotion_module": True,
        }
        self._log_queue: list[tuple[str, str]] = []

    # ── Public API (thread-safe) ──────────────────────────

    def set_status(self, **kwargs):
        """Update any state fields. Keys match self._state."""
        with self._state_lock:
            self._state.update(kwargs)

    def set_module(self, name: str, active: bool):
        """Toggle a module indicator. name: 'gesture'|'head'|'vision'."""
        with self._state_lock:
            self._state[name.lower()] = active

    def log(self, speaker: str, text: str):
        """Append a line to the conversation log."""
        ts = datetime.now().strftime("%H:%M:%S")
        with self._state_lock:
            self._log_queue.append((ts, speaker, text))

    def start(self):
        """Open the dashboard in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    # ── GUI Thread ────────────────────────────────────────

    def _run_gui(self):
        self._root = tk.Tk()
        self._root.title("FRIDAY — System Dashboard")
        self._root.configure(bg=C["bg"])
        self._root.geometry("780x620")
        self._root.resizable(True, True)
        self._root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._build_ui()
        self._tick()
        self._root.mainloop()

    def _on_window_close(self):
        self._running = False
        if self._on_close:
            self._on_close()
        self._root.destroy()

    # ── UI Construction ───────────────────────────────────

    def _build_ui(self):
        root = self._root

        # ── Title bar ─────────────────────────────────────
        title_frame = tk.Frame(root, bg=C["bg"])
        title_frame.pack(fill="x", padx=12, pady=(10, 2))

        tk.Label(title_frame, text="⚡ FRIDAY",
                 bg=C["bg"], fg=C["accent"],
                 font=("Consolas", 22, "bold")).pack(side="left")
        tk.Label(title_frame, text="  System Dashboard",
                 bg=C["bg"], fg=C["dim"],
                 font=("Consolas", 12)).pack(side="left", pady=6)

        self._clock_label = tk.Label(title_frame, text="",
                                      bg=C["bg"], fg=C["dim"],
                                      font=("Consolas", 10))
        self._clock_label.pack(side="right", padx=4)

        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=12)

        # ── Main content ──────────────────────────────────
        main = tk.Frame(root, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=12, pady=6)

        # Left column
        left = tk.Frame(main, bg=C["bg"])
        left.pack(side="left", fill="both", expand=False, padx=(0, 6))

        # Right column
        right = tk.Frame(main, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        self._build_identity_card(left)
        self._build_modules_card(left)
        self._build_sysinfo_card(left)
        self._build_controls_card(left)

        self._build_log_card(right)

        # Bottom bar
        self._status_bar = tk.Label(root, text=" Ready",
                                     bg=C["border"], fg=C["accent"],
                                     font=("Consolas", 8), anchor="w")
        self._status_bar.pack(fill="x", side="bottom")

    def _build_identity_card(self, parent):
        card = Card(parent, "🧑  IDENTITY")
        card.pack(fill="x", pady=(0, 6))

        self._row_user    = StatusRow(card, "User",    "—",         C["dim"])
        self._row_emotion = StatusRow(card, "Emotion", "neutral",   C["accent"])
        self._row_backend = StatusRow(card, "Backend", "Checking",  C["yellow"])

    def _build_modules_card(self, parent):
        card = Card(parent, "🔧  MODULES")
        card.pack(fill="x", pady=(0, 6))

        self._row_gesture = StatusRow(card, "Hand Gesture", "OFF", C["red"])
        self._row_head    = StatusRow(card, "Head Control", "OFF", C["red"])
        self._row_vision  = StatusRow(card, "Face Vision",  "OFF", C["red"])
        self._row_emotion_mod = StatusRow(card, "Emotion Detect", "ON", C["green"])

    def _build_sysinfo_card(self, parent):
        card = Card(parent, "💻  SYSTEM")
        card.pack(fill="x", pady=(0, 6))

        self._row_cpu  = StatusRow(card, "CPU",    "—%",  C["accent"])
        self._row_ram  = StatusRow(card, "RAM",    "—%",  C["accent"])
        self._row_disk = StatusRow(card, "Disk",   "—%",  C["accent"])

    def _build_controls_card(self, parent):
        card = Card(parent, "🎮  QUICK ACTIONS")
        card.pack(fill="x")

        btn_cfg = dict(
            bg=C["accent2"], fg=C["white"],
            font=("Consolas", 8, "bold"),
            relief="flat", cursor="hand2",
            padx=6, pady=4, bd=0,
            activebackground=C["accent"], activeforeground=C["white"]
        )
        btns = tk.Frame(card, bg=C["panel"])
        btns.pack(fill="x")

        tk.Button(btns, text="Clear Log",
                  command=self._clear_log, **btn_cfg).pack(
                      side="left", padx=2, pady=2)
        tk.Button(btns, text="Refresh",
                  command=self._force_refresh, **btn_cfg).pack(
                      side="left", padx=2, pady=2)

    def _build_log_card(self, parent):
        card = Card(parent, "💬  CONVERSATION LOG")
        card.pack(fill="both", expand=True)

        self._log_text = scrolledtext.ScrolledText(
            card,
            bg=C["bg"], fg=C["text"],
            font=("Consolas", 9),
            relief="flat", bd=0,
            wrap="word",
            state="disabled",
            insertbackground=C["accent"]
        )
        self._log_text.pack(fill="both", expand=True)

        # Tag colours
        self._log_text.tag_config("time",    foreground=C["dim"])
        self._log_text.tag_config("friday",  foreground=C["accent"])
        self._log_text.tag_config("user",    foreground=C["green"])
        self._log_text.tag_config("system",  foreground=C["yellow"])
        self._log_text.tag_config("msg",     foreground=C["text"])

    # ── Periodic Updates ──────────────────────────────────

    def _tick(self):
        """Called every 500ms by tkinter mainloop to refresh UI."""
        if not self._running:
            return
        try:
            self._refresh_clock()
            self._refresh_state()
            self._flush_log()
            if PSUTIL_AVAILABLE:
                self._refresh_sysinfo()
        except Exception as e:
            print(f"[Dashboard]: Tick error — {e}")
        self._root.after(500, self._tick)

    def _refresh_clock(self):
        now = datetime.now().strftime("%a %d %b  %H:%M:%S")
        self._clock_label.config(text=now)

    def _refresh_state(self):
        with self._state_lock:
            s = dict(self._state)

        # Identity
        self._row_user.update(s["user"], C["white"])

        emotion = s["emotion"]
        emotion_color = {
            "happy": C["green"], "sad": C["accent2"],
            "angry": C["red"],   "neutral": C["text"]
        }.get(emotion, C["text"])
        self._row_emotion.update(emotion.upper(), emotion_color)

        backend = s["backend"]
        b_color = C["green"] if "OpenAI" in backend or "Ollama" in backend else C["yellow"]
        self._row_backend.update(backend, b_color)

        # Modules
        def _mod(row, active):
            row.update("ON" if active else "OFF",
                       C["green"] if active else C["red"])

        _mod(self._row_gesture,     s["gesture"])
        _mod(self._row_head,        s["head"])
        _mod(self._row_vision,      s["vision"])
        _mod(self._row_emotion_mod, s["emotion_module"])

    def _refresh_sysinfo(self):
        try:
            cpu  = psutil.cpu_percent(interval=None)
            ram  = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            cpu_c  = C["green"] if cpu  < 70 else C["yellow"] if cpu  < 90 else C["red"]
            ram_c  = C["green"] if ram  < 70 else C["yellow"] if ram  < 90 else C["red"]
            disk_c = C["green"] if disk < 80 else C["yellow"] if disk < 95 else C["red"]
            self._row_cpu.update(f"{cpu:.0f}%",  cpu_c)
            self._row_ram.update(f"{ram:.0f}%",  ram_c)
            self._row_disk.update(f"{disk:.0f}%", disk_c)
        except Exception:
            pass

    def _flush_log(self):
        with self._state_lock:
            entries = list(self._log_queue)
            self._log_queue.clear()

        if not entries:
            return

        self._log_text.config(state="normal")
        for item in entries:
            ts, speaker, text = item
            tag = "friday" if speaker.upper() == "FRIDAY" else \
                  "system" if speaker.upper() == "SYSTEM" else "user"
            self._log_text.insert("end", f"[{ts}] ", "time")
            self._log_text.insert("end", f"{speaker}: ", tag)
            self._log_text.insert("end", f"{text}\n", "msg")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    def _force_refresh(self):
        self._status_bar.config(text=" Refreshed at " +
                                 datetime.now().strftime("%H:%M:%S"))


# ─────────────────────────────────────────────────────────
# Standalone demo
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    dash = FridayDashboard()
    dash.start()

    # Wait for window to open
    time.sleep(0.8)

    # Simulate live updates
    dash.log("SYSTEM", "Dashboard initialized.")
    dash.log("FRIDAY", "Good afternoon! FRIDAY online and ready.")
    dash.log("User",   "Open Chrome")
    dash.log("FRIDAY", "Opening Google Chrome.")
    dash.set_status(user="Demo User", emotion="happy", backend="OpenAI (GPT-4o-mini)")
    dash.set_module("Gesture", True)

    i = 0
    emotions = ["neutral", "happy", "sad", "angry", "neutral"]
    try:
        while True:
            time.sleep(2)
            i += 1
            dash.set_status(emotion=emotions[i % len(emotions)])
            dash.log("SYSTEM", f"Tick #{i} — all systems nominal.")
    except KeyboardInterrupt:
        dash.stop()
        print("Dashboard closed.")
