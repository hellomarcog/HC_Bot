# HC_Bot — Plan

## Goal

A disclosed bot account that reads posts on Reddit (and eventually X) and replies in character, at a human-like pace, for humor/experimentation — not growth, lead-gen, or influence.

## Key decisions so far

- **Disclosure**: profile bio explicitly identifies the account as a bot on every platform. The "act human" goal is about personality and pacing, not deceiving people about what they're talking to.
- **Autonomy**: runs autonomously (no per-reply human approval), bounded by hard guardrails — daily reply/post cap, no targeting private individuals, stays out of politics/tragedy/current events.
- **Persona**: man in his 40s, East Coast. Snarky, witty, teasing, doesn't back down in an argument but isn't abusive. Passionate about "real" hardcore/metal, actively dismissive of deathcore and genre trend-chasing. Also has strong, specific opinions on authentic hummus and The Golden Girls (plus Empty Nest / The Golden Palace, same universe).
- **Platform scope**: Reddit starts with r/hardcore only; more subreddits added later by explicit instruction. X is the current build focus — no specific accounts named yet, so discovery is keyword-based search rather than a fixed account list.
- **Access method**: Reddit uses Playwright browser automation end-to-end (read + post). X is a hybrid: Playwright browser automation to *find* posts (search), official X API to *post* replies — X's Free tier has no read/search access, and X's Automation Rules expect disclosed bots to post through the API anyway, so this resolves both constraints at once.
- **X API tier**: Free (write-only; posting a reply costs nothing beyond rate limits). Upgrading to Basic ($200/mo) later would add native read/search and remove the need for browser-based discovery on X, if that becomes worthwhile.
- **Reply generation**: Claude API, with persona encoded as a system prompt kept in one file (`persona/system_prompt.md`) rather than duplicated across code.

## Architecture

```
HC_Bot/
├── CLAUDE.md                  # project rules, non-negotiables, setup steps
├── PLAN.md                    # this file
├── persona/system_prompt.md   # prose persona, fed to Claude as the system prompt
├── config/config.yaml         # subreddit list, daily caps, polling/reply delay windows, keywords
├── src/
│   ├── browser.py             # Playwright session mgmt (one-time manual login, reused session)
│   ├── reddit.py              # watches + replies on r/hardcore (old.reddit.com), end-to-end browser
│   ├── x_read.py              # finds candidate posts on X via browser search (Free tier has no API search)
│   ├── x_api.py                # posts X replies via the official API (Tweepy, OAuth 1.0a user context)
│   ├── decide.py               # should-reply logic: relevance, dedupe, daily cap — platform-agnostic
│   ├── generate.py             # Claude API call: persona + post -> reply text — platform-agnostic
│   ├── act.py                  # human-like pause, post, record in state — platform-agnostic
│   └── state.py                # JSON-backed: replied post IDs, daily reply counts
├── main.py                     # Reddit loop (watch/decide/generate/act, human-like delays)
└── main_x.py                   # X loop (browser search -> decide/generate -> API reply)
```

State (`data/state.json`) and the saved browser login session (`data/*_storage_state.json`) are gitignored — the session file is credential-equivalent and never belongs in version control.

## Status

- [x] Repo initialized, pushed to private GitHub (`hellomarcog/HC_Bot`)
- [x] CLAUDE.md with persona, scope, and non-negotiable guardrails
- [x] Full scaffold committed: persona prompt, config, Playwright session handling, watch/decide/generate/act loop
- [x] X hybrid architecture added: `x_read.py` (browser search) + `x_api.py` (official API posting), `decide`/`act`/`generate` generalized to be platform-agnostic
- [ ] Live-tested against real Reddit — `reddit.py`'s scraping/posting selectors are a first pass against old.reddit.com's known DOM and haven't been run against the live site yet
- [ ] Live-tested against real X — `x_read.py`'s selectors are a first pass based on known `data-testid` attributes, also untested
- [ ] Manual login flow exercised end-to-end (Reddit and X)
- [ ] X developer account + app created, API keys obtained (Free tier) and dropped into `.env`
- [ ] Reply quality/tone tuned against real posts, on both platforms

## Next steps

1. Set up X developer account/app at developer.x.com, get Free-tier API keys, add to `.env`.
2. `playwright install chromium`, run the one-time manual login for X (and Reddit), confirm session persistence works.
3. Run `main_x.py` against the live site, fix whatever search/scraping selectors break against the real DOM, confirm a reply actually posts via the API.
4. Review/tune generated replies against real posts for tone and the "real hardcore vs. deathcore" opinion-strength.
5. Come back to Reddit (`main.py`) once X is stable, or in parallel if bandwidth allows.
