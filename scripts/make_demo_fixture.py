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
    {
        "segment_id": "seg_001",
        "start_sec": 12.0,
        "end_sec": 24.5,
        "source_likelihood": 0.81,
        "reason": "candidate reused footage",
        "clues": {
            "visible_handles": ["@demo_channel"],
            "ocr_text": "LIVE FROM DEMO",
            "context_terms": ["demo", "street", "crowd"],
            "phashes": ["c3e1c3e1c3e1c3e1"],
        },
    },
]

# A strong match, a weak/unrelated candidate, and an inaccessible repost — so the
# demo exercises the full confidence range, not just one perfect hit.
CACHED_TELEGRAM_RESULTS = [
    {
        "candidate_id": "cand_demo_1",
        "channel": "demo_channel",
        "message_id": 4521,
        "url": "https://t.me/demo_channel/4521",
        "posted_at": "2026-05-20T08:14:00Z",
        "caption": "LIVE FROM DEMO",
        "has_media": True,
        "is_forward": False,
        "accessible": True,
        "source_query": "@demo_channel",
        "phashes": ["c3e1c3e1c3e1c3e1"],
    },
    {
        "candidate_id": "cand_demo_2",
        "channel": "other_channel",
        "message_id": 8090,
        "url": "https://t.me/other_channel/8090",
        "posted_at": "2026-05-29T19:40:00Z",
        "caption": "unrelated street scene",
        "has_media": True,
        "is_forward": False,
        "accessible": True,
        "source_query": "street",
        "phashes": ["0f0f0f0f0f0f0f0f"],
    },
    {
        "candidate_id": "cand_demo_3",
        "channel": "reposter_channel",
        "message_id": 1212,
        "url": "https://t.me/reposter_channel/1212",
        "posted_at": "2026-05-25T10:00:00Z",
        "caption": "LIVE FROM DEMO (reposted)",
        "has_media": True,
        "is_forward": True,
        "forward_origin": "demo_channel",
        "accessible": False,
        "source_query": "@demo_channel",
        "phashes": ["c3e1c3e1c3e1c3e1"],
    },
]


def _load(name: str):
    path = os.path.join(FIX_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def check() -> int:
    seg = _load("sample_segment_metadata.json")
    res = _load("sample_telegram_results.json")
    assert isinstance(seg, list) and seg and "segment_id" in seg[0]
    assert seg[0].get("clues", {}).get("phashes"), "segment needs phashes"
    assert isinstance(res, list) and res and "candidate_id" in res[0]
    # The strong candidate must carry a url + phashes that match the segment.
    assert res[0].get("url") and res[0].get("phashes"), "candidate needs url+phashes"
    assert any(
        str(c.get("source_query", "")).startswith("@") for c in res
    ), "expected at least one handle-sourced candidate"
    print(
        f"OK: fixtures present and well-shaped "
        f"({len(seg)} segment(s), {len(res)} candidate(s))."
    )
    return 0


def main(argv) -> int:
    if "--check" in argv:
        return check()
    print(
        json.dumps(
            {"segments": SEGMENTS, "cached_telegram_results": CACHED_TELEGRAM_RESULTS},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
