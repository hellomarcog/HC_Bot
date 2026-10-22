"""Generates in-character replies via the Claude API."""

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

PERSONA_PATH = Path(__file__).resolve().parent.parent / "persona" / "system_prompt.md"
MODEL = "claude-sonnet-5"

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_persona = PERSONA_PATH.read_text()


def generate_reply(title: str, body: str) -> str:
    post_text = f"Title: {title}\n\n{body}".strip()
    response = _client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=_persona,
        messages=[
            {
                "role": "user",
                "content": f"Here's a Reddit post in r/hardcore:\n\n{post_text}\n\nWrite your reply.",
            }
        ],
    )
    return response.content[0].text.strip()
