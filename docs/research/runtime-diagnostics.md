# Research log: runtime diagnostics

The `clip2trace/diagnose_runtime` function (and `functions/diagnose_runtime.py`)
probes the execution environment. It must be a **sharedPool/trusted** function
for `context["secrets"]` to be present.

## How to run

On the Sinas instance (the result that actually matters):

```bash
# sync execution via the runtime API
curl -s -X POST "$SINAS_BASE_URL/functions/clip2trace/diagnose_runtime/execute" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"input": {}}'
```

Locally (dev sanity check):

```bash
uv run python -c "import sys; sys.path[:0]=['functions','src']; \
import diagnose_runtime, json; print(json.dumps(diagnose_runtime.handler({}, {}), indent=2))"
```

## Local dev environment (uv, 2026-06-01) — NOT the Sinas runtime

```json
{
  "python": "3.14.5",
  "modules": {"cv2": false, "scenedetect": false, "imagehash": true,
              "PIL": true, "numpy": true, "telethon": false,
              "rapidfuzz": true, "dateutil": true, "requests": true},
  "tools": {"ffmpeg": false, "tesseract": false},
  "tmp_free_bytes": 52157116416,
  "has_access_token": false, "secrets_available": false
}
```

Notes on the local box (developer machine):
- **ffmpeg: NOT installed**, **tesseract: NOT installed**, **OpenCV: NOT installed**.
  `imagehash`, `Pillow`, `numpy`, `rapidfuzz` resolve (pulled by uv from project
  deps). `telethon` and `opencv`/`scenedetect` are optional extras (not installed).
- Node/npm are also absent → `@sinas/cli` cannot run here.

## Sinas runtime — PENDING (blocked on instance access)

The values that drive design decisions must come from running `diagnose_runtime`
**on the instance**. Until then, design against the documented container limits:

| Capability | Local dev | Sinas runtime (to confirm) | Design implication |
|---|---|---|---|
| Python | 3.14.5 | confirm via probe | core lib targets >=3.10 |
| ffmpeg | absent | likely needed for decode | if absent, request as approved dep / system tool |
| tesseract | absent | unknown | OCR optional; regex-handle fallback always works |
| OpenCV | absent | needs `opencv-python-headless` (approved dep) | keyframe extraction degrades gracefully |
| imagehash/Pillow | present | needs approved dep | perceptual hashing |
| Telethon | absent | needs approved dep + sharedPool | live search only |
| `/tmp` free | ~52 GB | **100 MB tmpfs** | chunk video; bound downloads |
| disk | ample | **1 GB** | never store full corpora in-function |
| RAM | ample | **512 MB** | process frames streaming, not whole video |
| timeout | n/a | **300 s** | long videos → async + chunking |
| `access_token` | n/a | present in context | use for API calls back to Sinas |
| `secrets` | n/a | **shared-pool only** | Telegram functions must be `sharedPool: true` |

## Graceful-degradation matrix (what clip2trace does when a capability is missing)

clip2trace is built to **degrade, never crash**, when an optional runtime library
or tool is absent. Every heavy dependency is imported lazily, and each pipeline
step has a documented fallback. This is what makes the whole pipeline testable and
demoable offline (see the test suite + `docs/demo-plan.md`).

| Capability | Used by | When absent → fallback | Where |
|---|---|---|---|
| `scenedetect` | shot detection | uniform fixed-window segmentation (needs `duration_sec`), else deterministic demo segments | `detect_shots`/`uniform_windows` in `src/clip2trace/video.py`; `functions/detect_source_segments.py` |
| `opencv` (`cv2`) | keyframe extraction | skip extraction; use phashes supplied in the request (demo/cached) | `extract_keyframes` in `video.py`; `functions/extract_segment_clues.py` |
| `imagehash`/`Pillow` | perceptual hashing | `phash_of_frame`/`center_crop_phash` return `None`; supplied phashes still used | `video.py` |
| `tesseract`/`pytesseract` | OCR text | `ocr_available=false`; regex `@handle` + context-term extraction from supplied text still run | `functions/extract_segment_clues.py` |
| `rapidfuzz` | text overlap score | Jaccard token-overlap fallback | `text_overlap_score` in `src/clip2trace/matching.py` |
| `telethon` + secrets | live Telegram search | explicit `live_unavailable` status (never a silent fake); demo/cached/manual paths still work | `functions/search_global_telegram_posts.py` (Ark) |
| `ffmpeg` | video decode (under opencv) | bounded by the above video fallbacks; flagged here for dep-approval | runtime tool |

The `diagnose_runtime` function reports exactly which of these are importable on
the instance, so the above fallbacks can be predicted before a run.

## Blockers / follow-ups
- Run `diagnose_runtime` on the instance and paste real output here.
- If ffmpeg/OpenCV/tesseract/Telethon are missing or unapproved, file the
  dependency-approval requests (issue "Investigate Sinas function runtime
  capabilities").
- 100 MB `/tmp` + 512 MB RAM + 300 s are the binding constraints for the video
  pipeline — see docs/risks.md.
