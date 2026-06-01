#!/usr/bin/env python3
"""Generate / validate the controlled demo fixture for clip2trace.

The demo fixture lets the whole pipeline run with NO live Telegram access:
fixed segments + cached Telegram candidate results. This keeps the hackathon
demo deterministic. See docs/demo-plan.md.

Usage:
    uv run python scripts/make_demo_fixture.py            # print fixtures
    uv run python scripts/make_demo_fixture.py --check     # validate shapes
"""

from __future__ import annotations

import json
import os
import sys

FIX_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")

SEGMENTS = [
    {"segment_id": "seg_001", "start_sec": 12.0, "end_sec": 24.5,
     "source_likelihood": 0.81, "reason": "candidate reused footage",
     "clues": {"visible_handles": ["@demo_channel"],
               "ocr_text": "LIVE FROM DEMО", "context_terms": ["demo", "street"]}},
]

CACHED_TELEGRAM_RESULTS = [
    {"candidate_id": "cand_demo_1", "channel": "demo_channel", "message_id": 4521,
     "url": "https://t.me/demo_channel/4521", "posted_at": "2026-05-20T08:14:00Z",
     "caption": "LIVE FROM DEMO", "has_media": True, "is_forward": False,
     "accessible": True, "source_query": "@demo_channel"},
]


def _load(name: str):
    path = os.path.join(FIX_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def check() -> int:
    seg = _load("sample_segment_metadata.json")
    res = _load("sample_telegram_results.json")
    assert isinstance(seg, list) and seg and "segment_id" in seg[0]
    assert isinstance(res, list) and res and "candidate_id" in res[0]
    print("OK: fixtures present and well-shaped.")
    return 0


def main(argv) -> int:
    if "--check" in argv:
        return check()
    print(json.dumps({"segments": SEGMENTS,
                      "cached_telegram_results": CACHED_TELEGRAM_RESULTS},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
