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

**Claude-vision OCR — WORKING (2026-06-02).** Resolved end-to-end:
- The Claude provider's **default model was set to `claude-sonnet-4-6`** in the
  console (was `null`), so the adapter resolves the model (`200`).
- The Sinas OpenAI adapter (`POST /adapters/openai/v1/chat/completions`) routes the
  model by name but expects **Anthropic-native content blocks** for images: the
  OpenAI `image_url` shape returns `500`, while
  `{"type":"image","source":{"type":"base64","media_type":"image/png","data":…}}`
  returns `200`. `clip2trace.ocr` sends that block.
- Verified live: `ocr_image(frame, base_url, token)` on a rendered frame returned
  `"LIVE FROM DEMO @demo_channel"`. OCR still falls back to regex `@handle`
  extraction if the LLM is unavailable.
- Routing note: the adapter maps `model:"namespace/name"` to an **agent** instead
  of a direct-LLM call.

**Function runtime address — CORRECTED (functions CAN reach the runtime).** An
earlier reading of this probe concluded a function had "no runtime address": it
dumped `env_keys` + `context_keys` and found `context["access_token"]` but **no base
URL** (`env_keys` = HOME, PATH, WORKER_ID, WORKER_MODE, SINAS_CONTAINER_MODE, … ;
`context_keys` = access_token, execution_id, secrets, user_id, …). That conclusion
was **incomplete**: the base URL is **not delivered via env/context** — it is a
**hardcoded SDK default**, which is exactly why the key-dump never showed it. The
authoritative `sinas-package-author` skill (`.claude/skills/sinas-package-author/SKILL.md:327-337`)
documents that the **`sinas==0.1.7` SDK is preinstalled** in the worker and a function
calls back with:

```python
from sinas import SinasClient
client = SinasClient(base_url="http://host.docker.internal:8000",
                     token=context["access_token"])
```

This is corroborated on-instance: Claude-vision OCR already works from inside
`extract_segment_clues` by POSTing to `{base}/adapters/openai/v1/chat/completions`
(see the OCR section above). So a function **can** `GET /files/...` (input delivery,
#36) and could `POST /states` if needed.

> **Correction (2026-06-02, measured):** `diagnose_runtime` now probes `"sinas"`
> and reports **`"sinas": false`** on via-10 — the `sinas` SDK is **NOT** preinstalled
> in the worker, contrary to the skill note above. This does **not** change the
> conclusion: functions reach the runtime with **`requests`** (which *is* importable)
> against the hardcoded default base `http://host.docker.internal:8000`, using their
> per-execution `access_token`. Input delivery (#36) was confirmed working this way
> (`_stage_input_video` → `requests.get(.../files/...)`), so the `from sinas import
> SinasClient` snippet above is illustrative only — the shipped code does not depend
> on it.

**Persistence stays agent-layer — by design choice, not impossibility.** The package
keeps **functions as pure transforms** that return data, while the orchestrating
agents (`coordinator`/`report-writer`, which carry `enabledStores` /
`enabledCollections` readwrite) persist it (job lifecycle → `clip2trace/jobs`,
segments → `clip2trace/segments`, report → `clip2trace/reports`). This keeps
functions stateless/testable; we did **not** re-architect it after the correction.
The one place the function *does* call the runtime is **input delivery** (#36):
fetching the uploaded `input-videos` file to `/tmp` so PyAV can decode it. (Keyframe
*image* files still aren't stored — functions return perceptual hashes, which is what
visual verification needs.) See the agent prompts in `sinas-package.yaml` + `agents/*.md`.

**Follow-up (#33, OPTIONAL acceleration — operator-only):** if the Sinas/WeAreBrain
operator ever adds `libGL`+opencv/scenedetect and `ffmpeg`/`tesseract` to the
managed worker image, clip2trace uses them automatically for faster native
decode/shot-detection/OCR. **Not required** — the pip-only path above is the
supported, working route.

Documented container ceilings (design against these): **512 MB RAM, 1 GB disk,
100 MB `/tmp` (confirmed), 300 s timeout.**

## Input delivery (#36) — files API on via-10 (probed 2026-06-02)

How a function gets an uploaded `input-videos` file, confirmed against
`GET {SINAS_BASE_URL}/openapi.json` on via-10:

- The files API is **name-addressed**, not id-addressed:
  `GET /files/{namespace}/{collection}/{filename}`. So `input_video_file_id` is the
  uploaded file's **name** within `clip2trace/input-videos`.
- **Download returns a JSON envelope, not raw bytes** (schema `FileDownloadResponse`):
  `{ content_base64, content_type, file_metadata, version }`. The staging helper
  (`stage_input_file` in `src/clip2trace/storage.py`; inline `_stage_input_video` in
  the three video functions) base64-decodes `content_base64` to `/tmp`, bounded to
  ~90 MB (100 MB `/tmp` cap). (An earlier draft streamed raw bytes — wrong; corrected
  after this probe.)
- Upload (console/dashboard) is `POST /files/{ns}/{collection}` with
  `{ name, content_base64, content_type, visibility, file_metadata }`.
- A larger-file alternative exists for later (#20 scale-up): `POST
  /files/{ns}/{collection}/{filename}/url` mints a temp URL (served via
  `/files/serve/{token}`) for streaming, avoiding loading base64 into RAM.

**Auth / RBAC caveat (must run from the console).** With the admin token, both
`GET /files/clip2trace/input-videos` (list) and
`POST /functions/clip2trace/diagnose_runtime/execute` return **403 Not authorized** —
the same resource-level 403 noted in `sinas-investigation.md`. So functions/agents
and file ops must be exercised from the **console UI (full user session)**, not the
admin/scoped API token. The function's own per-execution `access_token` inherits the
invoking user's scope; if it 403s on the files download, grant a
`clip2trace.input-videos.read` permission in `sinas-config.yaml` to the user's role.

**Deploy status (2026-06-02).** The #36 + #25 + #3 package update **validated**
(`POST /api/v1/packages/preview` → `success: true`; 1 function created
`cluster_segments`, 6 updated, 2 agents updated — no invented fields) and was
**installed** (`POST /api/v1/packages/install` → 200). Workers must be **reloaded in
the console** (no reload API endpoint) before the new code loads.

### On-instance hybrid capture — DONE (console UI, full user session, 2026-06-02)

Run end-to-end from the console (full Admins session; the only path that executes
package resources — see #44). Uploaded `Israel captures castle in Lebanon
[CtaT27mc3bU].mkv` (2.5 MB, `video/matroska`, private) to `clip2trace/input-videos`.

**1. `diagnose_runtime` (post-install, exec `6a08ac4c-…`)** — the PyAV+hash path is
live; note `cv2`/`scenedetect`/`ffmpeg`/`tesseract`/`sinas` all `false`:

```json
{"python": "3.11.15",
 "modules": {"av": true, "cv2": false, "scenedetect": false, "imagehash": true,
             "PIL": true, "numpy": true, "telethon": true, "rapidfuzz": true,
             "dateutil": true, "requests": true, "sinas": false},
 "tools": {"ffmpeg": false, "tesseract": false},
 "tmp_dir": "/tmp", "tmp_free_bytes": 104845312,
 "has_access_token": true, "secrets_available": true,
 "context_keys": ["access_token","chat_id","execution_id","secrets",
                  "trigger_type","user_email","user_id"]}
```

**2. `coordinator` agent, HYBRID mode, `input_video_file_id` = the uploaded name**
→ `analyze_input_video` (job `job_09d6af2d-…`). Real input delivery + real PyAV shot
detection both succeed:

```json
{"status": "analyzed", "mode": "hybrid", "method": "shot_detection_pyav",
 "segments": [
   {"segment_id": "seg_001", "start_sec": 0.0,   "end_sec": 5.81},
   {"segment_id": "seg_002", "start_sec": 5.81,  "end_sec": 11.98},
   {"segment_id": "seg_003", "start_sec": 11.98, "end_sec": 14.52},
   {"segment_id": "seg_004", "start_sec": 14.52, "end_sec": 18.95}],
 "diagnostics": [
   "staged input video Israel captures castle in Lebanon [CtaT27mc3bU].mkv",
   "shot detection unavailable: ImportError('libxcb.so.1: cannot open shared object file: No such file or directory')"],
 "next_step": "extract_segment_clues"}
```

- `diagnostics[0]` = **input delivery works** (#36): the worker downloaded + staged
  the real upload to `/tmp` via `requests` (URL-encoded name; no `sinas` SDK).
- `method: "shot_detection_pyav"` with **4 real, irregular scene cuts** — these match
  the local `scripts/export_segments.py` boundaries for this clip exactly
  (`0.0 / 5.8 / 12.0 / 14.5 / 18.9 s`), i.e. a genuine real decode, not the demo
  fixtures.
- `diagnostics[1]` `libxcb.so.1` is **benign**: it's only the optional first-choice
  `scenedetect`/opencv path failing (those need `libGL`/`libxcb`, absent by design —
  cf. #33). The PyAV+numpy detector is the supported route and it succeeded.

**3. Real perceptual hashes + OCR — `extract_segment_clues` (run directly, execs
`ea0377fd-…` seg_001, `0bf9ca42-…` seg_003).** Real, content-distinct phashes and
real on-screen text (Claude vision, no tesseract):

```json
// seg_001 (0.0–5.81s)
{"segment_id": "seg_001",
 "phashes": ["9c93252d74d38bca","85d4d24b2b3e28cf","9c93252d3cd38bca",
             "c5d4d2492b3e28cf","9c93252d74d38bca","85d4d24b2b3e28cf"],
 "ocr_text": "DEMOCRACY NOW!  Israeli troops captured a Crusades-era castle in southern Lebanon,",
 "ocr_available": true,
 "diagnostics": ["staged input video Israel captures castle in Lebanon [CtaT27mc3bU].mkv"]}

// seg_003 (11.98–14.52s)
{"segment_id": "seg_003",
 "phashes": ["aa293587d4e5d368","b1173b140fa761ba","aaae1584b519b95e",
             "ac445ae565d556ca","aa3d25c5723d932a","cb152ad46bd546e8"],
 "ocr_text": "DEMOCRACY NOW!  It was previously held by Israeli forces during their 1982-2000 occupation of southern Lebanon",
 "ocr_available": true,
 "diagnostics": ["staged input video Israel captures castle in Lebanon [CtaT27mc3bU].mkv"]}
```

6 phashes per segment = 3 keyframes × (full + 0.6 center-crop), via PyAV keyframe
extraction + `imagehash`. seg_001 vs seg_003 differ entirely → real, not the demo
`c3e1…`/`5a5a…`.

**Wiring bug found + fixed (PR #46).** The first coordinator run produced **empty
phashes** (so `cluster_segments` returned 4 singleton clusters) because
`extract_segment_clues` was **not** in the coordinator's `enabledFunctions` (it lived
only on `source-segment-analyst`), and the coordinator prompt wrongly assumed
`analyze_input_video` returns phashes. PR #46 adds the function to the coordinator and
updates its prompt/workflow to call it per segment (between `analyze_input_video` and
`cluster_segments`); the direct runs above prove the phash path works on-instance.

**#44 status (unchanged).** This whole capture was driven from the **console browser
session** — package functions/agents executed fine there. The **API-token** path is
still blocked (resource-level 403 on package-installed resources); only
`/api/v1/packages/{preview,install}` accept the admin token. So an automated
(SDK/dashboard/CI) demo remains blocked pending the operator fix in #44.

**Remaining hand-off (1 step).** After PR #46 merges and the package is reinstalled
(`scripts/sinas_install.py`), a **single** coordinator hybrid pass should yield real
phashes + clusters without the manual `extract_segment_clues` calls — re-run the
console chat once and paste that one-pass output here to fully close the loop.

## Shot detection — color-histogram metric (2026-06-02)

The PyAV+numpy shot detector (`_detect_shots_av` + the inline copies in
`analyze_input_video`/`detect_source_segments`) scores each frame transition by the
**mean per-channel color-histogram total-variation distance**, not a grayscale
pixel-mean difference. Reason, found by exporting segment clips from real
`samples/*.mkv` compilations: a grayscale mean-diff (fixed 0.30 threshold)
**under-segmented** overlay-heavy / similar-luma news clips — two samples collapsed
to a single segment because their peak grayscale diff was only 0.25 / 0.29. A
persistent on-screen overlay (logo/border/caption) is constant frame-to-frame and
*dilutes* a global pixel mean, whereas it cancels in the histogram difference; color
also separates scenes that share brightness. After the change (threshold 0.25,
local-max + 1.5 s min-gap), the five samples segment 4 / 6 / 14 / 17 / 19 (was
4 / **1** / **1** / 8 / 6) — verified by eye that the new cuts land on real scene
changes. Still numpy-only (no opencv on the worker). Inspect with
`scripts/export_segments.py --all`.

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

## Status / follow-ups

- ✅ `diagnose_runtime` **has been run on via-10** and the real post-reload output is
  captured above (2026-06-02) — this section no longer has a pending "paste output"
  TODO. #3's acceptance (ffmpeg/tesseract/OpenCV/Telethon/disk/timeout/secrets
  documented) is met by the capability table above.
- Dependency-approval follow-ups were filed: **#33** (operator-only system libs —
  `libGL`/opencv/scenedetect, `ffmpeg`/`tesseract`; optional acceleration, not
  required) and **#36** (uploaded-video → worker input delivery, wired via
  `requests` against the `host.docker.internal:8000` files API — **no** `sinas` SDK;
  see the corrected runtime-address note above).
- ✅ **On-instance hybrid run captured (2026-06-02)** — see "On-instance hybrid
  capture — DONE" above. Real input delivery + `method: "shot_detection_pyav"` + real
  per-segment phashes + Claude-vision OCR all verified on via-10. Found & fixed a
  coordinator wiring bug (`extract_segment_clues` not enabled on the coordinator →
  empty phashes) in **PR #46**. The module probe shows **`"sinas": false`** (functions
  use `requests`, not the SDK). Remaining: one clean single-pass coordinator hybrid
  run after PR #46 is reinstalled.
- 100 MB `/tmp` + 512 MB RAM + 300 s remain the binding constraints for the video
  pipeline — see docs/risks.md.
