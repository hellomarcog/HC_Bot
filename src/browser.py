"""Playwright session management: one saved login per platform, reused across runs."""

from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def _storage_state_path(platform: str) -> Path:
    return DATA_DIR / f"{platform}_storage_state.json"


def login(platform: str, url: str) -> None:
    """One-time interactive login. Opens a real browser window; log in by hand, then press Enter."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        input(f"Log into {platform} in the opened window, then press Enter here to save the session...")
        context.storage_state(path=str(_storage_state_path(platform)))
        browser.close()
    print(f"Saved session: {_storage_state_path(platform)}")


@contextmanager
def session(platform: str, headless: bool = True):
    """Yields a logged-in Playwright page for `platform`, reusing the saved session."""
    state_path = _storage_state_path(platform)
    if not state_path.exists():
        raise RuntimeError(
            f"No saved session for {platform}. Run: python -m src.browser {platform} <login_url>"
        )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()
        try:
            yield page
        finally:
            context.storage_state(path=str(state_path))  # keep session fresh for next run
            browser.close()


if __name__ == "__main__":
    import sys

    _, platform_arg, url_arg = sys.argv
    login(platform_arg, url_arg)
