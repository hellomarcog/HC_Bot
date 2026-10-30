"""Generates in-character replies and original posts via the Claude API."""

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

PERSONA_PATH = Path(__file__).resolve().parent.parent / "persona" / "system_prompt.md"
MODEL = "claude-sonnet-5-5"

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_persona = PERSONA_PATH.read_text()


def generate_reply(source_description: str, post_text: str, max_chars: int | None = None) -> str | None:
    """Returns the reply text, or None if the model refused, produced no usable reply, or went
    over max_chars (the platform's hard length limit, if it has one)."""
    instruction = "Write your reply."
    if max_chars:
        # Ask for a bit under the hard limit so near-misses still fit.
        instruction += (
            f" It must fit in a single post: {max_chars - 30} characters or fewer, one paragraph,"
            " no line breaks."
        )
    content = f"Here's a post from {source_description}:\n\n{post_text.strip()}\n\n{instruction}"
    return _complete(content, effort="low", max_chars=max_chars)


LENGTHS = {
    "short": "a short one-liner, under 100 characters",
    "medium": "a couple of sentences, roughly 120-180 characters",
}


def generate_post(
    source_description: str, topic: str, max_chars: int, recent_posts: list[str], length: str
) -> str | None:
    """An original (non-reply) post about `topic`, in character. Returns None if refused, empty,
    or over max_chars. `recent_posts` are shown so the model doesn't repeat itself. `length` is
    "short", "medium", or "long" — mixing them keeps the feed from looking machine-made."""
    recent = "\n".join(f"- {p}" for p in recent_posts) or "(none yet)"
    # "long" asks well under the hard limit: the model tends to overshoot by 10-30 characters.
    size = LENGTHS.get(length, f"{max_chars - 50} characters or fewer")
    content = (
        f"Write an original post for your account on {source_description}. Topic: {topic}\n\n"
        f"Your recent posts — don't repeat their takes, jokes, bands, or phrasing:\n{recent}\n\n"
        f"Rules for this post: {size}, one paragraph, no line"
        " breaks. Write it the way a real person posts, not a polished caption. No hashtags,"
        " no @mentions, no links — hashtags get added separately. Only"
        " state facts (band names, records, episodes, cast) you're sure are accurate. Just the"
        " post text, nothing else."
    )
    # Medium effort: only a few posts a day, and accuracy on names/trivia matters more here.
    return _complete(content, effort="medium", max_chars=max_chars)


def _complete(user_content: str, effort: str, max_chars: int | None) -> str | None:
    response = _client.messages.create(
        model=MODEL,
        # Thinking is always on for this model and counts toward max_tokens, so leave headroom
        # beyond the short text itself.
        max_tokens=4000,
        output_config={"effort": effort},
        system=_persona,
        messages=[{"role": "user", "content": user_content}],
    )
    if response.stop_reason != "end_turn":  # refusal or cut off — don't post partial text
        print(f"generate: dropped, stop_reason={response.stop_reason} {response.stop_details or ''}")
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if max_chars and len(text) > max_chars:
        # Never post text the platform would reject or truncate.
        print(f"generate: dropped, {len(text)} chars > {max_chars}: {text!r}")
        return None
    return text or None
