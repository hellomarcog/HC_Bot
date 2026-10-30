"""Simple, inspectable reply-or-skip logic: relevance, dedupe, daily cap. Platform-agnostic."""

import re

from . import state


def is_relevant(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def blocked_word(text: str, blocked_words: list[str]) -> str | None:
    """The first blocked word/phrase found in text as a whole word (plurals included), or None."""
    for word in blocked_words:
        if re.search(rf"\b{re.escape(word.lower())}(s|es)?\b", text.lower()):
            return word
    return None


def should_reply(platform: str, post_id: str, text: str, config: dict) -> bool:
    if state.already_replied(post_id):
        return False
    if state.daily_count(platform) >= config["platforms"][platform]["daily_reply_cap"]:
        return False
    if blocked_word(text, config["guardrails"].get("blocked_words", [])):
        return False
    return is_relevant(text, keywords_for(platform, config))


def keywords_for(platform: str, config: dict) -> list[str]:
    """A platform's own keyword list if it has one, else the shared interests list."""
    return config["platforms"][platform].get("keywords", config["keywords"]["interests"])
