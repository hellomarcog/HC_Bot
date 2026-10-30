"""UNUSED — do not use. Scripting the X website violates X's Automation Rules (see CLAUDE.md,
"X rules"); kept only as a record of the dropped approach.

Finds candidate posts on X via browser search (Free-tier API has no read/search access).

Selectors verified against the live site 2026-10-29: each result is an
article[data-testid='tweet'], its canonical link is the one wrapping the <time> element
(other /status/ links in the article point at photos, analytics, or quoted posts), and
the body is div[data-testid='tweetText']. Results load after the page does, so wait for
them, then scroll a little to load more than the first handful.
"""

import random
from dataclasses import dataclass
from urllib.parse import quote

BASE = "https://x.com"


@dataclass
class Tweet:
    id: str
    url: str
    author: str
    text: str


def search_recent(page, query: str, limit: int = 25, scrolls: int = 3) -> list[Tweet]:
    page.goto(f"{BASE}/search?q={quote(query)}&f=live")
    try:
        page.wait_for_selector("article[data-testid='tweet']", timeout=20000)
    except Exception:
        return []  # no results, or X didn't load the timeline — try again next poll
    for _ in range(scrolls):
        page.mouse.wheel(0, random.randint(1800, 3000))
        page.wait_for_timeout(random.randint(1500, 3500))
    articles = page.query_selector_all("article[data-testid='tweet']")
    tweets = []
    for article in articles[:limit]:
        link = article.query_selector("a:has(time)")
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
