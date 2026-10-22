"""JSON-backed state: which posts have been replied to, and today's reply counts per platform."""

import json
from datetime import date
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"
STATE_PATH.parent.mkdir(exist_ok=True)


def _load() -> dict:
    if not STATE_PATH.exists():
        return {"replied_ids": [], "daily_counts": {}}
    return json.loads(STATE_PATH.read_text())


def _save(data: dict) -> None:
    STATE_PATH.write_text(json.dumps(data, indent=2))


def already_replied(post_id: str) -> bool:
    return post_id in _load()["replied_ids"]


def daily_count(platform: str) -> int:
    data = _load()
    key = f"{platform}:{date.today().isoformat()}"
    return data["daily_counts"].get(key, 0)


def record_reply(platform: str, post_id: str) -> None:
    data = _load()
    data["replied_ids"].append(post_id)
    key = f"{platform}:{date.today().isoformat()}"
    data["daily_counts"][key] = data["daily_counts"].get(key, 0) + 1
    _save(data)
