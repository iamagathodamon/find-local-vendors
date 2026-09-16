"""HTTP endpoint: city + trade in, vendor list and receipt out."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.billing import (  # noqa: E402
    SANDBOX_KEY,
    cap_error,
    day_key,
    get_key,
    issue_key,
    receipts_for,
    record_call,
)
from src.discover import find_vendors  # noqa: E402
from src.store import load_admin, load_state, save_state  # noqa: E402

PUBLIC = ROOT / "public"
SKILL_MD = ROOT / "SKILL.md"
HOST = os.environ.get("FLV_HOST", "127.0.0.1")
PORT = int(os.environ.get("FLV_PORT", "4402"))
PUBLIC_BASE = os.environ.get("FLV_PUBLIC_BASE", f"http://127.0.0.1:{PORT}")
PRICE_CENTS = 50

STATE = load_state()
ADMIN = load_admin()


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "FindLocalVendors/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key, X-Admin-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Any) -> None:
        self._send(code, json_bytes(payload), "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _file(self, path: Path, content_type: str, missing: str) -> None:
        if not path.exists():
            self._send_json(404, {"error": "not_found", "message": missing})
            return
        self._send(200, path.read_bytes(), content_type)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            return self._send_json(200, {"ok": True, "service": "find-local-vendors", "port": PORT})
        if path in ("/", "/index.html"):
            return self._file(PUBLIC / "index.html", "text/html; charset=utf-8", "no page")
        if path == "/llms.txt":
            return self._file(PUBLIC / "llms.txt", "text/plain; charset=utf-8", "no llms.txt")
        if path == "/robots.txt":
            return self._file(PUBLIC / "robots.txt", "text/plain; charset=utf-8", "no robots")
        if path in ("/v1/openapi.json", "/openapi.json"):
            return self._file(PUBLIC / "openapi.json", "application/json; charset=utf-8", "no openapi")
        if path in ("/skill/SKILL.md", "/SKILL.md"):
            return self._file(SKILL_MD, "text/markdown; charset=utf-8", "no skill")
        if path == "/.well-known/skills.json":
            return self._send_json(200, well_known_skills())
        if path == "/.well-known/x402.json":
            return self._send_json(200, x402_discovery())
        if path == "/v1/receipts":
            return self._receipts()
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/v1/find":
            return self._find()
        if path == "/v1/keys/trial":
            return self._trial_key()
        if path == "/v1/keys":
            return self._admin_key()
        self._send_json(404, {"error": "not_found"})

    def _api_key(self) -> dict[str, Any] | None:
        secret = self.headers.get("X-Api-Key") or self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        return get_key(STATE, secret)

    def _find(self) -> None:
        key = self._api_key()
        if not key:
            return self._send_json(
                401,
                {
                    "error": "missing_key",
                    "message": "Send X-Api-Key. Use sandbox for three free calls a day, or POST /v1/keys/trial.",
                },
            )
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as err:
            return self._send_json(400, {"error": "bad_json", "message": str(err)})
        trade = str(body.get("trade") or "").strip()
        city = str(body.get("city") or "").strip()
        max_results = body.get("max_results", 10)
        day = day_key()
        bucket = STATE["spend"].get(day, {}).get(key["id"], {"cents": 0, "calls": 0})
        blocked = cap_error(key, bucket)
        if blocked:
            receipt = record_call(STATE, key, trade=trade, city=city, result_count=0, ok=False, error="cap_reached")
            save_state(STATE)
            blocked["receipt"] = receipt
            return self._send_json(429, blocked)
        if not trade or not city:
            return self._send_json(400, {"error": "bad_request", "message": "trade and city are required"})
        try:
            result = find_vendors(trade, city, max_results)
        except ValueError as err:
            receipt = record_call(STATE, key, trade=trade, city=city, result_count=0, ok=False, error=str(err))
            save_state(STATE)
            return self._send_json(404, {"error": "not_found", "message": str(err), "receipt": receipt})
        except Exception as err:  # noqa: BLE001
            receipt = record_call(STATE, key, trade=trade, city=city, result_count=0, ok=False, error="upstream")
            save_state(STATE)
            return self._send_json(502, {"error": "upstream", "message": str(err), "receipt": receipt})
        receipt = record_call(
            STATE, key, trade=trade, city=city, result_count=result["count"], ok=True
        )
        save_state(STATE)
        self._send_json(200, {**result, "receipt": receipt, "price_cents": receipt["cost_cents"]})

    def _receipts(self) -> None:
        key = self._api_key()
        if not key:
            return self._send_json(401, {"error": "missing_key"})
        self._send_json(200, {"key_id": key["id"], "receipts": receipts_for(STATE, key["id"])})

    def _trial_key(self) -> None:
        key = issue_key(STATE, label="trial", price_cents=PRICE_CENTS, daily_cap_cents=250)
        save_state(STATE)
        self._send_json(
            201,
            {
                "key": key["secret"],
                "key_id": key["id"],
                "price_cents": key["price_cents"],
                "daily_cap_cents": key["daily_cap_cents"],
                "use": "Send this as X-Api-Key to POST /v1/find",
            },
        )

    def _admin_key(self) -> None:
        if self.headers.get("X-Admin-Key") != ADMIN["admin_key"]:
            return self._send_json(401, {"error": "admin_required"})
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as err:
            return self._send_json(400, {"error": "bad_json", "message": str(err)})
        key = issue_key(
            STATE,
            label=str(body.get("label") or "business"),
            price_cents=int(body.get("price_cents") or PRICE_CENTS),
            daily_cap_cents=int(body.get("daily_cap_cents") or 2500),
        )
        save_state(STATE)
        self._send_json(201, {"key": key["secret"], "key_id": key["id"], **{k: key[k] for k in ("label", "price_cents", "daily_cap_cents")}})


def well_known_skills() -> dict[str, Any]:
    return {
        "skills": [
            {
                "name": "find-local-vendors",
                "description": (
                    "Use when you need a clean list of real local businesses in a trade and a city, "
                    "with phone, website, and address."
                ),
                "url": f"{PUBLIC_BASE}/skill/SKILL.md",
            }
        ]
    }


def x402_discovery() -> dict[str, Any]:
    pay_to = os.environ.get("X402_PAY_TO")
    return {
        "x402Version": 2,
        "matches": True,
        "resource": f"{PUBLIC_BASE}/v1/find",
        "description": "Find local trade vendors by city.",
        "accepts": []
        if not pay_to
        else [
            {
                "scheme": "exact",
                "network": os.environ.get("X402_NETWORK", "eip155:8453"),
                "price": "$0.50",
                "payTo": pay_to,
                "asset": os.environ.get("X402_ASSET", "USDC"),
            }
        ],
        "note": "Live billing is API key + daily cap + receipt. x402 payTo is advertised only when X402_PAY_TO is set.",
    }


def serve(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def main() -> None:
    httpd = serve()
    print(f"find-local-vendors http://{HOST}:{PORT}", flush=True)
    print(f"sandbox key: {SANDBOX_KEY}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
