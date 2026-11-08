"""Builds the encrypted status dashboard and publishes it to GitHub Pages.

    python -m src.dashboard           # build and push to the dashboard repo
    python -m src.dashboard --local   # build into data/dashboard_site only, no push

The snapshot (posts, schedule, errors, counts — never keys or .env contents) is encrypted with
DASHBOARD_PASSWORD before it leaves this machine: AES-256-GCM with a key derived by
PBKDF2-SHA256. The public repo and site only ever hold ciphertext; dashboard/index.html asks for
the password and decrypts in the browser. Run every 15 minutes by deploy/hc-bot-dashboard.timer.
"""

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

from src import usage

ROOT = Path(__file__).resolve().parent.parent
POST_LOG = ROOT / "logs" / "x_posts.jsonl"
CONFIG_PATH = ROOT / "config" / "config.yaml"
PAGE = ROOT / "dashboard" / "index.html"
SITE_DIR = ROOT / "data" / "dashboard_site"  # local clone of the dashboard repo (gitignored)
REPO_URL = "https://github.com/hellomarcog/hc-bot-dashboard.git"
SERVICE = "hc-bot-x"
ITERATIONS = 600_000  # PBKDF2 rounds; the page reads this from data.json
HISTORY_DAYS = 30
X_HANDLE = "SuburbanDscipln"


def _log_entries() -> list[dict]:
    if not POST_LOG.exists():
        return []
    entries = []
    for line in POST_LOG.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not entry.get("dry_run"):
            entries.append(entry)
    return entries


def _service() -> dict:
    """systemd's view of the bot: running?, since when, and crashes in the last week."""
    out = subprocess.run(
        ["systemctl", "--user", "show", SERVICE, "-p", "ActiveState", "-p", "ActiveEnterTimestamp"],
        capture_output=True, text=True,
    ).stdout
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    journal = subprocess.run(
        ["journalctl", "--user", "-u", SERVICE, "--since", "7 days ago", "--no-pager", "-o", "cat"],
        capture_output=True, text=True,
    ).stdout
    return {
        "state": props.get("ActiveState", "unknown"),
        "since": props.get("ActiveEnterTimestamp", ""),
        "crashes_7d": journal.count("Main process exited"),
    }


def _network_ok() -> bool:
    try:
        socket.getaddrinfo("api.x.com", 443)
        return True
    except OSError:
        return False


def _plan_for(entries: list[dict], day: date) -> list[dict]:
    """The latest plan the bot logged for `day`, as [{time, topic}]. Older log lines stored plain
    time strings; newer ones store [time, topic] pairs."""
    plans = [e for e in entries if "plan" in e and e["time"].startswith(day.isoformat())]
    if not plans:
        return []
    slots = []
    for slot in plans[-1]["plan"]:
        when, topic = (slot, None) if isinstance(slot, str) else slot
        slots.append({"time": when, "topic": topic})
    return slots


def _costs(posted: list[dict], today: date) -> dict:
    """Estimated spend from logs/usage.jsonl (today, this month by service, per post)."""
    calls = usage.entries()
    month = today.strftime("%Y-%m")
    by_service = Counter()
    for c in calls:
        if c["time"].startswith(month):
            by_service[c["service"]] += c.get("cost", 0)
    # Only posts made since tracking began, or the average is diluted by untracked older posts.
    tracked_from = calls[0]["time"] if calls else "9999"
    month_posts = sum(1 for e in posted if e["time"].startswith(month) and e["time"] >= tracked_from)
    month_total = sum(by_service.values())
    return {
        "since": calls[0]["time"][:10] if calls else None,
        "today": round(sum(c.get("cost", 0) for c in calls if c["time"].startswith(today.isoformat())), 4),
        "month": round(month_total, 4),
        "month_by_service": {k: round(v, 4) for k, v in by_service.most_common()},
        # per post counts every call that month, including generations that were dropped
        "per_post": round(month_total / month_posts, 4) if month_posts else None,
    }


def build_snapshot() -> dict:
    config = yaml.safe_load(CONFIG_PATH.read_text())
    posts_cfg = config["platforms"]["x"]["posts"]
    entries = _log_entries()
    today = date.today()
    posted = [e for e in entries if e.get("posted")]
    problems = [e for e in entries if e.get("posted") is False and ("failed" in e or "skipped" in e)]

    per_day = Counter(e["time"][:10] for e in posted)
    days = [(today - timedelta(days=i)).isoformat() for i in range(HISTORY_DAYS - 1, -1, -1)]
    since = days[0]
    topics = Counter(
        "photo" if e.get("image") else e.get("topic", "?") for e in posted if e["time"][:10] >= since
    )
    month = today.strftime("%Y-%m")
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "handle": X_HANDLE,
        "service": _service(),
        "network_ok": _network_ok(),
        "today": {
            "date": today.isoformat(),
            "plan": _plan_for(entries, today),
            "posted": per_day.get(today.isoformat(), 0),
            "cap": posts_cfg["daily_post_cap"],
        },
        "posts": [
            {
                "time": e["time"],
                "topic": e.get("topic"),
                "text": e.get("text"),
                "id": e.get("id"),
                "photo": bool(e.get("image")),
            }
            for e in reversed(posted[-30:])
        ],
        "problems": [
            {"time": e["time"], "kind": "failed" if "failed" in e else "skipped",
             "reason": (e.get("failed") or e.get("skipped") or "")[:300]}
            for e in reversed(problems[-20:])
        ],
        "costs": _costs(posted, today),
        "history": [{"date": d, "posts": per_day.get(d, 0)} for d in days],
        "topics": topics.most_common(),
        "month": {
            "label": today.strftime("%B %Y"),
            "posts": sum(1 for e in posted if e["time"].startswith(month)),
            "photos": sum(1 for e in posted if e["time"].startswith(month) and e.get("image")),
            "problems": sum(1 for e in problems if e["time"].startswith(month)),
        },
    }


def encrypt(snapshot: dict, password: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(
        password.encode()
    )
    # AESGCM output is ciphertext + 16-byte tag, the same layout WebCrypto's decrypt expects.
    ciphertext = AESGCM(key).encrypt(iv, json.dumps(snapshot).encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iterations": ITERATIONS,
            "salt": b64(salt), "iv": b64(iv), "data": b64(ciphertext)}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(SITE_DIR), *args], capture_output=True, text=True)


def publish() -> None:
    """Replaces the dashboard repo's single commit with the new files (amend + force-push), so the
    repo never accumulates a history of snapshots."""
    if not (SITE_DIR / ".git").exists():
        # init rather than clone: every push replaces the remote's contents anyway.
        _git("init", "-q", "-b", "main")
        _git("remote", "add", "origin", REPO_URL)
        # Same commit identity as the HC_Bot repo (it's set there locally, not globally).
        for field in ("user.name", "user.email"):
            value = subprocess.run(["git", "-C", str(ROOT), "config", field], capture_output=True, text=True)
            if value.stdout.strip():
                _git("config", field, value.stdout.strip())
    _git("add", "-A")
    has_commit = _git("rev-parse", "--verify", "HEAD").returncode == 0
    message = f"Dashboard update {datetime.now():%Y-%m-%d %H:%M}"
    commit = ["commit", "-q", "-m", message] + (["--amend"] if has_commit else [])
    r = _git(*commit)
    if r.returncode:
        sys.exit(f"commit failed: {(r.stderr or r.stdout).strip()}")
    r = _git("push", "-q", "--force", "origin", "HEAD:main")
    if r.returncode:
        sys.exit(f"push failed: {r.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="build only, don't push")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if len(password) < 12:
        sys.exit("Set DASHBOARD_PASSWORD in .env (12+ characters; a long passphrase is best).")
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(PAGE, SITE_DIR / "index.html")
    (SITE_DIR / ".nojekyll").touch()  # serve files as-is
    (SITE_DIR / "data.json").write_text(json.dumps(encrypt(build_snapshot(), password)))
    if args.local:
        print(f"built {SITE_DIR}")
        return
    publish()
    print(f"published {datetime.now():%H:%M}")


if __name__ == "__main__":
    main()
