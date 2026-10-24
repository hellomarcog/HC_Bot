"""Finds candidate posts on X via browser search (Free-tier API has no read/search access).

NOTE: these selectors are a first pass based on X's known data-testid attributes
(article[data-testid='tweet'], div[data-testid='tweetText']). Untested against the
live site — expect to adjust once run for real.
"""

from dataclasses import dataclass
from urllib.parse import quote

BASE = "https://x.com"


@dataclass
class Tweet:
    id: str
    url: str
    author: str
    text: str


def search_recent(page, query: str, limit: int = 25) -> list[Tweet]:
    page.goto(f"{BASE}/search?q={quote(query)}&f=live")
    articles = page.query_selector_all("article[data-testid='tweet']")
    tweets = []
    for article in articles[:limit]:
        link = article.query_selector("a[href*='/status/']")
        if not link:
            continue
        href = link.get_attribute("href")
        tweet_id = href.rstrip("/").split("/")[-1]
        author = href.split("/status/")[0].rstrip("/").split("/")[-1]
        text_el = article.query_selector("div[data-testid='tweetText']")
        tweets.append(
            Tweet(
                id=tweet_id,
                url=f"{BASE}{href}",
                author=author,
                text=text_el.inner_text() if text_el else "",
            )
        )
    return tweets
