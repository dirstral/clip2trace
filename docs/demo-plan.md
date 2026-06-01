# Demo plan

## Goal
Show clip2trace tracing reused footage in an edited video to **likely Telegram
source candidates**, with confidence + evidence + caveats — **without depending
on live Telegram search**.

## Recommended demo fixture
A short edited "clip" that contains one obviously reused segment with a visible
@handle / on-screen text, plus a **cached Telegram candidate** that matches it.
- Segments: `tests/fixtures/sample_segment_metadata.json`.
- Cached candidates: `tests/fixtures/sample_telegram_results.json`.
- Regenerate/validate with `uv run python scripts/make_demo_fixture.py --check`.
Do **not** commit real videos/media (gitignored); keep fixtures as JSON.

## Controlled demo steps
1. `create_job` with `mode: "demo"`.
2. `analyze_input_video` → show timestamped candidate segments.
3. `generate_telegram_queries` → show the small ranked query plan (handle first).
4. `search_global_telegram_posts` with `cached_results` → candidate posts
   (status `ok`, source `cached`).
5. `verify_media_similarity` → perceptual-hash match (identical phash → 1.0).
6. `rank_source_candidates` → confidence + label + caveats.
7. `render_report` → final provenance report JSON.

## 3-minute script
1. (0:20) Problem: edited videos reuse footage; where did a clip come from?
2. (0:30) clip2trace pipeline diagram (architecture.md).
3. (1:30) Live run in demo mode → segments → query plan → candidate → visual
   match → report. Emphasise "likely candidate", confidence, caveats.
4. (0:40) Why it's trustworthy: visual verification (40% of score), explicit
   caveats, never claims "the original". Mention live mode + its caveats.

## 5-minute script
Add: (a) the scoring rubric walkthrough; (b) the live-vs-demo design and the
Telegram user-session / flood-wait / metered-search caveats; (c) the safety
scope (provenance only, no tactical analysis); (d) what's next (real video
decode, live search hardening, HTML report).

## Judge-facing product explanation
"clip2trace traces reused footage in an edited video back to its likely Telegram
source. It detects reused segments, searches public Telegram globally, and
**verifies candidates visually** — producing a provenance report of likely
candidates with confidence and caveats. It deliberately never claims to have
found the original."

## Fallback if live Telegram fails
Stay in `demo`/`hybrid` mode. The pipeline is identical; only the retrieval
source changes (cached/manual instead of live). The search function surfaces an
explicit `live_unavailable` status, so the demo degrades visibly and honestly.

## Known limitations to state up front
Real video decode/OCR depends on Sinas runtime libs (see runtime-diagnostics.md);
live search is flaky and metered; results are candidates for human verification,
not proof.
