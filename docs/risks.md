# Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **Telegram auth/session** — `channels.searchPosts` is user-account only; session string = full account access | High | Dedicated/disposable account; store session as Sinas secret; never commit; rotate on leak; `bootstrap_telegram_session.py` is local-only |
| 2 | **Search limits / flood-waits** — `FloodWaitError`, waits up to hours | High | Catch + backoff on `.seconds`; cache queries (`query-cache`); cap attempts/job |
| 3 | **Metered free-text search** — Stars cost after free slots | Med | Prefer handle/hashtag (unmetered); `checkSearchPostsFlood` first; never spend Stars without explicit opt-in |
| 4 | **Noisy search results** — many irrelevant hits | Med | Visual verification dominates scoring (40%); reject < 0.30; small ranked query set |
| 5 | **Media fetch failures** — private/deleted/inaccessible | Med | Mark `accessible:false`, add caveat, never crash; dry-run default; bounded downloads |
| 6 | **ffmpeg/tesseract/OpenCV availability** in Sinas runtime | High | `diagnose_runtime` probe; graceful degradation (regex handles when no OCR; fixture when no decode); request approved deps. OCR backend choice + upgrade path in [OCR backends](#ocr-backends-pytesseract-vs-easyocr-vs-claude-vision-27) below (#27) |
| 7 | **Long-video runtime** vs 300 s timeout / 512 MB / 100 MB `/tmp` | High | Async execution; chunked/streaming frame processing; bound input via `MAX_VIDEO_MB`; never load whole video |
| 8 | **Privacy / legal / ToS** — automated public-data retrieval | High | Provenance scope only; public posts only; store minimal data; respect Telegram ToS; no private/restricted scraping |
| 9 | **Overclaiming** — implying "the original" | High (credibility) | Banned phrases sanitised in `report.py`; rubric labels cap at "very_strong"; tests assert no "original" in output |
| 10 | **Sinas CLI maturity / Node absent here** | Med | CLI is WIP; validate via Management API if needed; documented blockers; Node install required for CLI |
| 11 | **Inferred package YAML fields** (collections/stores/components) | Med | Marked in sinas-investigation.md; confirm with `sinas validate`; adjust on rejection |
| 12 | **Function ≠ library** (sandbox can't import `src/`) | Med | Deployable code is inline in YAML; library is reference + tests; documented in architecture.md |
| 13 | **Demo depends on live Telegram** | Med | Full demo runs on cached fixtures; `hybrid` falls back; never silently fakes live |
| 14 | **Visual embedding similarity** — CLIP/torch too heavy for the pip-only / 512 MB worker | Med | Embeddings are an optional, operator-provisioned/local-only path behind the `embeddings` extra (not in `dev`); import-guarded; **phash stays the worker default and fallback**. See section below |
| 15 | **ASR is a heavy, optional dep** (whisper/faster-whisper) — won't run on the pip-only 512 MB / 300 s worker | Med | Opt-in via the `asr` extra (`src/clip2trace/asr.py`): import-guarded + backend-injectable; absent the dep, `extract_transcript()` returns `""` and the query plan is unchanged. See "ASR / transcript extraction" below |

## Visual embedding similarity (phash vs CLIP) — evaluation & runtime impact

clip2trace's visual-similarity signal is the heaviest weight in the scoring
rubric (`visual_similarity` = 0.40). Today it is computed from **perceptual
hashes** (`phash`, via Pillow + imagehash) compared with Hamming distance. phash
is robust to mild re-encoding and small overlays but degrades on **heavy
re-encoding, scaling, cropping, letterboxing, and aspect-ratio changes** — exactly
the edits common in reused footage. Embedding models (e.g. CLIP image encoders)
compare frames in a learned semantic space and tend to stay similar under those
transforms, so they can beat phash on the hard cases.

**Decision: keep phash as the always-available default; add an OPTIONAL,
import-guarded embedding path** (`clip2trace.matching`: `cosine_similarity`,
`best_embedding_similarity`, `embed_frames`, `best_visual_similarity`,
`load_clip_embedder`). `best_visual_similarity` uses embeddings only when both
sides supply them and otherwise falls back to phash, so default behaviour is
unchanged.

| Approach | Accuracy on re-encoded / cropped footage | Deps | RAM / CPU | Runs on Sinas worker? |
|---|---|---|---|---|
| **phash** (current default) | Good for light re-encode/overlay; **weak under crop/scale/letterbox/aspect change** | Pillow + imagehash (already in baseline) | ~tens of MB, fast on CPU | **Yes** — pip-only, fits 512 MB |
| **Lightweight embeddings** (e.g. small CLIP `ViT-B-32`, MobileCLIP-style, or ONNX-exported encoder) | Markedly better under crop/scale/re-encode; some semantic false positives | torch **or** onnxruntime + model weights (≈300 MB+) | Model + activations easily exceed 512 MB at load | **No** (torch); maybe a quantised ONNX encoder, still tight |
| **Full CLIP** (`open-clip-torch` + `torch`) | Best robustness to heavy edits | torch wheel ≈ **1–2 GB**, plus weights | Peaks well over 512 MB; slow on 1 CPU | **No** |

**Why it can't run on the worker.** Sinas workers are **pip-only, 512 MB RAM,
1 CPU, no system binaries** (see CLAUDE.md "Workers are pip-only"). The `torch`
wheel alone is ~1–2 GB and the model plus inference activations blow the 512 MB
ceiling, and there is no GPU. Even a quantised ONNX encoder is risky on 512 MB /
1 CPU within the 300 s budget. So embeddings are an **optional, operator-
provisioned / local-only upgrade path**, gated behind the `embeddings`
extra (`uv pip install -e ".[embeddings]"`, deliberately **not** in `dev` so CI
never pulls torch). `load_clip_embedder` imports torch/open_clip lazily and
raises a clear `RuntimeError` when they are absent — importing
`clip2trace.matching` never pulls torch.

**Fallback guarantee.** phash remains the worker default and the fallback: with
no embedder injected, the pipeline behaves exactly as before. The cosine math and
the embedder→phash selection are pure-Python and unit-tested with **injected
fake vectors** (no heavy deps), with an `importorskip`-guarded real-model test.

## OCR backends: pytesseract vs EasyOCR vs Claude-vision (#27)

clip2trace reads on-screen text (overlays, captions, channel handles,
watermarks) from keyframes to enrich the global-search query and verification
signal. OCR is **purely additive** — the regex @handle extractor runs on the raw
caption/text-hint regardless, so a missing OCR tier never breaks the pipeline.
We evaluated three backends against the **managed Sinas worker constraints**:
pip-only image (no system binaries — no `tesseract`/`ffmpeg`/`libGL`), **512 MB
RAM**, 1 CPU, 1 GB disk, 100 MB `/tmp`, 300 s timeout.

| Backend | Accuracy on overlays/handles | Dependency weight | RAM at inference | Runs on the pip-only 512 MB worker? | Per-frame cost |
|---|---|---|---|---|---|
| **pytesseract** | Fair on clean horizontal captions; weak on stylised/low-contrast overlays; no built-in language autodetect | Tiny Python wheel **but requires the `tesseract` system binary** (apt/brew) + language `.traineddata` | ~50–150 MB | **No** — the worker has no system binaries and cannot install them (docs `admin/system.md`) | ~50–300 ms (CPU) |
| **EasyOCR** | Good — neural detector+recogniser, robust to stylised/rotated text and many scripts | **Heavy**: pulls in **torch** (~hundreds of MB of wheels) + ~64 MB detection/recognition model weights downloaded on first `Reader()` | ~700 MB–1 GB+ resident with torch + models loaded | **No** — torch + models exceed 512 MB RAM (and first-run weight download is disallowed on a sandboxed worker) | ~0.5–3 s/frame on CPU (first call also pays model load) |
| **Claude vision** (Sinas OpenAI-compatible adapter) | Strong — best on stylised overlays, multi-language, and contextual handles; understands layout | **Zero extra deps** — only `requests` + the function's `access_token`; inference is remote | Negligible local RAM (just PNG-encode the frame) | **Yes** — the on-worker default | One LLM call/frame: network + provider latency (~1–3 s) and token/$ cost; we OCR only the **first keyframe per segment** to bound spend |

**Decision.** **Claude-vision is the on-worker default** — it is the only option
that satisfies the pip-only / 512 MB constraints with zero extra dependencies,
and it has the best accuracy on the stylised, multi-language overlays typical of
the target footage. Its cost (one adapter call per segment keyframe, bounded to
the first frame) is acceptable and already in the runtime budget.

**Upgrade path (operator-provisioned, local only).** For high-volume or
offline/local runs where avoiding per-frame LLM cost matters, two faster local
tiers are tried **first** when their dependency happens to be present, then we
fall through to Claude-vision:

```
pytesseract (needs tesseract binary) → easyocr (needs `pip install -e ".[ocr]"`) → claude-vision → ""
```

Both local tiers are **import-guarded** in `src/clip2trace/ocr.py`
(`tesseract_ocr`, `easyocr_ocr`) and selected by `select_backend`/`ocr_image`;
if the optional package is absent the tier is silently skipped and behaviour is
unchanged. **EasyOCR is *not* installed on the worker and is deliberately kept
out of the `dev` extra** (CI installs `dev`); it lives in its own
`[project.optional-dependencies] ocr = ["easyocr"]` extra so it never inflates CI
or the deployable function image. Because EasyOCR cannot run on the worker, the
**deployable inline function code is unchanged** — this is a library-level
upgrade path plus documentation.

## ASR / transcript extraction (optional, operator-provisioned/local)

Spoken context improves query planning: a transcript yields extra **context**
terms (and any spoken @handles / #hashtags) that fold into the same query
families `telegram_search.generate_queries` already builds. ASR is **not part of
the default pipeline** — it is an opt-in upgrade path.

**Why it can't run on the managed Sinas worker.** ASR models are heavy:

| Backend / model | On-disk model | Extra deps | Approx. peak RAM | Speed (CPU) |
|---|---|---|---|---|
| faster-whisper `tiny` (int8) | ~75 MB | ctranslate2 + onnxruntime (no torch) | ~0.5–1 GB | ~1–3× realtime |
| faster-whisper `base` | ~145 MB | ctranslate2 + onnxruntime (no torch) | ~1 GB+ | slower than realtime |
| openai-whisper `base` | ~140 MB | **torch** (~2 GB wheel) + ffmpeg binary | ~2 GB+ | well below realtime on CPU |

The Sinas worker is **pip-only, 512 MB RAM, 1 CPU, 100 MB `/tmp`, 300 s
timeout** with no system binaries. Even the smallest model exceeds the RAM
budget once the model + native runtime are loaded — for faster-whisper that's
CTranslate2/onnxruntime plus the model weights (no torch); openai-whisper is
heavier still and *additionally* needs torch and an `ffmpeg` binary the image
can't provide. CPU-only transcription of a clip also blows the 300 s timeout. So
ASR is intentionally **excluded from the worker** and provisioned only locally /
by an operator on a beefier host.

**Graceful degradation (no behaviour change without a transcript).**
`src/clip2trace/asr.py` import-guards the backend and keeps it injectable:

- the `asr` extra (`faster-whisper`) is **separate from `dev`** so CI stays
  light and green;
- with no backend installed, `extract_transcript()` returns `""` (and a failing
  backend also degrades to `""` — it never raises);
- `generate_queries(clues, transcript="")` is byte-for-byte identical to the
  clues-only call, so the default pipeline is unaffected.

Tests cover the no-dep fallback and the transcript→query-term path using a fake
injected transcriber, so no heavy model is needed in CI.

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
