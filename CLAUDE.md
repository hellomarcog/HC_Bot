# HC_Bot

A disclosed bot account with a distinct, opinionated personality, acting at a human pace: on Reddit it reads posts and replies in character; on X it makes its own original posts (no replies — see "X rules" below). Built for humor/experimentation, not growth or lead-gen.

## Non-negotiables (read before touching persona or scope logic)

- **The bot discloses itself as a bot.** Profile bio on every platform contains an explicit bot-identification message. This is never removed, hidden, or made ambiguous to "seem more human" — the human-like tone/pacing is about personality and timing, not about deceiving people into thinking they're talking to a real undisclosed person.
- **No targeting private individuals.** The bot only engages with public content — subreddit posts/comments, public accounts, brands, bands, shows, venues. It does not initiate snarky/confrontational replies at private randoms' personal posts. "Doesn't back down" applies to debates about hardcore music, deathcore, hummus, and Golden Girls — not to picking fights with regular people's unrelated posts.
- **Daily reply/post cap.** Hard numeric limit per platform per day (`daily_reply_cap` and, for X, `posts.daily_post_cap` in `config/config.yaml`). This is a hard stop, not a suggestion — the bot does not exceed it even if engagement is going well.
- Changes to any of the above require explicit sign-off from the user, not just a passing comment in a prompt.

## Persona: "the bot's" character

- **Identity**: human male, 40s, East Coast. The persona is written and talks like a real person with decades of specific taste — not a generic enthusiastic AI assistant.
- **Tone**: snarky, witty, teasing, strong opinions, doesn't back down when challenged. Confident, not cruel — the snark is the entertainment, not an excuse for harassment.
- **Core interests**: hardcore punk and heavy metal; hummus (authenticity matters a lot to him); The Golden Girls and other shows set in the same universe (e.g. Empty Nest, The Golden Palace).
- **Strong opinions**:
  - Passionate advocate for "real" hardcore — bands that capture the authentic spirit of the genre.
  - Actively dismissive of trend-chasing in hardcore, especially deathcore, which he considers a departure from real hardcore values.
  - Has specific, defensible takes — not just "old good, new bad." Should be able to name names and explain why, in character.
- **Voice notes for generation**: short, punchy, conversational. Opinion first, reasoning second. Willing to argue but not abusive. References his specific tastes (hummus quality, Golden Girls universe trivia) even when tangential, because that's part of the bit.

## Platform scope

- **Reddit**: starting with r/hardcore only. More subreddits to be added later — don't hardcode assumptions that r/hardcore is the only one; keep the subreddit list configurable.
- **X**: current focus, **original posts only** — the bot posts its own takes on a conservative, randomized schedule (`platforms.x.posts` in config: topics, hashtags, windows, cap). It does not read X, search X, reply, mention, or follow. Following is done by hand from `docs/follow_list.md`.

## X rules (from X's Automation Rules, April 2026 — reviewed with the user 2026-10-29)

- **No keyword-search auto-replies.** Automated replies are only allowed to users who opted in (mentioned the bot, replied to its post, DM'd it), with an easy opt-out and one reply per interaction.
- **No scripting the X website** (Playwright reading/search on X) — X says this can mean permanent suspension. All X activity goes through the official API.
- **AI reply bots need X's prior written approval.** A future mention-triggered reply mode is possible (the pay-per-use API has a mentions endpoint) but needs that approval first — don't build it until the user says it's been granted.
- **No automated @mentions, no trending-topic posting, no duplicate/near-duplicate posts, no bulk/automated following.** `main_x.py` enforces the first and third in code.

## Technical approach

- **Language**: Python.
- **Browser automation**: Playwright driving a real logged-in browser session, used for Reddit only. (`src/x_read.py` is a leftover from the abandoned X search approach — don't use it; see "X rules".)
- **X goes through the official API only** (`src/x_api.py`, Tweepy with OAuth 1.0a user-context auth). X API billing is pay-per-use. Don't move any X activity to browser automation, and don't silently add Reddit's API either — these are deliberate per-platform choices.
- **Reply generation**: Claude API, with the persona above encoded as a system prompt. Keep the persona definition in one place (`persona/system_prompt.md`) that both the code and future edits reference, rather than duplicating persona text across files. `src/generate.py` is shared across platforms — pass a plain-language source description (e.g. "r/hardcore on Reddit", "X (Twitter)") rather than hardcoding one platform's framing.
- **Autonomy model**: runs autonomously (no per-reply human approval) but inside the guardrails above. Log every action (what it saw, what it decided, what it posted) somewhere reviewable — this is "autonomous with limits," not "fire and forget with no visibility."
- **Content guardrails**: `guardrails.blocked_words` in config — any post (to reply to, or generated by the bot) containing one is skipped. Generated text over the platform's `max_reply_chars` is dropped, never truncated or posted.
- **Shared vs. platform-specific code**: `decide.py` (should-reply logic, blocked words), `act.py` (pause + post + record), `generate.py` (reply and original-post generation), and `state.py` are platform-agnostic — they take a `platform` string and work the same way for Reddit and X. Keep new platforms plugging into these rather than forking them.

## Setup

```
python -m venv .venv && source .venv/bin/activate   # system python doesn't have the deps
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in ANTHROPIC_API_KEY and, for X, the X_* API keys from developer.x.com
python -m src.browser reddit https://old.reddit.com/login
```

The Reddit login command opens a real browser window for a one-time manual login; log in by hand, then press Enter in the terminal to save the session (gitignored — equivalent to a credential). After that: `python main.py` runs the Reddit loop, and `python main_x.py` runs the X posting loop (API only, no login needed). `python main_x.py --dry-run` shows a sample week's schedule and a few generated posts without posting anything; everything the X loop does is logged to `logs/x_posts.jsonl`.

### Running in the background

The X loop runs as a systemd user service (`deploy/hc-bot-x.service`) so it survives logouts and restarts. Install once with the commands at the top of that file. Day to day:

```
systemctl --user status hc-bot-x      # is it running? shows the latest output
journalctl --user -u hc-bot-x -f      # watch its output live (Ctrl+C stops watching, not the bot)
systemctl --user restart hc-bot-x     # after changing code or config
systemctl --user stop hc-bot-x        # stop posting
```

Don't also run `python main_x.py` in a terminal while the service is running — that's two bots.

## Working conventions

- Don't add platforms, subreddits, or accounts to the active scope without the user explicitly naming them — scope grows by instruction, not by assumption.
- Don't loosen any of the Non-negotiables above as a side effect of an unrelated change (e.g. don't bump the daily cap while refactoring the scheduler).
- Favor simple, inspectable logic for "should I reply to this post" over clever heuristics — this bot's behavior needs to be easy to reason about and tune by hand.
