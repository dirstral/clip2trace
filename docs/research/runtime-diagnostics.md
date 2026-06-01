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

## Sinas runtime — PROBED on via-10 (2026-06-02, shared pool)

Real `clip2trace/diagnose_runtime` output from the console (execution
`9df46078-…`):

```json
{
  "python": "3.11.15",
  "modules": {"cv2": false, "scenedetect": false, "imagehash": false,
              "PIL": false, "numpy": false, "telethon": false,
              "rapidfuzz": false, "dateutil": false, "requests": false},
  "tools": {"ffmpeg": false, "tesseract": false},
  "tmp_dir": "/tmp", "tmp_free_bytes": 104849408,
  "has_access_token": true, "secrets_available": true
}
```

| Capability | Sinas runtime (via-10, measured) | Design implication |
|---|---|---|
| Python | **3.11.15** | core lib targets >=3.10 ✓ |
| `/tmp` free | **104,849,408 B = exactly 100 MiB** | confirms the 100 MB `/tmp` cap — chunk/bound everything |
| `access_token` in context | **true** | functions can call back to the Sinas API |
| `secrets` in context | **true** (this is a `sharedPool` fn) | Telegram functions correctly get secrets in the trusted pool |
| ffmpeg / tesseract | **absent** | OCR + decode degrade to regex-handle / supplied-phash fallbacks |
| numpy/pillow/imagehash/rapidfuzz/requests/dateutil | **not importable in the worker** | declared in `spec.dependencies` + shown under console "Installed Dependencies (9)", but the worker pool had not loaded them at probe time → click **"Reload Workers"** on the Functions page and re-probe |
| cv2 / scenedetect / telethon | **absent** | heavy deps; may need a larger worker image. Pipeline runs in fallback mode regardless |

**Key takeaway:** the install registered all 9 dependencies, but the **function
workers report none importable** until "Reload Workers" is clicked (follow-up).
Because every clip2trace step has a dependency-free fallback (see the matrix
below), the pipeline still executes and returns structured JSON in demo mode with
zero deps — real perceptual hashing/scoring activates once the light deps load.

**Follow-ups (#3):** (1) click "Reload Workers" and re-probe to confirm the light
deps load; (2) request `ffmpeg`/`tesseract`/a heavier worker image if real video
decode/OCR is needed on-instance (otherwise fallbacks cover the demo).

Documented container ceilings (design against these): **512 MB RAM, 1 GB disk,
100 MB `/tmp` (confirmed), 300 s timeout.**

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
