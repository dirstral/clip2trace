# Research log: Telegram global search feasibility

_Date: 2026-06-01. Sources: core.telegram.org (method docs), docs.telethon.dev,
tl.telethon.dev._

## Verdict

**MVP feasible with caveats. Global search requires a user session and may be
flaky. Visual verification must be our differentiator.**

## Findings

### The right method: `channels.searchPosts` (MTProto)
- *"Globally search for posts from public channels (including those we aren't a
  member of) containing either a specific hashtag, or a full text query."*
- Params: `hashtag` XOR `query` (exactly one), `offset_rate`, `offset_peer`,
  `offset_id`, `limit`, `allow_paid_stars`.
- **"Only users can use this method"** → a **USER account** is required; bots
  cannot call it. Error `420 FROZEN_METHOD_INVALID` if the account is frozen.
- **Hashtag search is unmetered**; **free-text search is metered** — each user
  has limited free full-text "slots", then it costs Telegram Stars
  (`allow_paid_stars`). Check quota with `channels.checkSearchPostsFlood`.

### Not sufficient
- `messages.searchGlobal` — global but scoped to the user's *own* dialogs/subs;
  not arbitrary public channels. `messages.search` — single chat only.
- **Bot API: NO global public-post search.** Bots only see chats they're in.

### Telethon
```python
from telethon import functions, types
result = client(functions.channels.SearchPostsRequest(
    hashtag="somehashtag",          # XOR query — set exactly one
    offset_rate=0, offset_peer=types.InputPeerEmpty(),
    offset_id=0, limit=100,
    # allow_paid_stars=<stars>      # only for paid free-text search
))
```
- Verify the exact call against the live `tl.telethon.dev` page before shipping
  (the doc page returned corrupted content during research; the call name and
  params are confirmed from the MTProto spec).

### Session (headless)
- Use **`StringSession`**, generated once interactively (phone + login code +
  optional 2FA). The string is **equivalent to full account access** — store as
  a Sinas secret, never commit. `scripts/bootstrap_telegram_session.py` does this.

### Operational risks
- `FloodWaitError` (420) carries `.seconds`; Telethon auto-sleeps below
  `flood_sleep_threshold`. Real waits range seconds → hours under aggressive use.
- Automated user-account activity carries **account-ban risk** (community
  reports). Use a dedicated, disposable account; rate-limit conservatively.
- Free-text search is economically bounded (Stars). Prefer handle + hashtag.

## Secrets in Sinas
Store `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING` as Sinas
**secrets** (declared as `type: secret` package variables). They are only
readable from `context["secrets"]` inside **sharedPool/trusted** functions —
hence `search_global_telegram_posts` and `fetch_telegram_candidate_media` are
declared `sharedPool: true`.

## Fallback / demo modes (build all four)
1. **Manually provided Telegram URLs** — operator pastes candidate links.
2. **Cached candidate results** — `cached_results` input (used by the demo).
3. **Curated test fixture** — `tests/fixtures/sample_telegram_results.json`.
4. **Optional local Telegram corpus** — a pre-indexed local set (stretch).

The search function returns an explicit `live_unavailable` / `demo_no_data`
status and diagnostics — it **never silently pretends** live search ran.
