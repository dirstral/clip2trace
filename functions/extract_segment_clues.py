"""extract_segment_clues — keyframes, perceptual hashes, OCR text, handles.

Produces the SegmentClues contract (docs/data-model.md) that feeds
generate_telegram_queries (and Ark's #13 global search):
  segment_id, keyframe_file_ids[], phashes[], ocr_text, visible_handles[],
  context_terms[], ocr_available.

Visual (#10): when a `video_path` + window is given and OpenCV is present,
extract keyframes and compute full-frame + center-crop perceptual hashes. When
phashes are supplied directly (demo/cached), pass them through.
Text (#11): regex @handle extraction, context-term derivation, OCR-availability
check. Real OCR text is supplied via `ocr_text` (the OCR upgrade is #27); we
degrade gracefully when OCR libs are absent.
"""

from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")
_HASHTAG_RE = re.compile(r"#(\w{2,64})")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "video", "live",
    "breaking", "news", "watch", "today", "footage",
}


def _ocr_available() -> bool:
    """True only if both an image backend and an OCR engine are importable."""
    try:
        import importlib
        importlib.import_module("cv2")
        importlib.import_module("pytesseract")
        return True
    except Exception:
        return False


def handler(input_data, context):
    input_data = input_data or {}
    if not input_data.get("job_id") or not input_data.get("segment_id"):
        return {"error": "job_id and segment_id are required"}

    text_hint = input_data.get("text_hint", "") or ""
    caption = input_data.get("caption", "") or ""
    ocr_text = input_data.get("ocr_text", "") or ""
    phashes = list(input_data.get("phashes") or [])
    keyframe_file_ids = list(input_data.get("keyframe_file_ids") or [])
    video_path = input_data.get("video_path")
    start, end = input_data.get("start_sec"), input_data.get("end_sec")
    diagnostics = []

    # --- #10 visual: extract keyframes -> perceptual hashes when possible. ---
    if video_path and start is not None and end is not None:
        try:
            from clip2trace.video import (extract_keyframes, phash_of_frame,
                                          center_crop_phash)
            for frame in extract_keyframes(video_path, float(start), float(end)):
                h = phash_of_frame(frame)
                if h:
                    phashes.append(h)
                ch = center_crop_phash(frame)
                if ch:
                    phashes.append(ch)
        except Exception as exc:
            diagnostics.append(f"keyframe extraction unavailable: {exc!r}")

    # --- #11 text: handles, context terms, OCR availability. ---
    blob = " ".join([text_hint, caption, ocr_text])
    try:
        from clip2trace.telegram_search import (extract_handles,
                                                derive_context_terms)
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
        "segment_id": input_data.get("segment_id"),
        "keyframe_file_ids": keyframe_file_ids,
        "phashes": phashes,
        "ocr_text": ocr_text,
        "visible_handles": handles,
        "context_terms": context_terms,
        "ocr_available": _ocr_available(),
        "diagnostics": diagnostics,
        "implemented": True,
    }
