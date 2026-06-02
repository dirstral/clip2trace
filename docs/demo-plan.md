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
3. `extract_segment_clues` → handles / OCR text / context terms / phashes.
4. `generate_telegram_queries` → show the small ranked query plan (handle first).
5. `search_global_telegram_posts` with `cached_results` → candidate posts
   (status `ok`, source `cached`).
6. `fetch_telegram_candidate_media` → normalised candidate metadata (dry-run).
7. `verify_media_similarity` → perceptual-hash match (identical phash → 1.0).
8. `rank_source_candidates` → confidence + label + caveats.
9. `render_report` (`output_format: "html"` for the readable report) → final
   provenance report.

## Run it offline right now (no Sinas instance, no Telegram)
The whole chain above is exercised end-to-end by the test suite on the demo
fixtures — this is the safest thing to run live in front of judges:

```bash
uv pip install -e ".[dev,video]"
uv run --with pytest pytest -q tests/test_pipeline_e2e.py -v   # full chain on fixtures
uv run python scripts/make_demo_fixture.py --check            # validate fixtures
```

Per-step inputs/outputs (handlers in `functions/`, fixtures in `tests/fixtures/`):

| Step | Key input | Key output to point at |
|---|---|---|
| create_job | `{mode: demo}` | `status: created`, `progress: 0.0`, `job_id` |
| detect_source_segments | `{job_id}` | `segments[]` with `start_sec/end_sec/source_likelihood` |
| extract_segment_clues | segment + `text_hint`/`ocr_text` | `visible_handles`, `context_terms`, `phashes`, `ocr_available` |
| generate_telegram_queries | clues | `queries[]` — `query_type: handle` first (priority 1) |
| search_global_telegram_posts | `{cached_results}` | `status: ok`, `source: cached`, `candidates[]` |
| verify_media_similarity | seg vs candidate phashes | `visual_score: 1.0` on the identical demo phash |
| rank_source_candidates | candidate + `verification` | `confidence`, `confidence_label`, `caveats`, `recommended_next_steps` |
| render_report | segments + ranked | `report_json` (+ `report_html` when `output_format` html/both) |

On a Sinas instance the same steps run via the runtime API, e.g.:
```bash
curl -s -X POST "$SINAS_BASE_URL/functions/clip2trace/create_job/execute" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"input": {"mode": "demo"}}'
# long steps (analyze_input_video): use /execute/async then poll /executions/{id}
```

## Annotated highlight (what to say while it runs)
- The **strong** candidate (`cand_demo_1`) has an identical perceptual hash and a
  matching `@handle` → `very_strong`/`strong`. Stress: *likely candidate, not the
  original.*
- The **weak** candidate (`cand_demo_2`, unrelated phash) is **rejected** — show
  the score dropping below 0.30. This proves the rubric discriminates.
- The **repost** candidate (`cand_demo_3`, `is_forward: true`, inaccessible)
  illustrates the standing "may itself be a repost" caveat.

## Troubleshooting (live)
- `search_global_telegram_posts` returns `live_unavailable` → Telegram secrets /
  user-session missing or function not `sharedPool`. Fall back to demo/cached;
  this is expected and honest, not a bug.
- `verify_media_similarity` shows `visual_score: 0.0` → no overlapping phashes
  (opencv/imagehash missing on the runtime, or candidate media not fetched). Check
  `diagnose_runtime`; supply phashes via the cached fixture for the demo.
- Empty `segments` → no `video_path`/`duration_sec` and not demo mode; pass
  `mode: demo` or a `duration_sec` for the uniform-window fallback.

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
scope (provenance only, no tactical analysis); (d) the readable **HTML report**
(`render_report` with `output_format: html`); (e) what's next (real video decode
on the instance, live search hardening).

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
