# Live Telegram end-to-end test (via-10, 2026-06-03)

First real run of the full clip2trace pipeline against **live** Telegram (not demo
fixtures), on the via-10 instance with a premium Telegram user session. Captures what
works, and the real-world constraints discovered.

## TL;DR

- The **entire pipeline runs end-to-end live**: upload → PyAV decode → shot detection →
  OCR (Claude vision) → query generation → **live global search** → candidate-media
  download → perceptual hash → visual verify → rank → report. All stages confirmed on a
  real uploaded video.
- **Discovery is text-only.** Telegram's global search (`channels.SearchPostsRequest`)
  matches a **hashtag or free-text against post captions** — there is **no
  content/reverse-video search**. So clip2trace can only *retrieve* candidates by the
  video's OCR'd on-screen text, then **visually verify** them (phash). The visual step is
  *verification*, not discovery.
- Consequence: a source is findable **only when the reused footage carries on-screen text
  (handle / hashtag / distinctive quote) that also appears in the source post's caption**,
  **and** the source post is indexed. Arbitrary footage with no shared text token cannot be
  found — not a bug, a property of Telegram's API.

## What was verified working

| Stage | Result |
|---|---|
| Upload to `clip2trace/input-videos` | 201 |
| `analyze_input_video` (live) | `method: shot_detection_pyav`, real segments |
| `extract_segment_clues` | real phashes + **OCR read the on-screen text** |
| `generate_telegram_queries` | handle/ocr/context/hashtag queries from clues |
| `search_global_telegram_posts` (live) | returned **100 real candidates** |
| `fetch_telegram_candidate_media(dry_run=false)` | downloaded media + **phashed it** (PR #59/#60) |
| `verify_media_similarity` → `rank_source_candidates` → `render_report` | full report produced |

**Integrity check:** fed 100 noise candidates (generic-word matches), the rubric correctly
**rejected all** (confidence ≤ 0.29) → report = *"no confident source"*. The system does not
false-positive or overclaim.

## Telegram constraints discovered (real-world)

1. **Free-text global search requires Telegram Premium.** Non-premium → every free-text
   query returns `PremiumAccountRequiredError (SearchPostsRequest)`. **Hashtag** search is
   free. (The earlier design note assuming free-text was merely "metered/Stars" is outdated.)
2. **Caption-only matching.** Search matches post text/captions, not video pixels or even
   on-screen text. The pipeline OCRs on-screen text and searches it — which finds posts whose
   *captions* contain those words. A `@telegram` feature-demo clip (on-screen chat "Harriet
   Lawson…") could not be found because its source caption ("Expanded Emoji and Sticker
   Search") shares no words.
3. **Global-index lag for new/small channels.** A freshly-created public channel + post was
   **not indexed** (0 hits) hours later — Telegram doesn't promptly index tiny new channels.
4. **phash discriminates poorly on UI/screenshot content** (~0.55–0.59 similarity between
   *unrelated* phone screenshots). Real-world footage (varied scenes) discriminates far
   better; UI demos are a worst case. (The rubric still correctly rejected these.)

## Auth (for driving the pipeline via the API)

- The instance executes package functions/agents for a principal carrying the **`sinas.*:all`**
  wildcard permission. The CLI/`sinas login` API key was scoped narrower (had
  `sinas.functions.execute:all` but not the wildcard) → resource-level 403; a wildcard key (or
  the browser **JWT** session) executes fine. See `permissions-diagnosis.md` / #44.
- Telegram live search needs the three secrets (`TELEGRAM_API_ID/HASH/SESSION_STRING`) set on
  the instance **for the premium account** + `ENABLE_TELEGRAM_LIVE_SEARCH=true`. The instance
  secret must be the *premium* account's session (a non-premium session re-triggers the
  premium error even if the account elsewhere is premium).

## Implication for the product

clip2trace is a **trace-by-shared-text-token + visual-verify** tool, not a reverse-video
search engine (which Telegram's API cannot support). It reliably traces reused footage that
carries a handle/hashtag also present in the source post — the common watermarked-repost case
— and honestly reports "no confident source" otherwise. True content-based discovery would
require an independent video index, out of scope for the Telegram API.

`samples/telegram_emoji_search_demo.mp4` is the real `@telegram` clip used in this test.
