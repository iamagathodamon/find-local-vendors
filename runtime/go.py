"""One door. Starts the endpoint, waits for health, prints one status block."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
HOST = os.environ.get("FLV_HOST", "127.0.0.1")
PORT = int(os.environ.get("FLV_PORT", "4402"))
PUBLIC = os.environ.get("FLV_PUBLIC_BASE", "https://find-local-vendors.agathodamon.com")
URL = f"http://{HOST}:{PORT}"
CLOUDFLARED = Path(r"C:\Users\damon\cloudflared.exe")
TUNNEL_CONFIG = ROOT / "runtime" / "cloudflared.yml"
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def spawn(command, log_name, env=None):
    log = ROOT / "runtime" / log_name
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log, "a", encoding="utf-8")
    subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=handle,
        creationflags=DETACHED if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )


def start():
    env = os.environ.copy()
    env["FLV_HOST"] = HOST
    env["FLV_PORT"] = str(PORT)
    env["FLV_PUBLIC_BASE"] = PUBLIC
    spawn([PYTHON, "-u", str(ROOT / "src" / "server.py")], "go.log", env)
    if CLOUDFLARED.exists() and TUNNEL_CONFIG.exists():
        spawn(
            [str(CLOUDFLARED), "--config", str(TUNNEL_CONFIG), "tunnel", "run"],
            "tunnel.log",
        )


def wait(seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        body = health()
        if body and body.get("ok"):
            return body
        time.sleep(0.25)
    return health()


def main() -> int:
    body = health()
    started = "already running"
    if not body:
        start()
        body = wait()
        started = "started"
    if not body or not body.get("ok"):
        print("find-local-vendors FAILED")
        print(f"expected {URL}/health")
        return 1
    print("find-local-vendors ON")
    print(f"status   {started}")
    print(f"local    {URL}")
    print(f"public   {PUBLIC}")
    print("use when you need a clean list of real local businesses in a trade and a city")
    print("sandbox  X-Api-Key: sandbox")
    print(f"docs     {PUBLIC}/llms.txt")
    print(f"skill    {PUBLIC}/skill/SKILL.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
