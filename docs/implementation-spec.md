# Implementation spec

## MVP scope
- Accept an input video (file id in a Sinas collection) and a mode
  (demo/live/hybrid).
- Detect candidate reused-footage segments (shot detection or fixture).
- Extract clues: keyframes + perceptual hashes, OCR text (if available),
  visible @handles (regex), context terms.
- Generate a small ranked Telegram query set.
- Retrieve candidate posts (demo/cached/manual; live optional via Telethon).
- Verify candidate media (perceptual-hash distance + text overlap + temporal).
- Rank with the evidence rubric; produce a JSON provenance report with caveats.
- A dashboard skeleton + an end-to-end **demo path** that needs no live Telegram.

## Non-goals (MVP)
- Claiming "the original" source (forbidden language).
- Tactical analysis, target identification, military advice, geolocation.
- Heavy ML (CLIP/embeddings/Whisper/EasyOCR/FAISS/torch) — stretch only.
- Private/deleted Telegram content.
- HTML report (JSON first; HTML is stretch).

## Modules (`src/clip2trace/`)
| Module | Responsibility | Tested |
|---|---|---|
| `schemas.py` | pydantic data models (Job, SourceSegment, …) | indirectly |
| `scoring.py` | rubric weights, confidence labels, `score_candidate` | `test_scoring.py` |
| `matching.py` | hamming/phash similarity, text overlap, temporal | `test_matching.py` |
| `telegram_search.py` | `generate_queries`, demo/live `search_posts` | `test_query_generation.py` |
| `video.py` | shot detection, keyframe extraction, phash (lazy deps) | smoke |
| `telegram_media.py` | candidate metadata normalise + bounded fetch | smoke |
| `storage.py` | Sinas state client + in-memory fallback | — |
| `report.py` | build provenance report JSON, language sanitiser | — |

## Function contracts
See [api-contracts.md](api-contracts.md) for full JSON in/out. Every function:
validates required keys, returns structured JSON, never crashes on missing
optional fields, returns `{"error": "..."}` on bad input, and avoids large
downloads unless explicitly invoked.

## Agent contracts
See `agents/*.md`. coordinator orchestrates; source-segment-analyst classifies
segments; telegram-query-planner builds queries; evidence-ranker scores;
report-writer writes the report. All use cautious provenance language and the
shared skills.

## Dependency list
Baseline (approved deps): `numpy, pillow, imagehash, rapidfuzz, python-dateutil,
requests` (+ `pydantic` for the local library/tests). Optional/heavier (need
admin approval + larger containers): `opencv-python-headless, scenedetect,
telethon`. Excluded until justified (stretch issues): torch, CLIP, FAISS,
Whisper, EasyOCR.

## Known constraints
- Function container: 512 MB RAM, 1 CPU, 1 GB disk, 100 MB `/tmp`, 300 s timeout.
- `context["secrets"]` only in `sharedPool` functions.
- Live Telegram global search needs a **user account** session; free-text is
  metered; flood-waits happen.
- Sinas function bodies cannot import `src/clip2trace` (see architecture.md).

## Demo mode
`mode=demo` (default): full pipeline using `cached_results`/fixtures, no live
Telegram. `hybrid`: try live, fall back to cached. `live`: live only (flaky).
