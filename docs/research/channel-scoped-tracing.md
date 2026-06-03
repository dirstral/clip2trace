# Channel-scoped visual source-tracing (live, via-10 Telegram, 2026-06-03)

Global text search has hard limits (premium for free-text, **caption-only** matching,
new-channel index lag — see [telegram-live-test.md](telegram-live-test.md)). A
**channel-scoped** mode sidesteps all three: enumerate a known channel's videos
directly, segment + perceptually-hash them, and match an input video **by content**.

## What this proves

Two local dev tools (worker-parity: `cv2`/`scenedetect` blocked → PyAV+numpy path,
Pillow/imagehash phash — exactly what the Sinas worker runs) drove the full
channel-scoped pipeline against the live `t.me/clip2trace` channel:

- **`scripts/enumerate_channel.py`** — Telethon `iter_messages` (catches video
  *documents* like `.mkv` by mime/extension, not just streamable video messages) →
  bounded download → shot detection + per-segment phash → cross-post vs within-post
  reuse clustering. Result: **7 videos, 64 segments**; 0 cross-post reuse (the samples
  are unrelated compilations), 3 within-post repeats inside one compilation.
- **`scripts/match_into_channel.py`** — builds the channel corpus once, then traces
  each input video into it, reusing the **real rubric** (`clip2trace.matching` +
  `clip2trace.scoring` + `clip2trace.report` — no ad-hoc thresholds).

### One-by-one match result (all 5 `samples/*.mkv` as inputs)

| input sample | → channel post | visual | confidence | label |
|---|---|---|---|---|
| Массированный удар… | `t.me/clip2trace/5` | 1.000 | 0.500 | plausible |
| Мужчина напал… | `t.me/clip2trace/6` | 1.000 | 0.500 | plausible |
| Политолог… | `t.me/clip2trace/7` | 1.000 | 0.500 | plausible |
| Israel captures castle… | `t.me/clip2trace/8` | 1.000 | 0.500 | plausible |
| Myanmar explosion… | `t.me/clip2trace/9` | 1.000 | 0.500 | plausible |

Each input's **top** candidate is its own channel post at `visual=1.000`, with
every input segment localized to the matching channel timestamp (`seg_NNN
[a–b s] == msg M [a–b s] (sim 1.000)`). Unrelated channel videos correctly sit
at the phash baseline (~0.69–0.75) and stay `weak`.

## Honest scoring note (matters for demo expectations)

`visual_similarity` is **40%** of the confidence rubric (`scoring.WEIGHTS`). A
self-match (input == its own channel post) therefore scores `visual≈1.0` but
**overall confidence ≈0.50** — we set `channel_relevance=1.0` (the candidate is, by
construction, from the chosen channel) so it lands at **"plausible"**, not higher.
Reaching `strong`/`very_strong` would require the other dimensions to genuinely fire
(post **predates** the input, caption/handle/OCR text match). That is by design: the
headline is **localization** (which post + timestamp), with confidence shown honestly
beside it — never "the original".

## Why this is the better demo than global search

Content-based, no premium, no caption dependency, no index lag. The on-instance
production form is the `enumerate_channel_videos` Sinas function (mirrors
`search_global_telegram_posts`, then reuses the existing
`fetch_telegram_candidate_media → verify_media_similarity → rank_source_candidates →
render_report` chain). **That function is `area:telegram` (Ark's lane).** These local
scripts are the proven reference implementation + contract for it.
