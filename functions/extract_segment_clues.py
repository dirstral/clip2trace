"""extract_segment_clues — keyframes, perceptual hashes, OCR text, handles.

Produces the SegmentClues contract (docs/data-model.md) that feeds
generate_telegram_queries (and Ark's #13 global search):
  segment_id, keyframe_file_ids[], phashes[], ocr_text, visible_handles[],
  context_terms[], ocr_available.

Visual (#10): when a `video_path` + window is given, extract keyframes (OpenCV
or PyAV — PyAV bundles ffmpeg so it runs on the managed worker) and compute
full-frame + center-crop perceptual hashes (Pillow+imagehash, no OpenCV). When
phashes are supplied directly (demo/cached), pass them through.
Text (#11): regex @handle extraction + context-term derivation, plus on-instance
OCR (tesseract if present, else Claude vision via the platform LLM); supplied
`ocr_text` always wins. Degrades gracefully when nothing is available.

Two call shapes (the input video is staged to /tmp at most ONCE per execution):
  * single — {job_id, segment_id, start_sec, end_sec, input_video_file_id, ...}
    returns one SegmentClues dict (backward-compatible).
  * batch  — {job_id, input_video_file_id, segments:[{segment_id, start_sec,
    end_sec, ...}, ...]} returns {segments:[clues, ...], diagnostics, implemented}.
    The video is downloaded once and reused across every segment, avoiding the
    per-segment re-stage of one function call per segment.
"""

from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")
_HASHTAG_RE = re.compile(r"#(\w{2,64})")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "video",
    "live",
    "breaking",
    "news",
    "watch",
    "today",
    "footage",
}


def _clues_for_segment(seg, context, video_path, seed_diagnostics=None):
    """Compute the SegmentClues dict for one segment against a staged video_path.

    `video_path` is the already-staged local clip (shared across a batch); this
    helper never stages. `seed_diagnostics` prepends any job-level notes (e.g.
    staging messages) so single-mode output stays identical to before.
    """
    seg = seg or {}
    text_hint = seg.get("text_hint", "") or ""
    caption = seg.get("caption", "") or ""
    ocr_text = seg.get("ocr_text", "") or ""
    phashes = list(seg.get("phashes") or [])
    keyframe_file_ids = list(seg.get("keyframe_file_ids") or [])
    start, end = seg.get("start_sec"), seg.get("end_sec")
    diagnostics = list(seed_diagnostics or [])
    ocr_available = False
    frames = []

    # --- #10 visual: extract keyframes -> perceptual hashes when possible. ---
    if video_path and start is not None and end is not None:
        try:
            from clip2trace.video import (
                center_crop_phash,
                extract_keyframes,
                phash_of_frame,
            )

            frames = extract_keyframes(video_path, float(start), float(end))
            for frame in frames:
                h = phash_of_frame(frame)
                if h:
                    phashes.append(h)
                ch = center_crop_phash(frame)
                if ch:
                    phashes.append(ch)
        except Exception as exc:
            diagnostics.append(f"keyframe extraction unavailable: {exc!r}")

    # --- #11 OCR: real on-screen text (tesseract -> Claude vision). Supplied
    # ocr_text always wins; regex handles below work regardless.
    if not ocr_text and frames:
        try:
            from clip2trace.ocr import ocr_image

            got = ocr_image(frames[0], context=context)
            if got:
                ocr_text = got
                ocr_available = True
        except Exception as exc:
            diagnostics.append(f"ocr unavailable: {exc!r}")

    # --- #11 text: handles, context terms, OCR availability. ---
    if not ocr_available:
        try:
            import importlib

            importlib.import_module("pytesseract")
            ocr_available = True
        except Exception:
            ocr_available = bool(ocr_text)

    blob = " ".join([text_hint, caption, ocr_text])
    try:
        from clip2trace.telegram_search import derive_context_terms, extract_handles

        handles = extract_handles(blob)
        context_terms = derive_context_terms(blob)
    except Exception:
        handles, seen = [], set()
        for h in _HANDLE_RE.findall(blob):
            if h.lower() not in seen:
                seen.add(h.lower())
                handles.append(h)
        cleaned = _HASHTAG_RE.sub(" ", _HANDLE_RE.sub(" ", blob))
        context_terms, seen = [], set()
        for w in _WORD_RE.findall(cleaned):
            k = w.lower()
            if k in _STOPWORDS or k in seen:
                continue
            seen.add(k)
            context_terms.append(w)
            if len(context_terms) >= 8:
                break

    return {
        "segment_id": seg.get("segment_id"),
        "keyframe_file_ids": keyframe_file_ids,
        "phashes": phashes,
        "ocr_text": ocr_text,
        "visible_handles": handles,
        "context_terms": context_terms,
        "ocr_available": ocr_available,
        "diagnostics": diagnostics,
        "implemented": True,
    }


def handler(input_data, context):
    input_data = input_data or {}
    if not input_data.get("job_id"):
        return {"error": "job_id is required"}
    segments = input_data.get("segments")
    batch = isinstance(segments, list)
    if not batch and not input_data.get("segment_id"):
        return {"error": "job_id and segment_id are required"}

    # #36: stage a real uploaded video to /tmp so keyframes decode. Staged ONCE
    # per execution and reused across every segment (cache_key=job_id also lets
    # warm pooled workers reuse it across calls). The library-side cache is in
    # clip2trace.storage; the YAML copy carries a self-contained equivalent.
    staging_diags = []
    video_path = input_data.get("video_path")
    file_id = input_data.get("input_video_file_id")
    if not video_path and file_id:
        try:
            from clip2trace.storage import stage_input_file

            video_path = stage_input_file(
                file_id, context, cache_key=input_data.get("job_id")
            )
        except Exception as exc:
            staging_diags.append(f"input staging failed: {exc!r}")
        staging_diags.append(
            f"staged input video {file_id}"
            if video_path
            else f"input video {file_id} could not be staged"
        )

    if batch:
        out_segments = [
            _clues_for_segment(
                seg, context, (seg or {}).get("video_path") or video_path
            )
            for seg in segments
        ]
        return {
            "segments": out_segments,
            "diagnostics": staging_diags,
            "implemented": True,
        }

    # Single mode: fold staging notes into the one returned dict (unchanged shape).
    return _clues_for_segment(input_data, context, video_path, staging_diags)
