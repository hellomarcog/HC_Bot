"""Main run loop for X: in-character original posts via the official API, on a human-ish schedule.

    python main_x.py            # run for real (posts to X)
    python main_x.py --dry-run  # show a sample week's schedule + a few posts; post nothing

The bot does not read X or reply to anyone: X's Automation Rules ban keyword-search
auto-replies and scripting the X website, and AI reply bots need X's written approval.

Scheduling: each day the bot decides up front how many posts to make (sometimes none) and
picks random times for them inside the configured windows, at least min_gap_minutes apart.
"""

import difflib
import json
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from src import decide, generate, state

CONFIG_PATH = "config/config.yaml"
POST_LOG = Path("logs/x_posts.jsonl")
DRY_RUN_POSTS = 3
LENGTH_WEIGHTS = {"short": 3, "medium": 4, "long": 2}
MAX_LATENESS = timedelta(minutes=30)  # skip a slot rather than post this long after it


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _log(entry: dict) -> None:
    POST_LOG.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
    with POST_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def plan_day(posts_cfg: dict, day: date) -> list[datetime]:
    """Random post times for `day`, or [] on a skip day."""
    if random.random() < posts_cfg["skip_day_chance"]:
        return []
    tz = ZoneInfo(posts_cfg["timezone"])
    windows = []
    for w in posts_cfg["windows"]:
        start = datetime.combine(day, datetime.strptime(w["start"], "%H:%M").time(), tz)
        end = datetime.combine(day, datetime.strptime(w["end"], "%H:%M").time(), tz)
        windows.append((start, end))
    total = sum((end - start).total_seconds() for start, end in windows)
    count = random.randint(posts_cfg["posts_per_day"]["min"], posts_cfg["posts_per_day"]["max"])
    gap = timedelta(minutes=posts_cfg["min_gap_minutes"])
    for _ in range(100):  # retry until the gaps work out
        times = []
        for _ in range(count):
            # Pick a window weighted by its length, then a random second within it.
            start, end = random.choices(windows, weights=[(e - s).total_seconds() / total for s, e in windows])[0]
            times.append(start + timedelta(seconds=random.uniform(0, (end - start).total_seconds())))
        times.sort()
        if all(b - a >= gap for a, b in zip(times, times[1:])):
            return times
    return times[:1]  # couldn't fit them all with the gap; post once instead


def _rejection(text: str, recent: list[str], config: dict) -> str | None:
    """Why this post must not go out, or None if it's fine. Simple checks, easy to tune."""
    if "@" in text:
        return "contains an @mention"  # automated mentions need opt-in under X's rules
    if "http" in text or "www." in text:
        return "contains a link"
    word = decide.blocked_word(text, config["guardrails"].get("blocked_words", []))
    if word:
        return f"blocked word: {word}"
    for old in recent:
        if difflib.SequenceMatcher(None, text.lower(), old.lower()).ratio() > 0.6:
            return "too similar to a recent post"  # X bans duplicate/near-duplicate posts
    return None


def make_post(
    config: dict, recent: list[str], last_topic: str | None = None
) -> tuple[str, str] | tuple[None, str]:
    """Returns (post text with hashtags, topic name), or (None, reason) if nothing usable."""
    x_cfg = config["platforms"]["x"]
    posts_cfg = x_cfg["posts"]
    topics = [t for t in posts_cfg["topics"] if t["name"] != last_topic] or posts_cfg["topics"]
    topic = random.choice(topics)
    n_tags = min(random.choice(posts_cfg["hashtag_counts"]), len(topic["hashtags"]))
    tags = random.sample(topic["hashtags"], k=n_tags)
    suffix = (" " + " ".join(tags)) if tags else ""
    length = random.choices(list(LENGTH_WEIGHTS), weights=list(LENGTH_WEIGHTS.values()))[0]
    budget = x_cfg["max_reply_chars"] - len(suffix)
    body = generate.generate_post("X (Twitter)", topic["prompt"], budget, recent, length)
    if body is None:
        return None, f"{topic['name']}: no usable text (refused, empty, or too long)"
    reason = _rejection(body, recent, config)
    if reason:
        return None, f"{topic['name']}: {reason} — {body!r}"
    return body + suffix, topic["name"]


def post_once(config: dict, last_topic: str | None) -> str | None:
    """Makes and publishes one post, unless the daily cap is hit. Returns the topic posted."""
    posts_cfg = config["platforms"]["x"]["posts"]
    if state.daily_post_count("x") >= posts_cfg["daily_post_cap"]:
        return None
    text, topic_or_reason = make_post(config, state.recent_posts("x"), last_topic)
    if text is None:
        print(f"skipped — {topic_or_reason}")
        _log({"posted": False, "skipped": topic_or_reason})
        return None
    import tweepy

    from src import x_api  # imported here so dry runs never touch the X API

    try:
        post_id = x_api.post(text)
    except tweepy.TweepyException as e:
        # Rate limit (429), billing/permission (402/403), duplicate post, etc. Not recorded as a
        # post, so it doesn't count toward the cap.
        print(f"post failed: {e}")
        _log({"posted": False, "failed": str(e), "topic": topic_or_reason, "text": text})
        return None
    state.record_post("x", text)
    _log({"posted": True, "topic": topic_or_reason, "text": text, "id": post_id})
    print(f"posted {post_id}: {text}")
    return topic_or_reason


def dry_run(config: dict) -> None:
    """Prints a sample week of schedules and a few posts. Posts nothing; doesn't touch state."""
    posts_cfg = config["platforms"]["x"]["posts"]
    today = datetime.now(ZoneInfo(posts_cfg["timezone"])).date()
    print("Sample schedule (re-rolled each run):")
    for i in range(7):
        day = today + timedelta(days=i)
        times = plan_day(posts_cfg, day)
        print(f"  {day:%a %b %d}: " + (", ".join(f"{t:%-I:%M %p}" for t in times) or "no posts"))
    print()
    recent = list(state.recent_posts("x"))
    last_topic = None
    for _ in range(DRY_RUN_POSTS):
        text, topic_or_reason = make_post(config, recent, last_topic)
        if text is None:
            print(f"skipped — {topic_or_reason}\n")
            _log({"posted": False, "dry_run": True, "skipped": topic_or_reason})
            continue
        print(f"[{topic_or_reason}] ({len(text)} chars)\n  {text}\n")
        _log({"posted": False, "dry_run": True, "topic": topic_or_reason, "text": text})
        recent.append(text)  # so later dry-run posts avoid repeating earlier ones
        last_topic = topic_or_reason
    print(f"Dry run done. Logged to {POST_LOG}")


def main() -> None:
    config = load_config()
    if "--dry-run" in sys.argv[1:]:
        dry_run(config)
        return
    posts_cfg = config["platforms"]["x"]["posts"]
    tz = ZoneInfo(posts_cfg["timezone"])
    last_topic = None
    while True:
        now = datetime.now(tz)
        # Plan today; times already past (e.g. after a restart) are dropped, not made up.
        plan = [t for t in plan_day(posts_cfg, now.date()) if t > now]
        print(f"{now:%a %b %d}: " + (", ".join(f"{t:%-I:%M %p}" for t in plan) or "no posts"))
        _log({"plan": [t.isoformat(timespec="minutes") for t in plan]})
        for when in plan:
            _sleep_until(when, tz)
            late = datetime.now(tz) - when
            if late > MAX_LATENESS:
                # Computer was asleep/suspended past the slot; don't post at an odd hour.
                print(f"skipped {when:%-I:%M %p} slot — {late} late (computer asleep?)")
                _log({"posted": False, "skipped": f"missed {when.isoformat(timespec='minutes')} slot, {late} late"})
                continue
            last_topic = post_once(config, last_topic) or last_topic
        # Wait until a random few minutes after midnight, then plan the next day.
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tz)
        _sleep_until(tomorrow + timedelta(seconds=random.uniform(60, 1800)), tz)


def _sleep_until(when: datetime, tz: ZoneInfo) -> None:
    """Sleep in short steps against the wall clock. One long time.sleep() doesn't count time the
    computer spends suspended, so after waking it would oversleep by however long it was asleep."""
    while (remaining := (when - datetime.now(tz)).total_seconds()) > 0:
        time.sleep(min(remaining, 60))


if __name__ == "__main__":
    main()
