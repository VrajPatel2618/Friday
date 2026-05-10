"""
smarthome_setup.py - Home Assistant Auto-Setup for FRIDAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run this once to configure smart home:
    python smarthome_setup.py

What it does:
  1. Scans your local network for Home Assistant (port 8123)
  2. Tests the connection
  3. Guides you to create a Long-Lived Access Token
  4. Writes HA_URL + HA_TOKEN into a .env file
  5. Tests the full connection with the token
  6. Lists all your HA entities (lights, switches, etc.)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import socket
import subprocess
import sys
import os
import json
import threading
from datetime import datetime

# Fix Unicode output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Dependency check ──────────────────────────────────────
try:
    import requests
except ImportError:
    print("[Setup]: Installing requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


# ─────────────────────────────────────────────────────────
# Network Scanner
# ─────────────────────────────────────────────────────────

def get_local_subnet() -> str:
    """Get the local machine's IP to derive subnet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        # Return subnet base e.g. "192.168.1"
        return ".".join(ip.split(".")[:3])
    except Exception:
        return "192.168.1"


def scan_for_ha(subnet: str, port: int = 8123, timeout: float = 0.4) -> list[str]:
    """
    Scan the subnet for devices listening on port 8123 (Home Assistant default).
    Returns list of IPs that responded.
    """
    found = []
    lock  = threading.Lock()

    def check(ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            if result == 0:
                with lock:
                    found.append(ip)
        except Exception:
            pass

    print(f"\n[Scan]: Scanning {subnet}.1 – {subnet}.254 on port {port}...")
    print("        This takes ~15 seconds. Please wait...")

    threads = []
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        t  = threading.Thread(target=check, args=(ip,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return found


def verify_ha(url: str, timeout: int = 5) -> bool:
    """Check if URL is actually a Home Assistant instance."""
    try:
        resp = requests.get(f"{url}/api/", timeout=timeout)
        return resp.status_code in (200, 401)   # 401 = needs auth = still HA
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# Home Assistant API helpers
# ─────────────────────────────────────────────────────────

def test_token(url: str, token: str) -> bool:
    """Test whether the token is valid against HA API."""
    try:
        resp = requests.get(
            f"{url}/api/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        return resp.status_code == 200
    except Exception:
        return False


def list_entities(url: str, token: str) -> dict:
    """Return all HA entities grouped by domain."""
    try:
        resp = requests.get(
            f"{url}/api/states",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if resp.status_code != 200:
            return {}

        states = resp.json()
        domains: dict[str, list] = {}
        for s in states:
            domain = s["entity_id"].split(".")[0]
            name   = s.get("attributes", {}).get("friendly_name", s["entity_id"])
            state  = s.get("state", "unknown")
            domains.setdefault(domain, []).append((s["entity_id"], name, state))

        return domains
    except Exception as e:
        print(f"[Setup]: Could not fetch entities — {e}")
        return {}


# ─────────────────────────────────────────────────────────
# Config / .env writer
# ─────────────────────────────────────────────────────────

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def write_env(ha_url: str, ha_token: str) -> None:
    """Write or update HA credentials into .env file."""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()

    # Remove existing HA lines
    lines = [l for l in lines
             if not l.startswith("HA_URL=") and not l.startswith("HA_TOKEN=")]

    lines.append(f"HA_URL={ha_url}\n")
    lines.append(f"HA_TOKEN={ha_token}\n")

    with open(ENV_FILE, "w") as f:
        f.writelines(lines)


def patch_config_py(ha_url: str, ha_token: str) -> None:
    """
    Directly patch config.py so FRIDAY picks up credentials immediately
    without needing python-dotenv or env vars.
    """
    config_path = os.path.join(os.path.dirname(__file__), "config.py")
    with open(config_path, "r") as f:
        content = f.read()

    # Replace the env-var default for HA_URL
    content = content.replace(
        'os.getenv("HA_URL",    "")',
        f'os.getenv("HA_URL",    "{ha_url}")'
    )
    # Replace the env-var default for HA_TOKEN
    content = content.replace(
        'os.getenv("HA_TOKEN", "")',
        f'os.getenv("HA_TOKEN", "{ha_token}")'
    )

    with open(config_path, "w") as f:
        f.write(content)

    print("[Setup]: config.py updated with HA credentials.")


# ─────────────────────────────────────────────────────────
# Print helpers
# ─────────────────────────────────────────────────────────

def hr(char="─", n=55):
    print(char * n)

def header(text):
    hr()
    print(f"  {text}")
    hr()


# ─────────────────────────────────────────────────────────
# Main Setup Flow
# ─────────────────────────────────────────────────────────

def main():
    print()
    header("FRIDAY — Home Assistant Setup Wizard")

    # ── Step 1: Find HA on network ───────────────────────
    print("\nStep 1/4 — Discovering Home Assistant on your network")

    my_subnet = get_local_subnet()
    print(f"[Info]: Your machine is on subnet: {my_subnet}.x")

    # Also check localhost / common manual entries
    candidates = [f"http://localhost:8123", f"http://homeassistant.local:8123"]
    found_ips  = scan_for_ha(my_subnet)

    if found_ips:
        print(f"\n[Scan]: Found {len(found_ips)} device(s) on port 8123:")
        for ip in found_ips:
            print(f"          http://{ip}:8123")
        candidates = [f"http://{ip}:8123" for ip in found_ips] + candidates
    else:
        print("[Scan]: No devices found via port scan.")

    # Verify which ones are actually HA
    ha_instances = []
    for url in candidates:
        print(f"[Check]: Testing {url} ...", end=" ", flush=True)
        if verify_ha(url):
            print("HOME ASSISTANT FOUND")
            ha_instances.append(url)
        else:
            print("not HA")

    # ── Step 2: Choose HA instance ───────────────────────
    print("\nStep 2/4 — Select Home Assistant instance")

    if ha_instances:
        if len(ha_instances) == 1:
            ha_url = ha_instances[0]
            print(f"[Auto]: Using {ha_url}")
        else:
            print("Multiple HA instances found:")
            for i, url in enumerate(ha_instances):
                print(f"  [{i+1}] {url}")
            choice = input("\nEnter number (or press Enter for #1): ").strip()
            idx    = int(choice) - 1 if choice.isdigit() else 0
            ha_url = ha_instances[idx]
    else:
        print("[Warn]: Could not auto-detect Home Assistant.")
        ha_url = input("Enter your HA URL manually (e.g. http://192.168.1.100:8123): ").strip()
        if not ha_url:
            print("[Error]: No URL provided. Exiting.")
            return

    print(f"\n[OK]: Using Home Assistant at: {ha_url}")

    # ── Step 3: Get Long-Lived Access Token ──────────────
    print("\nStep 3/4 — Generate Long-Lived Access Token")
    hr("─", 55)
    print(f"""
  How to get your token:
  ─────────────────────
  1. Open:  {ha_url}/profile
  2. Scroll to the bottom -> "Long-Lived Access Tokens"
  3. Click "CREATE TOKEN"
  4. Name it:  FRIDAY
  5. Copy the token (it's only shown ONCE)
  6. Paste it below
""")
    hr("─", 55)

    token = input("  Paste your token here: ").strip()
    if not token:
        print("[Error]: No token provided. Exiting.")
        return

    # ── Step 4: Verify token ─────────────────────────────
    print("\nStep 4/4 — Verifying token...")

    if not test_token(ha_url, token):
        print("[Error]: Token rejected by Home Assistant. Check it and try again.")
        return

    print("[OK]: Token verified! Connection to Home Assistant successful.")

    # ── Save credentials ──────────────────────────────────
    write_env(ha_url, token)
    patch_config_py(ha_url, token)
    print(f"[OK]: Credentials saved to .env and config.py")

    # ── List entities ─────────────────────────────────────
    print("\n" + "━" * 55)
    print("  Your Home Assistant Devices")
    print("━" * 55)

    domains = list_entities(ha_url, token)

    SHOW_DOMAINS = ["light", "switch", "climate", "lock",
                    "cover", "fan", "media_player", "scene", "automation"]

    if domains:
        for domain in SHOW_DOMAINS:
            if domain not in domains:
                continue
            print(f"\n  [{domain.upper()}]")
            for entity_id, name, state in domains[domain][:20]:
                print(f"    {name:<30}  [{state}]  ({entity_id})")
    else:
        print("  (Could not fetch entities — check HA connection)")

    # ── Voice command cheatsheet ──────────────────────────
    print("\n" + "━" * 55)
    print("  FRIDAY Voice Commands for Smart Home")
    print("━" * 55)
    print("""
  LIGHTS
    "Lights on / off"
    "Dim lights"        -> 30% brightness
    "Bright lights"     -> 100% brightness

  CLIMATE
    "Set temperature to 22"
    "AC on / off"
    "Fan on / off"

  SECURITY
    "Lock the door"
    "Unlock the door"

  SCENES
    "Movie mode"        -> activates scene.movie_mode
    "Night mode"        -> activates scene.night_mode
    "Morning mode"      -> activates scene.morning_mode

  DASHBOARD
    "Open dashboard"    -> opens the FRIDAY status window

  TIP: Edit ENTITY_MAP in commands.py to map your exact entity IDs.
""")

    print("━" * 55)
    print("  Setup complete! Run: python main.py")
    print("━" * 55)


if __name__ == "__main__":
    main()
