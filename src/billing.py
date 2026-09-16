"""API keys, daily caps, and one-line receipts."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any


SANDBOX_KEY = "sandbox"
SANDBOX_DAILY_CALLS = 3
DEFAULT_PRICE_CENTS = 50
DEFAULT_DAILY_CAP_CENTS = 2500


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def day_key(when: datetime | None = None) -> str:
    return (when or utc_now()).strftime("%Y-%m-%d")


def new_secret() -> str:
    return "flv_" + secrets.token_urlsafe(24)


def default_state() -> dict[str, Any]:
    return {
        "keys": {
            SANDBOX_KEY: {
                "id": SANDBOX_KEY,
                "secret": SANDBOX_KEY,
                "label": "public sandbox",
                "sandbox": True,
                "price_cents": 0,
                "daily_cap_cents": 0,
                "daily_call_cap": SANDBOX_DAILY_CALLS,
                "created": utc_now().isoformat(),
            }
        },
        "receipts": [],
        "spend": {},
    }


def get_key(state: dict[str, Any], secret: str | None) -> dict[str, Any] | None:
    if not secret:
        return None
    for key in state["keys"].values():
        if key.get("secret") == secret:
            return key
    return None


def issue_key(
    state: dict[str, Any],
    *,
    label: str,
    price_cents: int = DEFAULT_PRICE_CENTS,
    daily_cap_cents: int = DEFAULT_DAILY_CAP_CENTS,
) -> dict[str, Any]:
    key_id = "key_" + secrets.token_hex(4)
    record = {
        "id": key_id,
        "secret": new_secret(),
        "label": label,
        "sandbox": False,
        "price_cents": int(price_cents),
        "daily_cap_cents": int(daily_cap_cents),
        "daily_call_cap": None,
        "created": utc_now().isoformat(),
    }
    state["keys"][key_id] = record
    return record


def _spend_bucket(state: dict[str, Any], key_id: str, day: str) -> dict[str, int]:
    by_day = state["spend"].setdefault(day, {})
    bucket = by_day.setdefault(key_id, {"cents": 0, "calls": 0})
    return bucket


def cap_error(key: dict[str, Any], bucket: dict[str, int]) -> dict[str, Any] | None:
    if key.get("sandbox"):
        cap = int(key.get("daily_call_cap") or SANDBOX_DAILY_CALLS)
        if bucket["calls"] >= cap:
            return {
                "error": "cap_reached",
                "message": f"sandbox daily cap is {cap} calls. Ask the owner to issue a paid key.",
                "cap": cap,
                "used": bucket["calls"],
                "raise_with": "the business that holds this endpoint",
            }
        return None
    cap_cents = int(key.get("daily_cap_cents") or 0)
    if cap_cents and bucket["cents"] + int(key.get("price_cents") or 0) > cap_cents:
        return {
            "error": "cap_reached",
            "message": (
                f"daily cap is ${cap_cents / 100:.2f}. "
                "The business that issued this key can raise it."
            ),
            "cap_cents": cap_cents,
            "used_cents": bucket["cents"],
            "raise_with": key.get("label") or key.get("id"),
        }
    return None


def record_call(
    state: dict[str, Any],
    key: dict[str, Any],
    *,
    trade: str,
    city: str,
    result_count: int,
    ok: bool,
    error: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    day = day_key(now)
    bucket = _spend_bucket(state, key["id"], day)
    cost = 0 if key.get("sandbox") or not ok else int(key.get("price_cents") or 0)
    bucket["calls"] += 1
    bucket["cents"] += cost
    receipt = {
        "id": "rcpt_" + secrets.token_hex(6),
        "time": now.isoformat(),
        "key_id": key["id"],
        "trade": trade,
        "city": city,
        "result_count": result_count,
        "cost_cents": cost,
        "ok": ok,
        "error": error,
    }
    state["receipts"].insert(0, receipt)
    state["receipts"] = state["receipts"][:5000]
    return receipt


def receipts_for(state: dict[str, Any], key_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return [row for row in state["receipts"] if row["key_id"] == key_id][:limit]
