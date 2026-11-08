"""Commands from the Telegram remote (src/telegram_bot.py) to the X posting loop (main_x.py).

The two run as separate processes and share data/control.json; every read-modify-write holds an
exclusive file lock so they can't clobber each other. Nothing here can raise the daily post cap —
post_once still checks it for every post, including "post now" requests.
"""

import contextlib
import fcntl
import json
from datetime import datetime, timedelta
from pathlib import Path

CONTROL_PATH = Path(__file__).resolve().parent.parent / "data" / "control.json"
LOCK_PATH = CONTROL_PATH.with_suffix(".lock")
POST_NOW_MAX_AGE = timedelta(minutes=30)  # don't act on a stale request (e.g. desktop was asleep)


def _empty() -> dict:
    return {"paused": False, "skip_next": 0, "hint": None, "post_now": [], "slots": []}


@contextlib.contextmanager
def _edit():
    """Locked read-modify-write of the control file."""
    CONTROL_PATH.parent.mkdir(exist_ok=True)
    with open(LOCK_PATH, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _empty()
        if CONTROL_PATH.exists():
            data.update(json.loads(CONTROL_PATH.read_text()))
        yield data
        CONTROL_PATH.write_text(json.dumps(data, indent=2))


def read() -> dict:
    with _edit() as data:
        return json.loads(json.dumps(data))


# --- written by the Telegram remote ---

def set_paused(paused: bool) -> None:
    with _edit() as data:
        data["paused"] = paused


def add_skip() -> int:
    with _edit() as data:
        data["skip_next"] += 1
        return data["skip_next"]


def set_hint(text: str | None, posts: int = 1) -> None:
    """Guidance for the next `posts` posts (None clears it)."""
    with _edit() as data:
        data["hint"] = {"text": text, "remaining": posts} if text else None


def request_post(topic: str | None) -> None:
    """topic: a topic name, "photo", "photo: <scene>", or None for the usual random pick."""
    with _edit() as data:
        data["post_now"].append({"topic": topic, "requested": datetime.now().isoformat(timespec="seconds")})


def add_slot(day: str, hhmm: str, topic: str | None) -> None:
    with _edit() as data:
        data["slots"].append({"date": day, "time": hhmm, "topic": topic})


# --- read by the posting loop ---

def take_post_requests() -> tuple[list[dict], list[dict]]:
    """Removes and returns (fresh requests, expired requests)."""
    with _edit() as data:
        requests, data["post_now"] = data["post_now"], []
    cutoff = datetime.now() - POST_NOW_MAX_AGE
    fresh = [r for r in requests if datetime.fromisoformat(r["requested"]) >= cutoff]
    return fresh, [r for r in requests if r not in fresh]


def take_slots(day: str) -> list[dict]:
    """Removes and returns slots added for `day`; drops slots for days already past."""
    with _edit() as data:
        mine = [s for s in data["slots"] if s["date"] == day]
        data["slots"] = [s for s in data["slots"] if s["date"] > day]
    return mine


def take_skip() -> bool:
    with _edit() as data:
        if data["skip_next"] > 0:
            data["skip_next"] -= 1
            return True
        return False


def hint() -> str | None:
    h = read()["hint"]
    return h["text"] if h else None


def used_hint() -> None:
    """Called after a post that used the hint actually went out."""
    with _edit() as data:
        if data["hint"]:
            data["hint"]["remaining"] -= 1
            if data["hint"]["remaining"] <= 0:
                data["hint"] = None
