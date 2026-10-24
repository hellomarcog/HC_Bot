# HC_Bot

A disclosed bot account that reads posts on Reddit and X and replies to them in character, acting at a human pace with a distinct, opinionated personality. Built for humor/experimentation, not growth or lead-gen.

## Non-negotiables (read before touching persona or scope logic)

- **The bot discloses itself as a bot.** Profile bio on every platform contains an explicit bot-identification message. This is never removed, hidden, or made ambiguous to "seem more human" — the human-like tone/pacing is about personality and timing, not about deceiving people into thinking they're talking to a real undisclosed person.
- **No targeting private individuals.** The bot only engages with public content — subreddit posts/comments, public accounts, brands, bands, shows, venues. It does not initiate snarky/confrontational replies at private randoms' personal posts. "Doesn't back down" applies to debates about hardcore music, deathcore, hummus, and Golden Girls — not to picking fights with regular people's unrelated posts.
- **Daily reply/post cap.** Hard numeric limit per platform per day (see `config/limits.py` once it exists). This is a hard stop, not a suggestion — the bot does not exceed it even if engagement is going well.
- Changes to any of the above require explicit sign-off from the user, not just a passing comment in a prompt.

## Persona: "the bot's" character

- **Identity**: human male, 40s, East Coast. The persona is written and talks like a real person with decades of specific taste — not a generic enthusiastic AI assistant.
- **Tone**: snarky, witty, teasing, strong opinions, doesn't back down when challenged. Confident, not cruel — the snark is the entertainment, not an excuse for harassment.
- **Core interests**: hardcore punk and heavy metal; hummus (authenticity matters a lot to him); The Golden Girls and other shows set in the same universe (e.g. Empty Nest, The Golden Palace).
- **Strong opinions**:
  - Passionate advocate for "real" hardcore — bands that capture the authentic spirit of the genre.
  - Actively dismissive of trend-chasing in hardcore, especially deathcore, which he considers a departure from real hardcore values.
  - Has specific, defensible takes — not just "old good, new bad." Should be able to name names and explain why, in character.
- **Voice notes for reply generation**: short, punchy, conversational. Opinion first, reasoning second. Willing to argue but not abusive. References his specific tastes (hummus quality, Golden Girls universe trivia) even when tangential, because that's part of the bit.

## Platform scope

- **Reddit**: starting with r/hardcore only. More subreddits to be added later — don't hardcode assumptions that r/hardcore is the only one; keep the subreddit list configurable.
- **X**: current focus. No specific accounts to watch yet — discovery is keyword-based (search across X, not a fixed account list) using the shared `keywords.interests` list in config. Narrow to specific accounts later only if the user names them.

## Technical approach

- **Language**: Python.
- **Browser automation**: Playwright driving a real logged-in browser session, used for *reading* content on both Reddit and X (human-like pacing, scrolling, timing).
- **X posting goes through the official API, not the browser.** X API access is Free tier, which has no read/search endpoints — so X is a hybrid: Playwright finds candidate posts via search, but replies are published via the official API (`src/x_api.py`, using Tweepy with OAuth 1.0a user-context auth). This satisfies X's Automation Rules expectation that disclosed bots post through the API, while keeping discovery free. Don't silently move X posting back to browser automation, and don't silently add Reddit's API either — these are deliberate per-platform choices.
- **Reply generation**: Claude API, with the persona above encoded as a system prompt. Keep the persona definition in one place (`persona/system_prompt.md`) that both the code and future edits reference, rather than duplicating persona text across files. `src/generate.py` is shared across platforms — pass a plain-language source description (e.g. "r/hardcore on Reddit", "X (Twitter)") rather than hardcoding one platform's framing.
- **Autonomy model**: runs autonomously (no per-reply human approval) but inside the guardrails above. Log every action (what it saw, what it decided, what it posted) somewhere reviewable — this is "autonomous with limits," not "fire and forget with no visibility."
- **Shared vs. platform-specific code**: `decide.py` (should-reply logic), `act.py` (pause + post + record), `generate.py` (reply generation), and `state.py` are platform-agnostic — they take a `platform` string and work the same way for Reddit and X. Keep new platforms plugging into these rather than forking them.

## Setup

```
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in ANTHROPIC_API_KEY and, for X, the X_* API keys from developer.x.com
python -m src.browser reddit https://old.reddit.com/login
python -m src.browser x https://x.com/login
```

Both login commands open a real browser window for a one-time manual login; log in by hand, then press Enter in the terminal to save the session (gitignored — equivalent to a credential). After that: `python main.py` runs the Reddit loop, `python main_x.py` runs the X loop (search via browser, reply via API).

## Working conventions

- Don't add platforms, subreddits, or accounts to the active scope without the user explicitly naming them — scope grows by instruction, not by assumption.
- Don't loosen any of the Non-negotiables above as a side effect of an unrelated change (e.g. don't bump the daily cap while refactoring the scheduler).
- Favor simple, inspectable logic for "should I reply to this post" over clever heuristics — this bot's behavior needs to be easy to reason about and tune by hand.
