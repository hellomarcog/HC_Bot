"""Posts replies on X via the official API — required even on Free tier, since the bot is
disclosed and X's Automation Rules expect disclosed bots to post through the API rather than
by driving the UI directly."""

import os

import tweepy
from dotenv import load_dotenv

load_dotenv()

_client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)


def post_reply(tweet_id: str, reply_text: str) -> None:
    _client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
