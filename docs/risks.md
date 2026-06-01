# Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **Telegram auth/session** — `channels.searchPosts` is user-account only; session string = full account access | High | Dedicated/disposable account; store session as Sinas secret; never commit; rotate on leak; `bootstrap_telegram_session.py` is local-only |
| 2 | **Search limits / flood-waits** — `FloodWaitError`, waits up to hours | High | Catch + backoff on `.seconds`; cache queries (`query-cache`); cap attempts/job |
| 3 | **Metered free-text search** — Stars cost after free slots | Med | Prefer handle/hashtag (unmetered); `checkSearchPostsFlood` first; never spend Stars without explicit opt-in |
| 4 | **Noisy search results** — many irrelevant hits | Med | Visual verification dominates scoring (40%); reject < 0.30; small ranked query set |
| 5 | **Media fetch failures** — private/deleted/inaccessible | Med | Mark `accessible:false`, add caveat, never crash; dry-run default; bounded downloads |
| 6 | **ffmpeg/tesseract/OpenCV availability** in Sinas runtime | High | `diagnose_runtime` probe; graceful degradation (regex handles when no OCR; fixture when no decode); request approved deps |
| 7 | **Long-video runtime** vs 300 s timeout / 512 MB / 100 MB `/tmp` | High | Async execution; chunked/streaming frame processing; bound input via `MAX_VIDEO_MB`; never load whole video |
| 8 | **Privacy / legal / ToS** — automated public-data retrieval | High | Provenance scope only; public posts only; store minimal data; respect Telegram ToS; no private/restricted scraping |
| 9 | **Overclaiming** — implying "the original" | High (credibility) | Banned phrases sanitised in `report.py`; rubric labels cap at "very_strong"; tests assert no "original" in output |
| 10 | **Sinas CLI maturity / Node absent here** | Med | CLI is WIP; validate via Management API if needed; documented blockers; Node install required for CLI |
| 11 | **Inferred package YAML fields** (collections/stores/components) | Med | Marked in sinas-investigation.md; confirm with `sinas validate`; adjust on rejection |
| 12 | **Function ≠ library** (sandbox can't import `src/`) | Med | Deployable code is inline in YAML; library is reference + tests; documented in architecture.md |
| 13 | **Demo depends on live Telegram** | Med | Full demo runs on cached fixtures; `hybrid` falls back; never silently fakes live |

## Safety / compliance notes
- Product wording is **provenance and source tracing only**. No tactical
  analysis, target identification, military advice, or conflict geolocation.
- Use "edited video", "reused footage segment", "candidate source segment",
  "Telegram source candidate", "provenance report". Avoid "broadcast" /
  "compilation" as the product category.
- **Data retention / media storage**: downloaded media is bounded, optional, and
  gitignored; prefer metadata-only (dry-run). Do not add private datasets or
  downloaded Telegram media to git.
- **Telegram account/session risk**: see rows 1–3.
