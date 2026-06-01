"""extract_segment_clues — keyframes, perceptual hashes, OCR text, handles."""

from __future__ import annotations

import re

_HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")


def handler(input_data, context):
    input_data = input_data or {}
    if not input_data.get("job_id") or not input_data.get("segment_id"):
        return {"error": "job_id and segment_id are required"}

    text = input_data.get("text_hint", "") or ""
    handles = []
    for h in _HANDLE_RE.findall(text):
        if h not in handles:
            handles.append(h)

    # OCR + keyframe extraction depend on runtime libs; report availability.
    ocr_available = False
    try:
        import importlib
        importlib.import_module("cv2")
        # tesseract / pytesseract checked here in the full implementation
    except Exception:
        pass

    return {
        "segment_id": input_data.get("segment_id"),
        "keyframe_file_ids": [],
        "phashes": [],
        "ocr_text": "",
        "visible_handles": handles,
        "context_terms": [],
        "ocr_available": ocr_available,
        "implemented": False,
    }
