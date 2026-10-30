# HC_Bot — Plan

## Goal

A disclosed bot account with an opinionated persona, for humor/experimentation — not growth, lead-gen, or influence. On X it makes its own original posts; on Reddit it reads posts and replies in character, at a human-like pace.

## Key decisions so far

- **Disclosure**: profile bio explicitly identifies the account as a bot on every platform. The "act human" goal is about personality and pacing, not deceiving people about what they're talking to. On X, also turn on the account's "Automated" label.
- **Autonomy**: runs autonomously (no per-post human approval), bounded by hard guardrails — daily caps, no targeting private individuals, blocked-words filter, stays out of politics/tragedy/current events.
- **Persona**: man in his 40s, East Coast. Snarky, witty, teasing, doesn't back down in an argument but isn't abusive. Passionate about "real" hardcore/metal, actively dismissive of deathcore and genre trend-chasing. Also has strong, specific opinions on authentic hummus and The Golden Girls (plus Empty Nest / The Golden Palace, same universe).
- **X: original posts only (decided 2026-10-29).** The original plan (browser keyword search -> AI reply via API) was dropped after reviewing X's Automation Rules, which prohibit keyword-search auto-replies, scripting the X website, and AI reply bots without X's written approval. X's rules do allow automated original posts for entertainment via the API, so that's what the bot does. Following accounts is done by hand from `docs/follow_list.md`.
- **X posting pace**: deliberately conservative to start — 0–2 posts/day (hard cap 2), ~1 day in 5 skipped, random times in a lunch window and an evening window (Eastern), at least 2.5h apart. Mixed post lengths, 0–2 niche hashtags, topics rotate. Raise `posts_per_day` and `daily_post_cap` together once the first weeks look fine.
- **X API**: pay-per-use billing. Rate limits are far above what the bot uses.
- **Reddit**: r/hardcore only for now, more subreddits by explicit instruction. Playwright browser automation end-to-end (read + post). Not yet checked against Reddit's own bot rules — do that before going live.
- **Reply/post generation**: Claude API (`claude-sonnet-5-5`), persona as a system prompt kept in one file (`persona/system_prompt.md`).

## Architecture

```
HC_Bot/
├── CLAUDE.md                  # project rules, non-negotiables, X rules, setup steps
├── PLAN.md                    # this file
├── docs/follow_list.md        # hand-curated X accounts to follow manually
├── persona/system_prompt.md   # prose persona, fed to Claude as the system prompt
├── config/config.yaml         # subreddits, caps, X posting schedule/topics/hashtags, blocked words
├── src/
│   ├── browser.py             # Playwright session mgmt (Reddit)
│   ├── reddit.py              # watches + replies on r/hardcore (old.reddit.com), end-to-end browser
│   ├── x_api.py               # X via the official API (Tweepy, OAuth 1.0a user context)
│   ├── x_read.py              # UNUSED leftover from the dropped X search approach — don't use
│   ├── decide.py              # should-reply logic + blocked words — platform-agnostic
│   ├── generate.py            # Claude API: replies and original posts — platform-agnostic
│   ├── act.py                 # human-like pause, post, record in state — platform-agnostic
│   └── state.py               # JSON-backed: replied IDs, recent posts, daily counts
├── main.py                    # Reddit loop
└── main_x.py                  # X posting loop (daily plan -> generate -> checks -> API post)
```

State (`data/state.json`), saved browser sessions (`data/*_storage_state.json`), and logs (`logs/`) are gitignored.

## Status

- [x] Repo, CLAUDE.md, scaffold, persona, config
- [x] X developer app created, API keys in `.env`
- [x] X posting loop built and dry-run tested: schedule, topic rotation, length/hashtag variety, length limit, @mention/link/blocked-word/near-duplicate checks, error handling, JSONL logging
- [ ] X profile ready: bot disclosure in bio, "Automated" label on, avatar/banner, pinned intro post
- [ ] Follow ~30–60 accounts by hand from `docs/follow_list.md` over the first two weeks
- [ ] Confirm per-post cost on the X Developer Console usage page
- [ ] First live run of `main_x.py`; review `logs/x_posts.jsonl` daily for the first week (watch for factual errors in trivia)
- [ ] Reddit: check Reddit's bot rules, then live-test `main.py` (selectors untested)

## Later / parked

- **X mention replies** (reply only to people who mention the bot or reply to its posts): needs X's written approval for AI reply bots — request via the X developer forum (Rules and Policies), describing the opt-in, opt-out, caps and filters. Then read mentions via the API, never the browser.
- **Polls** via the API (e.g. "best NYHC record of the 80s?") for engagement.
- **A model-based topic check** (politics/tragedy/death) in addition to the blocked-words list, which can't catch everything.
