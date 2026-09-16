import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
PORT = 4412


def http_json(method, path, payload=None, headers=None, port=PORT):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return err.code, parsed


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["FLV_PORT"] = str(PORT)
        env["FLV_HOST"] = "127.0.0.1"
        env["FLV_DATA"] = cls.tmp.name
        cls.proc = subprocess.Popen(
            [PYTHON, str(ROOT / "src" / "server.py")],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 8
        last = None
        while time.time() < deadline:
            try:
                code, body = http_json("GET", "/health")
                if code == 200 and body.get("ok"):
                    return
            except Exception as err:  # noqa: BLE001
                last = err
                time.sleep(0.2)
        raise RuntimeError(f"server did not start: {last}")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.tmp.cleanup()

    def test_health(self):
        code, body = http_json("GET", "/health")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])

    def test_missing_key(self):
        code, body = http_json("POST", "/v1/find", {"trade": "HVAC", "city": "Dallas, TX"})
        self.assertEqual(code, 401)
        self.assertEqual(body["error"], "missing_key")

    def test_sandbox_requires_trade_and_city(self):
        code, body = http_json(
            "POST", "/v1/find", {"trade": "", "city": ""}, headers={"X-Api-Key": "sandbox"}
        )
        self.assertEqual(code, 400)

    def test_trial_key_and_receipts(self):
        code, body = http_json("POST", "/v1/keys/trial", {})
        self.assertEqual(code, 201)
        key = body["key"]
        self.assertTrue(key.startswith("flv_"))
        code, receipts = http_json("GET", "/v1/receipts", headers={"X-Api-Key": key})
        self.assertEqual(code, 200)
        self.assertEqual(receipts["receipts"], [])

    def test_skill_and_llms(self):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/skill/SKILL.md")
        with urllib.request.urlopen(req, timeout=5) as response:
            text = response.read().decode()
        self.assertIn("Use when you need a clean list", text)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/llms.txt")
        with urllib.request.urlopen(req, timeout=5) as response:
            self.assertIn("POST /v1/find", response.read().decode())


if __name__ == "__main__":
    unittest.main()
