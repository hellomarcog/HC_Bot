"""Posts a reply with a human-like pause beforehand, then records it in state. Platform-agnostic."""

import random
import time
from typing import Callable

from . import state


def post_and_record(platform: str, post_id: str, reply_text: str, post_fn: Callable[[str], None]) -> None:
    time.sleep(random.uniform(2, 8))  # pause before posting, like a human reading first
    post_fn(reply_text)
    state.record_reply(platform, post_id)
