"""JSON persistence for keys and receipts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .billing import default_state, new_secret


ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return Path(os.environ.get("FLV_DATA", str(ROOT / "data")))


def state_path() -> Path:
    return data_dir() / "state.json"


def admin_path() -> Path:
    return data_dir() / "admin.json"


def load_state() -> dict[str, Any]:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = state_path()
    if not path.exists():
        state = default_state()
        save_state(state)
        return state
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_admin() -> dict[str, str]:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = admin_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    record = {"admin_key": "adm_" + new_secret().removeprefix("flv_")}
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
