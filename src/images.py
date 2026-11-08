"""Generates the bot's photos via the OpenAI Images API (needs OPENAI_API_KEY — a ChatGPT
subscription doesn't include API access).

Every selfie is an edit of one reference portrait, so the character's face stays the same across
posts. Image prompts come from config (`platforms.x.posts.selfies`), not from the model, so what
gets drawn stays easy to inspect and can't drift into real people, logos, or band art.
"""

import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from src import usage

load_dotenv()

# Added to every image prompt.
STYLE_RULES = (
    " Shot on a phone, natural and a little imperfect, not a polished ad. No readable text, logos,"
    " brand names, or band names anywhere in the image. Nobody else's face in frame."
)

_client = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _save(response, out_path: Path, model: str) -> Path:
    usage.record_image(model, response.usage)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(response.data[0].b64_json))
    return out_path


def make_reference(cfg: dict, out_path: Path) -> Path:
    """A plain portrait of the character, used as the face for every later selfie."""
    prompt = (
        f"Photorealistic phone selfie of {cfg['character']}. Neutral background, even light,"
        " face clearly visible, looking at the camera." + STYLE_RULES
    )
    response = _openai().images.generate(
        model=cfg["model"], prompt=prompt, size=cfg["size"], quality=cfg["quality"], output_format="jpeg"
    )
    return _save(response, out_path, cfg["model"])


def make_selfie(cfg: dict, scene_prompt: str, out_path: Path, pov: bool = False) -> Path:
    """The reference character in `scene_prompt`, or (pov=True) a first-person shot from his
    point of view — no face, so no reference image needed."""
    if pov:
        prompt = (
            f"Amateur first-person point-of-view phone photo, {scene_prompt}. Not staged, not"
            " professional, not food-blog styling." + STYLE_RULES
        )
        response = _openai().images.generate(
            model=cfg["model"], prompt=prompt, size=cfg["size"], quality=cfg["quality"], output_format="jpeg"
        )
        return _save(response, out_path, cfg["model"])
    prompt = (
        f"Photorealistic phone selfie of the man in the reference photo — same face, same person —"
        f" {scene_prompt}. He is {cfg['character']}." + STYLE_RULES
    )
    with open(cfg["reference_image"], "rb") as ref:
        response = _openai().images.edit(
            model=cfg["model"],
            image=[ref],
            prompt=prompt,
            size=cfg["size"],
            quality=cfg["quality"],
            output_format="jpeg",
        )
    return _save(response, out_path, cfg["model"])
