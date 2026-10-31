"""Main run loop for X: in-character original posts via the official API, on a human-ish schedule.

    python main_x.py                        # run for real (posts to X)
    python main_x.py --dry-run              # sample week's schedule + a few posts; post nothing
    python main_x.py --make-reference       # generate the selfie character's reference face
    python main_x.py --selfie "hummus aisle" --dry-run  # make a selfie post, save it, don't post
    python main_x.py --selfie "hummus aisle"            # make a selfie post and post it now

The bot does not read X or reply to anyone: X's Automation Rules ban keyword-search
auto-replies and scripting the X website, and AI reply bots need X's written approval.

Some scheduled posts are AI-generated "selfies" of the character with a caption (see
`platforms.x.posts.selfies` in config and src/images.py); every one carries the configured label.

Scheduling: each day the bot decides up front how many posts to make (sometimes none) and
picks random times for them inside the configured windows, at least min_gap_minutes apart.
"""

import argparse
import difflib
import json
import os
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from src import decide, generate, state

CONFIG_PATH = "config/config.yaml"
POST_LOG = Path("logs/x_posts.jsonl")
IMAGE_DIR = Path("data/images/posts")
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


def special_day(posts_cfg: dict, day: date) -> list[tuple[datetime, str | None]] | None:
    """Fixed (time, topic) slots for `day` from `special_days` in config, or None if it's a normal
    day. These replace the random plan for that day (no skip-day roll); the cap still applies."""
    days = {str(k): v for k, v in (posts_cfg.get("special_days") or {}).items()}
    if day.isoformat() not in days:
        return None
    tz = ZoneInfo(posts_cfg["timezone"])
    return [
        (datetime.combine(day, datetime.strptime(slot["time"], "%H:%M").time(), tz), slot.get("topic"))
        for slot in days[day.isoformat()]
    ]


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
    config: dict, recent: list[str], last_topic: str | None = None, topic_name: str | None = None
) -> tuple[str, str] | tuple[None, str]:
    """Returns (post text with hashtags, topic name), or (None, reason) if nothing usable.
    `topic_name` forces a topic; otherwise one is picked at random (never a scheduled_only one)."""
    x_cfg = config["platforms"]["x"]
    posts_cfg = x_cfg["posts"]
    if topic_name:
        topics = [t for t in posts_cfg["topics"] if t["name"] == topic_name]
        if not topics:
            return None, f"no topic named {topic_name!r}"
    else:
        pool = [t for t in posts_cfg["topics"] if not t.get("scheduled_only")]
        topics = [t for t in pool if t["name"] != last_topic] or pool
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


def selfies_ready(selfie_cfg: dict) -> bool:
    return bool(
        selfie_cfg.get("enabled")
        and Path(selfie_cfg["reference_image"]).exists()
        and os.environ.get("OPENAI_API_KEY")
    )


def make_selfie_post(config: dict, recent: list[str], scene_name: str | None = None) -> tuple[dict | None, str]:
    """Caption + image for a selfie post. Returns ({text, topic, image, alt}, "") or (None, reason).
    The caption is made and checked first, so a rejected caption doesn't cost an image."""
    from src import images  # imported here so text-only runs don't need the OpenAI SDK/key

    x_cfg = config["platforms"]["x"]
    selfie_cfg = x_cfg["posts"]["selfies"]
    scenes = selfie_cfg["scenes"]
    if scene_name:
        scenes = [s for s in scenes if s["name"] == scene_name]
        if not scenes:
            return None, f"no scene named {scene_name!r}"
    scene = random.choice(scenes)
    n_tags = min(random.choice(x_cfg["posts"]["hashtag_counts"]), len(scene["hashtags"]))
    tags = random.sample(scene["hashtags"], k=n_tags)
    parts = [p for p in [selfie_cfg.get("label", ""), *tags] if p]  # label "" = no label
    suffix = (" " + " ".join(parts)) if parts else ""
    budget = x_cfg["max_reply_chars"] - len(suffix)
    pov = scene.get("pov", False)  # first-person shot (his hands, his counter), not a selfie
    shown = "you took, from your point of view," if pov else "you're posting of yourself"
    topic = (
        f"{scene['caption']}. This is the caption for a photo {shown}"
        f" {scene['image_prompt']}. Don't describe the photo; react to the moment."
    )
    length = random.choice(["short", "medium"])  # captions stay brief
    body = generate.generate_post("X (Twitter)", topic, budget, recent, length)
    if body is None:
        return None, f"selfie {scene['name']}: no usable caption"
    reason = _rejection(body, recent, config)
    if reason:
        return None, f"selfie {scene['name']}: {reason} — {body!r}"
    out = IMAGE_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{scene['name'].replace(' ', '-')}.jpg"
    try:
        images.make_selfie(selfie_cfg, scene["image_prompt"], out, pov=pov)
    except Exception as e:  # OpenAI errors (billing, moderation, bad model name) — don't crash the loop
        return None, f"selfie {scene['name']}: image failed: {e}"
    if pov:
        alt = f"AI-generated photo: {scene['image_prompt']}."
    else:
        alt = f"AI-generated photo of the bot's character, a man {scene['image_prompt']}."
    return {"text": body + suffix, "topic": f"selfie: {scene['name']}", "image": str(out), "alt": alt}, ""


def _publish(post: dict) -> str | None:
    """Sends one post to X. Returns its id, or None if X refused it (logged)."""
    import tweepy

    from src import x_api  # imported here so dry runs never touch the X API

    try:
        media_ids = [x_api.upload_image(post["image"], post["alt"])] if post.get("image") else None
        post_id = x_api.post(post["text"], media_ids)
    except tweepy.TweepyException as e:
        # Rate limit (429), billing/permission (402/403), duplicate post, etc. Not recorded as a
        # post, so it doesn't count toward the cap.
        print(f"post failed: {e}")
        _log({"posted": False, "failed": str(e), **post})
        return None
    state.record_post("x", post["text"])
    _log({"posted": True, **post, "id": post_id})
    print(f"posted {post_id}: {post['text']}" + (f" [{post['image']}]" if post.get("image") else ""))
    return post_id


def post_once(
    config: dict, last_topic: str | None, selfie_scene: str | None = None, topic: str | None = None
) -> str | None:
    """Makes and publishes one post, unless the daily cap is hit. Returns the topic posted.
    Sometimes (selfies.chance) it's a selfie; `selfie_scene` forces one ("" = any scene).
    `topic` forces a text post on that topic (special_days)."""
    posts_cfg = config["platforms"]["x"]["posts"]
    if state.daily_post_count("x") >= posts_cfg["daily_post_cap"]:
        print("daily post cap reached")
        return None
    recent = state.recent_posts("x")
    selfie_cfg = posts_cfg.get("selfies", {})
    roll_selfie = topic is None and selfies_ready(selfie_cfg) and random.random() < selfie_cfg["chance"]
    if selfie_scene is not None or roll_selfie:
        post, reason = make_selfie_post(config, recent, selfie_scene or None)
        if post:
            return post["topic"] if _publish(post) else None
        print(f"selfie skipped — {reason}")
        _log({"posted": False, "skipped": reason})
        if selfie_scene is not None:
            return None  # asked for a selfie specifically; don't swap in a text post
    text, topic_or_reason = make_post(config, recent, last_topic, topic)
    if text is None:
        print(f"skipped — {topic_or_reason}")
        _log({"posted": False, "skipped": topic_or_reason})
        return None
    return topic_or_reason if _publish({"text": text, "topic": topic_or_reason}) else None


def dry_run(config: dict) -> None:
    """Prints a sample week of schedules and a few posts. Posts nothing; doesn't touch state."""
    posts_cfg = config["platforms"]["x"]["posts"]
    today = datetime.now(ZoneInfo(posts_cfg["timezone"])).date()
    print("Sample schedule (re-rolled each run):")
    for i in range(7):
        day = today + timedelta(days=i)
        plan = special_day(posts_cfg, day) or [(t, None) for t in plan_day(posts_cfg, day)]
        print(f"  {day:%a %b %d}: " + (", ".join(f"{t:%-I:%M %p}" + (f" ({topic})" if topic else "") for t, topic in plan) or "no posts"))
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


def selfie_dry_run(config: dict, scene: str | None) -> None:
    """Makes one selfie post (image costs money) and saves it, but doesn't post or touch state."""
    post, reason = make_selfie_post(config, state.recent_posts("x"), scene)
    if post is None:
        print(f"skipped — {reason}")
        return
    print(f"[{post['topic']}] ({len(post['text'])} chars)\n  {post['text']}\n  image: {post['image']}")
    _log({"posted": False, "dry_run": True, **post})


def make_reference(config: dict) -> None:
    from src import images

    selfie_cfg = config["platforms"]["x"]["posts"]["selfies"]
    ref = Path(selfie_cfg["reference_image"])
    # Never overwrite the current face; the user swaps it in by hand if they like the new one.
    out = ref.with_name(ref.stem + "-candidate" + ref.suffix) if ref.exists() else ref
    images.make_reference(selfie_cfg, out)
    print(f"saved {out}" + (f" — rename it to {ref.name} to use it" if out != ref else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--make-reference", action="store_true")
    parser.add_argument("--selfie", nargs="?", const="", metavar="SCENE", help="post a selfie now")
    args = parser.parse_args()
    config = load_config()
    if args.make_reference:
        make_reference(config)
        return
    if args.selfie is not None:
        if args.dry_run:
            selfie_dry_run(config, args.selfie or None)
        else:
            post_once(config, None, selfie_scene=args.selfie)
        return
    if args.dry_run:
        dry_run(config)
        return
    posts_cfg = config["platforms"]["x"]["posts"]
    tz = ZoneInfo(posts_cfg["timezone"])
    last_topic = None
    while True:
        now = datetime.now(tz)
        # Plan today; times already past (e.g. after a restart) are dropped, not made up.
        plan = special_day(posts_cfg, now.date())
        if plan is None:
            plan = [(t, None) for t in plan_day(posts_cfg, now.date())]
        plan = [(t, topic) for t, topic in plan if t > now]
        if state.daily_post_count("x") > 0:
            plan = []  # restarted on a day that already has a post (e.g. a manual one); leave it there
        print(f"{now:%a %b %d}: " + (", ".join(f"{t:%-I:%M %p}" + (f" ({topic})" if topic else "") for t, topic in plan) or "no posts"))
        _log({"plan": [[t.isoformat(timespec="minutes"), topic] for t, topic in plan]})
        for when, topic in plan:
            _sleep_until(when, tz)
            late = datetime.now(tz) - when
            if late > MAX_LATENESS:
                # Computer was asleep/suspended past the slot; don't post at an odd hour.
                print(f"skipped {when:%-I:%M %p} slot — {late} late (computer asleep?)")
                _log({"posted": False, "skipped": f"missed {when.isoformat(timespec='minutes')} slot, {late} late"})
                continue
            last_topic = post_once(config, last_topic, topic=topic) or last_topic
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
