"""Reddit watching + reply posting, using old.reddit.com for stable, scrapeable markup.

NOTE: these selectors are a first pass based on old.reddit.com's known DOM structure.
They haven't been run against the live site yet — expect to adjust them once tested.
"""

from dataclasses import dataclass

BASE = "https://old.reddit.com"


@dataclass
class Post:
    id: str  # fullname, e.g. t3_abc123
    title: str
    permalink: str
    selftext: str


def fetch_new_posts(page, subreddit: str, limit: int = 25) -> list[Post]:
    page.goto(f"{BASE}/r/{subreddit}/new/")
    things = page.query_selector_all("div.thing[data-fullname]")
    posts = []
    for thing in things[:limit]:
        fullname = thing.get_attribute("data-fullname")
        title_el = thing.query_selector("a.title")
        if not fullname or not title_el:
            continue
        permalink = thing.get_attribute("data-permalink") or title_el.get_attribute("href")
        selftext_el = thing.query_selector(".usertext-body .md")
        posts.append(
            Post(
                id=fullname,
                title=title_el.inner_text(),
                permalink=permalink,
                selftext=selftext_el.inner_text() if selftext_el else "",
            )
        )
    return posts


def post_reply(page, permalink: str, reply_text: str) -> None:
    url = permalink if permalink.startswith("http") else f"{BASE}{permalink}"
    page.goto(url)
    textarea = page.query_selector(".commentarea > form textarea")
    if textarea is None:
        raise RuntimeError(f"Couldn't find the top-level comment box on {url}")
    textarea.click()
    textarea.type(reply_text, delay=40)  # human-ish typing speed, not instant paste
    page.click(".commentarea > form button[type=submit]")
