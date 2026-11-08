"""Private Telegram remote for the X bot: status info, commands, and alerts.

    python -m src.telegram_bot            # run (as the hc-bot-telegram service)
    python -m src.telegram_bot --whoami   # print the chat id of the next message sent to the bot

Answers only TELEGRAM_CHAT_ID (from .env); messages from anyone else are ignored without a reply.
Commands reach the posting loop through src/control.py, so they can't get around the daily cap,
blocked words, or any other check in main_x.py. Alerts come from tailing logs/x_posts.jsonl and
watching the hc-bot-x service. Uses the Telegram Bot API directly over HTTPS (free, no server).
"""

import argparse
import html
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml
from dotenv import load_dotenv

from src import control, dashboard, decide

ROOT = Path(__file__).resolve().parent.parent
POST_LOG = ROOT / "logs" / "x_posts.jsonl"
CONFIG_PATH = ROOT / "config" / "config.yaml"
STATE_PATH = ROOT / "data" / "telegram_state.json"  # how far into the post log alerts have got
POLL_TIMEOUT = 25  # long-poll seconds; alerts are checked between polls
MAX_HINT = 300

load_dotenv(ROOT / ".env")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"

COMMANDS = [
    ("status", "Is the bot running? Today at a glance"),
    ("today", "Today's schedule and posts"),
    ("posts", "Last 3 posts"),
    ("problems", "Recent failures and skips"),
    ("stats", "This month and the last 7 days"),
    ("post", "Post now: /post, /post photo [scene], /post <topic>"),
    ("next", "Guide the next post: /next <idea> (or /next 3 <idea>)"),
    ("clearnext", "Drop the /next guidance"),
    ("add", "Add a post today: /add 21:30 [topic | photo]"),
    ("skip", "Skip the next scheduled post"),
    ("pause", "Pause scheduled posts"),
    ("resume", "Resume scheduled posts"),
    ("topics", "Topic and photo scene names"),
    ("help", "All commands"),
]


# --- Telegram API ---

def _call(method: str, **params):
    r = requests.post(f"{API}/{method}", timeout=POLL_TIMEOUT + 10, **params)
    r.raise_for_status()
    return r.json()["result"]


def send(chat_id: int, text: str) -> None:
    _call("sendMessage", data={"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML",
                               "disable_web_page_preview": "true"})


def send_photo(chat_id: int, path: str, caption: str) -> None:
    with open(path, "rb") as f:
        _call("sendPhoto", data={"chat_id": chat_id, "caption": caption[:1000], "parse_mode": "HTML"},
              files={"photo": f})


# --- formatting helpers ---

def _esc(text: str) -> str:
    return html.escape(text, quote=False)  # Telegram HTML only needs <, >, &


def _config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _t(iso: str) -> str:
    """'2026-11-07T22:27-05:00' or a naive log time -> '10:27 PM'."""
    return datetime.fromisoformat(iso).strftime("%-I:%M %p")


def _when(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return d.strftime("%-I:%M %p") if d.date() == date.today() else d.strftime("%b %-d, %-I:%M %p")


def _ago(iso: str) -> str:
    mins = int((datetime.now() - datetime.fromisoformat(iso).replace(tzinfo=None)).total_seconds() // 60)
    if mins < 60:
        return f"{mins} min ago"
    if mins < 48 * 60:
        return f"{mins // 60} h ago"
    return f"{mins // 1440} days ago"


def _link(handle: str, post_id: str | None) -> str:
    return f'<a href="https://x.com/{handle}/status/{post_id}">view on X</a>' if post_id else ""


def _plain(reason: str) -> str:
    """Short plain-words version of a failure/skip reason."""
    r = reason.lower()
    for needle, words in [
        ("name resolution", "network down"), ("connection", "network down"), ("402", "X API out of credits"),
        ("credits", "X API out of credits"), ("429", "X rate limit"), ("image failed", "image generation failed"),
        ("blocked word", "blocked word in generated text"), ("too similar", "too similar to a recent post"),
        ("missed", "missed slot (computer asleep/off)"), ("paused", "posting paused"),
        ("skipped by request", "skipped by your /skip"), ("cap reached", "daily cap reached"),
        ("expired", "post-now request expired"),
    ]:
        if needle in r:
            return words
    return reason[:120]


def _control_line() -> str:
    c = control.read()
    bits = ["⏸ <b>paused</b>" if c["paused"] else "▶️ posting on"]
    if c["skip_next"]:
        bits.append(f"skipping next {c['skip_next']}")
    if c["hint"]:
        bits.append(f"/next: “{_esc(c['hint']['text'])}” ({c['hint']['remaining']} post(s))")
    if c["post_now"]:
        bits.append(f"{len(c['post_now'])} post-now queued")
    return " · ".join(bits)


# --- info commands ---

def cmd_status(chat_id: int, _args: str) -> None:
    s = dashboard.build_snapshot()
    svc = s["service"]
    icon = "🟢" if svc["state"] == "active" else "🔴"
    net = "network OK" if s["network_ok"] else "⚠️ network down"
    next_slot = next((p for p in s["today"]["plan"] if datetime.fromisoformat(p["time"]) > datetime.now().astimezone()), None)
    last = s["posts"][0] if s["posts"] else None
    lines = [
        f"{icon} <b>{_esc(svc['state'])}</b> since {_esc(svc['since'])} · {net}",
        f"Crashes (7 days): {svc['crashes_7d']}",
        _control_line(),
        f"Today: {s['today']['posted']}/{s['today']['cap']} posts · next: "
        + (f"{_t(next_slot['time'])}" + (f" ({_esc(next_slot['topic'])})" if next_slot["topic"] else "") if next_slot else "none"),
        f"Last post: {_ago(last['time'])} ({_esc(last['topic'] or '')})" if last else "Last post: none yet",
        f"Est. cost today: {_money(s['costs']['today'])} · month: {_money(s['costs']['month'])}",
    ]
    send(chat_id, "\n".join(lines))


def cmd_today(chat_id: int, _args: str) -> None:
    s = dashboard.build_snapshot()
    today = date.today().isoformat()
    plan = s["today"]["plan"]
    lines = [f"<b>Today</b> — {s['today']['posted']}/{s['today']['cap']} posts"]
    lines.append("Plan: " + (", ".join(_t(p["time"]) + (f" ({_esc(p['topic'])})" if p["topic"] else "") for p in plan) or "none"))
    for p in s["posts"]:
        if p["time"].startswith(today):
            lines.append(f"✅ {_t(p['time'])} {_esc(p['topic'] or '')} — {_link(s['handle'], p['id'])}")
    for p in s["problems"]:
        if p["time"].startswith(today):
            lines.append(f"⚠️ {_t(p['time'])} {_esc(_plain(p['reason']))}")
    lines.append(_control_line())
    send(chat_id, "\n".join(lines))


def cmd_posts(chat_id: int, _args: str) -> None:
    s = dashboard.build_snapshot()
    entries = {e.get("id"): e for e in dashboard._log_entries() if e.get("posted")}
    if not s["posts"]:
        send(chat_id, "No posts yet.")
        return
    for p in reversed(s["posts"][:3]):
        caption = f"<b>{_when(p['time'])}</b> · {_esc(p['topic'] or '')}\n{_esc(p['text'] or '')}\n{_link(s['handle'], p['id'])}"
        image = entries.get(p["id"], {}).get("image")
        if image and (ROOT / image).exists():
            send_photo(chat_id, str(ROOT / image), caption)
        else:
            send(chat_id, caption)


def cmd_problems(chat_id: int, _args: str) -> None:
    s = dashboard.build_snapshot()
    if not s["problems"]:
        send(chat_id, "No problems logged. 👍")
        return
    lines = ["<b>Recent problems</b>"]
    for p in s["problems"][:6]:
        lines.append(f"• {_when(p['time'])} — {_esc(_plain(p['reason']))}")
    lines.append(f"Crashes (7 days): {s['service']['crashes_7d']}")
    send(chat_id, "\n".join(lines))


SERVICE_NAMES = {"claude": "Claude", "openai_image": "OpenAI images", "x": "X API"}


def _money(v: float) -> str:
    return f"${v:.3f}" if v < 1 else f"${v:.2f}"


def _cost_lines(c: dict) -> list[str]:
    by = " · ".join(f"{SERVICE_NAMES.get(k, k)} {_money(v)}" for k, v in c["month_by_service"].items())
    per = f" · {_money(c['per_post'])}/post" if c["per_post"] is not None else ""
    return [f"<b>Est. cost</b>: {_money(c['month'])} this month · {_money(c['today'])} today{per}",
            by or "No paid calls this month yet."]


def cmd_stats(chat_id: int, _args: str) -> None:
    s = dashboard.build_snapshot()
    m = s["month"]
    lines = [f"<b>{m['label']}</b>: {m['posts']} posts ({m['photos']} photo) · {m['problems']} failed/skipped",
             *_cost_lines(s["costs"]), "", "<b>Last 7 days</b>"]
    for h in s["history"][-7:]:
        day = datetime.fromisoformat(h["date"]).strftime("%a %-d")
        lines.append(f"<code>{day:<7}</code> {'▇' * h['posts'] or '·'} {h['posts']}")
    if s["topics"]:
        lines += ["", "<b>Topics (30 days)</b>", ", ".join(f"{_esc(t)} {n}" for t, n in s["topics"])]
    send(chat_id, "\n".join(lines))


def cmd_topics(chat_id: int, _args: str) -> None:
    posts_cfg = _config()["platforms"]["x"]["posts"]
    topics = ", ".join(t["name"] for t in posts_cfg["topics"])
    scenes = ", ".join(sc["name"] for sc in posts_cfg["selfies"]["scenes"])
    send(chat_id, f"<b>Topics:</b> {_esc(topics)}\n<b>Photo scenes:</b> {_esc(scenes)}\n\n"
                  "e.g. <code>/post hummus</code>, <code>/post photo record bin</code>")


def cmd_help(chat_id: int, _args: str) -> None:
    send(chat_id, "\n".join(f"/{name} — {_esc(desc)}" for name, desc in COMMANDS)
         + "\n\nEvery post still goes through the daily cap and all content checks.")


# --- control commands ---

def _parse_topic(args: str) -> tuple[str | None, str | None]:
    """'' -> any, 'photo [scene]' -> photo, '<topic>' -> topic. Returns (topic, error)."""
    args = args.strip().lower()
    if not args:
        return None, None
    posts_cfg = _config()["platforms"]["x"]["posts"]
    if args.split()[0] == "photo":
        scene = args[len("photo"):].strip()
        scenes = [sc["name"] for sc in posts_cfg["selfies"]["scenes"]]
        if scene and scene not in scenes:
            return None, f"No photo scene “{scene}”. Scenes: {', '.join(scenes)}"
        return (f"photo: {scene}" if scene else "photo"), None
    topics = [t["name"] for t in posts_cfg["topics"]]
    if args not in topics:
        return None, f"No topic “{args}”. Topics: {', '.join(topics)} — or “photo”."
    return args, None


def _cap_note() -> str:
    posted = dashboard.build_snapshot()["today"]
    left = posted["cap"] - posted["posted"]
    return "" if left > 0 else "\n⚠️ Today's cap is already reached, so this won't post until you raise the cap."


def cmd_post(chat_id: int, args: str) -> None:
    topic, err = _parse_topic(args)
    if err:
        send(chat_id, _esc(err))
        return
    control.request_post(topic)
    send(chat_id, f"👍 Posting {_esc(topic or 'a random topic')} within ~30 s. I'll message you when it's out." + _cap_note())


def cmd_next(chat_id: int, args: str) -> None:
    args = args.strip()
    posts = 1
    first, _, rest = args.partition(" ")
    if first.isdigit() and rest:
        posts, args = max(1, min(int(first), 5)), rest.strip()
    if not args:
        send(chat_id, "Usage: <code>/next riff on the Turnstile show this weekend</code> (or <code>/next 3 …</code> for the next 3 posts)")
        return
    if len(args) > MAX_HINT:
        send(chat_id, f"Keep it under {MAX_HINT} characters.")
        return
    word = decide.blocked_word(args, _config()["guardrails"].get("blocked_words", []))
    if word:
        send(chat_id, f"That includes a blocked word (“{_esc(word)}”), so I won't pass it on.")
        return
    control.set_hint(args, posts)
    send(chat_id, f"👍 The next {posts} post(s) will work in: “{_esc(args)}”. Use /post to do it now.")


def cmd_clearnext(chat_id: int, _args: str) -> None:
    control.set_hint(None)
    send(chat_id, "Cleared the /next guidance.")


def cmd_add(chat_id: int, args: str) -> None:
    when_text, _, topic_text = args.strip().partition(" ")
    when = None
    for fmt in ("%H:%M", "%I:%M%p", "%I%p"):
        try:
            when = datetime.strptime(when_text.lower(), fmt).time()
            break
        except ValueError:
            continue
    if when is None:
        send(chat_id, "Usage: <code>/add 21:30</code>, <code>/add 9:30pm photo</code>, <code>/add 13:05 hummus</code>")
        return
    tz = ZoneInfo(_config()["platforms"]["x"]["posts"]["timezone"])  # same clock as the posting loop
    if datetime.combine(date.today(), when, tz) <= datetime.now(tz):
        send(chat_id, "That time has already passed today.")
        return
    topic, err = _parse_topic(topic_text)
    if err:
        send(chat_id, _esc(err))
        return
    control.add_slot(date.today().isoformat(), when.strftime("%H:%M"), topic)
    send(chat_id, f"👍 Added a post at {when.strftime('%-I:%M %p')} today ({_esc(topic or 'random topic')})." + _cap_note())


def cmd_skip(chat_id: int, _args: str) -> None:
    n = control.add_skip()
    send(chat_id, f"👍 Skipping the next {n} scheduled post(s). /post still works.")


def cmd_pause(chat_id: int, _args: str) -> None:
    control.set_paused(True)
    send(chat_id, "⏸ Scheduled posts paused until /resume. /post still works.")


def cmd_resume(chat_id: int, _args: str) -> None:
    control.set_paused(False)
    send(chat_id, "▶️ Scheduled posts resumed.")


HANDLERS = {
    "status": cmd_status, "start": cmd_help, "help": cmd_help, "today": cmd_today, "posts": cmd_posts,
    "problems": cmd_problems, "stats": cmd_stats, "topics": cmd_topics, "post": cmd_post,
    "next": cmd_next, "clearnext": cmd_clearnext, "add": cmd_add, "skip": cmd_skip,
    "pause": cmd_pause, "resume": cmd_resume,
}


# --- alerts ---

def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    # First run: start at the end of the log so old entries aren't replayed as alerts.
    return {"log_offset": POST_LOG.stat().st_size if POST_LOG.exists() else 0}


def _save_state(st: dict) -> None:
    STATE_PATH.write_text(json.dumps(st))


def check_alerts(chat_id: int, st: dict) -> None:
    """New post-log lines since last time -> alerts for posts and problems."""
    if not POST_LOG.exists():
        return
    with POST_LOG.open() as f:
        f.seek(st["log_offset"])
        new = f.read()
        end = f.tell()
    handle = dashboard.X_HANDLE
    for line in new.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("dry_run") or "plan" in e:
            continue
        if e.get("posted"):
            caption = f"✅ <b>Posted</b> ({_esc(e.get('topic') or '')})\n{_esc(e.get('text') or '')}\n{_link(handle, e.get('id'))}"
            image = e.get("image")
            if image and (ROOT / image).exists():
                send_photo(chat_id, str(ROOT / image), caption)
            else:
                send(chat_id, caption)
        elif "failed" in e or "skipped" in e:
            reason = e.get("failed") or e.get("skipped") or ""
            send(chat_id, f"⚠️ <b>{'Failed' if 'failed' in e else 'Skipped'}</b>: {_esc(_plain(reason))}\n<i>{_esc(reason[:300])}</i>")
    # Advance only after everything was sent; if Telegram drops mid-way, they're retried next time.
    st["log_offset"] = end
    _save_state(st)


def service_state() -> str:
    return subprocess.run(["systemctl", "--user", "is-active", dashboard.SERVICE],
                          capture_output=True, text=True).stdout.strip() or "unknown"


# --- main loop ---

def whoami() -> None:
    print("Send any message to your bot in Telegram…")
    offset = None
    while True:
        for u in _call("getUpdates", data={"timeout": POLL_TIMEOUT, **({"offset": offset} if offset else {})}):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if msg:
                who = msg.get("from", {})
                print(f"chat id: {msg['chat']['id']}  (from @{who.get('username')}, {who.get('first_name')})")
                print("Put it in .env as TELEGRAM_CHAT_ID=<that number>.")
                _call("getUpdates", data={"offset": offset, "timeout": 0})  # mark as read
                return


def run() -> None:
    chat_id = int(os.environ.get("TELEGRAM_CHAT_ID") or 0)
    if not chat_id:
        sys.exit("Set TELEGRAM_CHAT_ID in .env (find it with: python -m src.telegram_bot --whoami)")
    _call("setMyCommands", json={"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
    st = _load_state()
    _save_state(st)
    last_service = service_state()
    offset = None
    print("telegram remote running")
    while True:
        try:
            updates = _call("getUpdates", data={"timeout": POLL_TIMEOUT, **({"offset": offset} if offset else {})})
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                if msg.get("chat", {}).get("id") != chat_id:
                    continue  # not you: ignore silently
                text = (msg.get("text") or "").strip()
                if not text.startswith("/"):
                    send(chat_id, "Commands only — try /help")
                    continue
                name, _, args = text[1:].partition(" ")
                name = name.split("@")[0].lower()  # "/status@MyBot" -> "status"
                handler = HANDLERS.get(name)
                if handler is None:
                    send(chat_id, "Unknown command — try /help")
                    continue
                try:
                    handler(chat_id, args)
                except Exception as e:  # a broken command shouldn't take the remote down
                    send(chat_id, f"That command failed: {_esc(type(e).__name__)}: {_esc(str(e)[:300])}")
            check_alerts(chat_id, st)
            now_service = service_state()
            if now_service != last_service:
                icon = "✅" if now_service == "active" else "🔴"
                send(chat_id, f"{icon} X bot service is now <b>{_esc(now_service)}</b> (was {_esc(last_service)})")
                last_service = now_service
        except requests.RequestException as e:  # Telegram unreachable (Wi-Fi/DNS drop): wait and retry
            print(f"telegram unreachable: {e}")
            time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--whoami", action="store_true")
    args = parser.parse_args()
    if not TOKEN:
        sys.exit("Set TELEGRAM_BOT_TOKEN in .env (create the bot with @BotFather in Telegram)")
    whoami() if args.whoami else run()


if __name__ == "__main__":
    main()
