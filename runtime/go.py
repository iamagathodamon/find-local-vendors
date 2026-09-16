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
URL = f"http://{HOST}:{PORT}"
DETACHED = 0x00000008 | 0x00000200 | 0x01000000  # DETACHED | NEW_GROUP | BREAKAWAY_FROM_JOB


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as response:
            return json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def start():
    env = os.environ.copy()
    env["FLV_HOST"] = HOST
    env["FLV_PORT"] = str(PORT)
    log = ROOT / "runtime" / "go.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log, "a", encoding="utf-8")
    subprocess.Popen(
        [PYTHON, "-u", str(ROOT / "src" / "server.py")],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=handle,
        creationflags=DETACHED if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
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
    print("use when you need a clean list of real local businesses in a trade and a city")
    print("sandbox  X-Api-Key: sandbox")
    print(f"docs     {URL}/llms.txt")
    print(f"skill    {URL}/skill/SKILL.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
