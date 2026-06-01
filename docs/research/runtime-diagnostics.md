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

Authoritative `clip2trace/diagnose_runtime` output **after clicking "Reload
Workers"** (console execution `7d9c2424-…`; an initial probe `9df46078-…` before
reload reported all modules `false`, so the reload step is required after install):

```json
{
  "python": "3.11.15",
  "modules": {"av": true, "cv2": false, "scenedetect": false, "imagehash": true,
              "PIL": true, "numpy": true, "telethon": true,
              "rapidfuzz": true, "dateutil": true, "requests": true},
  "tools": {"ffmpeg": false, "tesseract": false},
  "tmp_dir": "/tmp", "tmp_free_bytes": 104849408,
  "has_access_token": true, "secrets_available": true
}
```

| Capability | via-10 (measured, post-reload) | Design implication |
|---|---|---|
| Python | **3.11.15** | core lib targets >=3.10 ✓ |
| `/tmp` free | **104,849,408 B = exactly 100 MiB** | confirms the 100 MB `/tmp` cap — chunk/bound everything |
| `access_token` / `secrets` in context | **true / true** (`sharedPool` fn) | functions can call back to Sinas; Telegram fns get secrets in the trusted pool |
| numpy, Pillow, imagehash | **importable** | real perceptual hashing works on supplied/extracted frames |
| rapidfuzz | **importable** | real fuzzy text-overlap scoring (not the Jaccard fallback) |
| telethon | **importable** | live Telegram search is technically available (Ark; still needs a user session + secrets) |
| requests, dateutil | **importable** | API calls + date parsing work |
| **cv2 (opencv), scenedetect** | **NOT importable** | shot detection + keyframe *extraction* stay on the uniform-window / supplied-phash fallback. opencv-headless usually needs a system lib (e.g. `libGL`) in the worker image |
| ffmpeg / tesseract | **absent** | video decode + OCR degrade to fallbacks (regex handles, supplied phashes) |

**Key takeaways:**
- After install you **must click "Reload Workers"** for declared deps to load into
  the worker pool (first probe showed all `false`; after reload, 7/9 import).
- Sinas workers accept **pip packages only** — there is no supported way to add
  system libs (`libGL`) or binaries (`ffmpeg`/`tesseract`) to the managed image
  (docs `admin/system.md`, `functions.md`). So `cv2`/`scenedetect` (which need
  `libGL`) and `ffmpeg`/`tesseract` can't be self-served.
- **Resolution (full pipeline, pip-only):** clip2trace now decodes via **PyAV**
  (`av` — its wheel bundles ffmpeg, no system libs), detects shots via a
  **PyAV+numpy** frame-diff detector, hashes via **Pillow+imagehash+numpy**, and
  does OCR via **Claude vision** through the OpenAI adapter (no tesseract binary).
  So the entire real-video pipeline runs on the managed worker with the
  pip-installable deps that already load. opencv/scenedetect/tesseract stay as the
  *preferred* path when present.

**Confirmed on-instance (2026-06-02):** `av: true` in the worker — so PyAV decode,
the PyAV+numpy shot detector, and PIL/imagehash hashing all run on the managed
worker. The full visual pipeline is live with **zero infra changes**.

**OCR-via-Claude routing finding:** the OpenAI adapter
(`POST /adapters/openai/v1/chat/completions`) is reachable, but a **direct-LLM**
call needs the model registered on the provider — with the Claude provider's
`default_model: null`, `model:"claude-sonnet-4-6"` returns
`404 No provider found for model`. Two ways to make Claude-vision OCR resolve:
1. set the Claude provider's **default model to `claude-sonnet-4-6`** in the console
   (also closes the #1 gap), or
2. route via an **agent**: the adapter maps `model:"clip2trace/<agent>"` to that
   agent. (Until then, OCR falls back to regex-handle extraction — the strongest
   retrieval signal — so the pipeline is unaffected.)

**Follow-up (#33, OPTIONAL acceleration — operator-only):** if the Sinas/WeAreBrain
operator ever adds `libGL`+opencv/scenedetect and `ffmpeg`/`tesseract` to the
managed worker image, clip2trace uses them automatically for faster native
decode/shot-detection/OCR. **Not required** — the pip-only path above is the
supported, working route.

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
