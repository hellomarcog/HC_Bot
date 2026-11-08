"""Records every paid API call (Claude, OpenAI images, X) with its token counts and estimated cost
to logs/usage.jsonl, for the dashboard and Telegram /stats.

Costs are estimates from the `costs:` prices in config, computed when the call happens (so a later
price change doesn't rewrite history). The real bills are in each provider's console. Recording
never raises: a bookkeeping problem must not stop a post.
"""

import json
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
USAGE_LOG = ROOT / "logs" / "usage.jsonl"
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _prices() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text()).get("costs", {})


def _write(entry: dict) -> None:
    USAGE_LOG.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
    with USAGE_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def record_claude(model: str, usage) -> None:
    """`usage` is an Anthropic response's .usage. Thinking tokens are included in output_tokens."""
    try:
        p = _prices().get("claude", {})
        tokens = {
            "input": usage.input_tokens or 0,
            "output": usage.output_tokens or 0,
            "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        }
        cost = sum(tokens[k] * p.get(k, 0) for k in tokens) / 1_000_000
        _write({"service": "claude", "model": model, **tokens, "cost": round(cost, 6)})
    except Exception as e:
        print(f"usage: couldn't record Claude call: {e}")


def record_image(model: str, usage) -> None:
    """`usage` is an OpenAI ImagesResponse's .usage (may be None)."""
    try:
        p = _prices().get("openai_image", {})
        details = getattr(usage, "input_tokens_details", None)
        text_in = getattr(details, "text_tokens", None)
        image_in = getattr(details, "image_tokens", None)
        if text_in is None and image_in is None:  # no breakdown: price all input as text
            text_in, image_in = getattr(usage, "input_tokens", 0) or 0, 0
        out = getattr(usage, "output_tokens", 0) or 0
        cost = (
            (text_in or 0) * p.get("text_input", 0)
            + (image_in or 0) * p.get("image_input", 0)
            + out * p.get("image_output", 0)
        ) / 1_000_000
        _write({"service": "openai_image", "model": model, "text_input": text_in or 0,
                "image_input": image_in or 0, "output": out, "cost": round(cost, 6)})
    except Exception as e:
        print(f"usage: couldn't record image call: {e}")


def record_x(action: str) -> None:
    """action: "post" or "media_upload" (priced per request)."""
    try:
        _write({"service": "x", "action": action, "cost": _prices().get("x", {}).get(action, 0)})
    except Exception as e:
        print(f"usage: couldn't record X call: {e}")


def entries() -> list[dict]:
    if not USAGE_LOG.exists():
        return []
    out = []
    for line in USAGE_LOG.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
