"""Simple, inspectable reply-or-skip logic: relevance, dedupe, daily cap. Platform-agnostic."""

from . import state


def is_relevant(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def should_reply(platform: str, post_id: str, text: str, config: dict) -> bool:
    if state.already_replied(post_id):
        return False
    if state.daily_count(platform) >= config["platforms"][platform]["daily_reply_cap"]:
        return False
    return is_relevant(text, config["keywords"]["interests"])
