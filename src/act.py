"""Posts a reply with a human-like pause before typing, then records it in state."""

import random
import time

from . import reddit, state


def post_and_record(page, platform: str, post_id: str, permalink: str, reply_text: str) -> None:
    time.sleep(random.uniform(2, 8))  # pause before "typing", like a human reading the post first
    reddit.post_reply(page, permalink, reply_text)
    state.record_reply(platform, post_id)
