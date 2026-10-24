"""Main run loop for X: browser search to find candidate posts, decide, generate, reply via API."""

import random
import time

import yaml

from src import act, browser, decide, generate, x_api, x_read

CONFIG_PATH = "config/config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _delay_range(cfg: dict) -> tuple[float, float]:
    return cfg["min"], cfg["max"]


def run_once(page, config: dict) -> None:
    x_cfg = config["platforms"]["x"]
    query = " OR ".join(config["keywords"]["interests"])
    for tweet in x_read.search_recent(page, query):
        if not decide.should_reply("x", tweet.id, tweet.text, config):
            continue
        reply_text = generate.generate_reply("X (Twitter)", tweet.text)
        act.post_and_record("x", tweet.id, reply_text, lambda t: x_api.post_reply(tweet.id, t))
        time.sleep(random.uniform(*_delay_range(x_cfg["reply_delay_seconds"])))


def main() -> None:
    config = load_config()
    x_cfg = config["platforms"]["x"]
    with browser.session("x", headless=True) as page:
        while True:
            run_once(page, config)
            time.sleep(random.uniform(*_delay_range(x_cfg["poll_interval_seconds"])))


if __name__ == "__main__":
    main()
