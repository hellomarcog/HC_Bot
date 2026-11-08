"""Posts on X (text, images) via the official API — required even on Free tier, since the bot is
disclosed and X's Automation Rules expect disclosed bots to post through the API rather than
by driving the UI directly."""

import os

import requests
import tweepy
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

from src import usage

load_dotenv()

_client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)


def post_reply(tweet_id: str, reply_text: str) -> None:
    _client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)


def post(text: str, media_ids: list[str] | None = None) -> str:
    """Publishes an original post (optionally with uploaded images); returns its id."""
    post_id = str(_client.create_tweet(text=text, media_ids=media_ids).data["id"])
    usage.record_x("post")
    return post_id


# Tweepy's media upload uses the old v1.1 endpoint, so images go to the v2 endpoint directly,
# signed with the same OAuth 1.0a keys.
_oauth = OAuth1(
    os.environ["X_API_KEY"],
    os.environ["X_API_SECRET"],
    os.environ["X_ACCESS_TOKEN"],
    os.environ["X_ACCESS_TOKEN_SECRET"],
)


def upload_image(path: str, alt_text: str | None = None) -> str:
    """Uploads a JPEG/PNG (5 MB max) and returns its media id, for post(..., media_ids=[id])."""
    with open(path, "rb") as f:
        r = requests.post(
            "https://api.x.com/2/media/upload",
            auth=_oauth,
            files={"media": f},
            data={"media_category": "tweet_image"},
            timeout=60,
        )
    if not r.ok:
        raise tweepy.TweepyException(f"media upload failed: {r.status_code} {r.text}")
    media_id = r.json()["data"]["id"]
    usage.record_x("media_upload")
    if alt_text:
        m = requests.post(
            "https://api.x.com/2/media/metadata",
            auth=_oauth,
            json={"id": media_id, "metadata": {"alt_text": {"text": alt_text[:1000]}}},
            timeout=30,
        )
        if not m.ok:  # alt text is nice to have; don't lose the post over it
            print(f"alt text not set: {m.status_code} {m.text}")
    return media_id
