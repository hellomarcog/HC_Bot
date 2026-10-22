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
- **X**: no accounts/hashtags defined yet. Leave the watch-list empty/configurable rather than guessing targets.

## Technical approach

- **Language**: Python.
- **Browser automation**: Playwright (or Selenium if a specific need arises) driving a real logged-in browser session on both Reddit and X, to get human-like pacing, scrolling, and timing — not the official REST APIs.
  - Note: X's Automation Rules formally expect disclosed bots to post via their official API even when browser-driven pacing is used elsewhere; we're accepting that gray area knowingly for this project. Don't "fix" this unilaterally by switching X to API-only without checking with the user first.
- **Reply generation**: Claude API, with the persona above encoded as a system prompt. Keep the persona definition in one place (e.g. `persona/system_prompt.md`) that both the code and future edits can reference, rather than duplicating persona text across files.
- **Autonomy model**: runs autonomously (no per-reply human approval) but inside the guardrails above. Log every action (what it saw, what it decided, what it posted) somewhere reviewable — this is "autonomous with limits," not "fire and forget with no visibility."

## Working conventions

- Don't add platforms, subreddits, or accounts to the active scope without the user explicitly naming them — scope grows by instruction, not by assumption.
- Don't loosen any of the Non-negotiables above as a side effect of an unrelated change (e.g. don't bump the daily cap while refactoring the scheduler).
- Favor simple, inspectable logic for "should I reply to this post" over clever heuristics — this bot's behavior needs to be easy to reason about and tune by hand.
