"""Main run loop: watch r/hardcore, decide, generate, act — at human-like intervals."""

import random
import time

import yaml

from src import act, browser, decide, generate, reddit

CONFIG_PATH = "config/config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _delay_range(cfg: dict) -> tuple[float, float]:
    return cfg["min"], cfg["max"]


def run_once(page, config: dict) -> None:
    reddit_cfg = config["platforms"]["reddit"]
    for subreddit in reddit_cfg["subreddits"]:
        for post in reddit.fetch_new_posts(page, subreddit):
            text = f"{post.title}\n{post.selftext}"
            if not decide.should_reply("reddit", post.id, text, config):
                continue
            reply_text = generate.generate_reply(f"r/{subreddit} on Reddit", text)
            if reply_text is None:
                continue
            act.post_and_record(
                "reddit", post.id, reply_text, lambda t: reddit.post_reply(page, post.permalink, t)
            )
            time.sleep(random.uniform(*_delay_range(reddit_cfg["reply_delay_seconds"])))


def main() -> None:
    config = load_config()
    poll_cfg = config["platforms"]["reddit"]["poll_interval_seconds"]
    with browser.session("reddit", headless=True) as page:
        while True:
            run_once(page, config)
            time.sleep(random.uniform(*_delay_range(poll_cfg)))


if __name__ == "__main__":
    main()
