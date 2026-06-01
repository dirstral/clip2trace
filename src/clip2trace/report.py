"""Build the provenance report JSON.

Careful language is enforced here: we never emit "original"; the report is for
human verification and always carries caveats. See skills/report-style.md.
"""

from __future__ import annotations

from typing import Dict, List

BANNED_PHRASES = ("the original", "original post", "confirmed original",
                  "we found the original")

GLOBAL_CAVEATS = [
    "Global Telegram search is retrieval, not proof of origin.",
    "A matched Telegram post may itself be a repost, not the first appearance.",
    "Private, deleted, or restricted posts are out of scope and may be missed.",
    "Confidence scores are automated and require human verification.",
]


def _sanitise(text: str) -> str:
    """Replace overclaiming phrasing with cautious provenance language."""
    out = text or ""
    lowered = out.lower()
    for bad in BANNED_PHRASES:
        if bad in lowered:
            # rebuild preserving case-insensitively
            idx = lowered.find(bad)
            out = out[:idx] + "likely Telegram source candidate" + out[idx + len(bad):]
            lowered = out.lower()
    return out


def build_report(job_id: str, segments: List[Dict],
                 ranked_candidates: List[Dict], *, mode: str = "demo",
                 summary: str = "") -> Dict:
    """Assemble the report JSON dict (schemas.ProvenanceReport shape)."""
    kept = [c for c in ranked_candidates if not c.get("rejected")]
    label_counts: Dict[str, int] = {}
    for c in kept:
        label_counts[c.get("confidence_label", "unknown")] = \
            label_counts.get(c.get("confidence_label", "unknown"), 0) + 1

    if not summary:
        summary = (
            f"Analysed input video into {len(segments)} candidate source "
            f"segment(s); {len(kept)} Telegram source candidate(s) retained "
            f"after scoring (mode={mode}). "
            "These are likely candidates for human verification, not confirmed origins."
        )

    return {
        "job_id": job_id,
        "summary": _sanitise(summary),
        "generated_mode": mode,
        "segments": segments,
        "ranked_candidates": kept,
        "label_counts": label_counts,
        "caveats": list(GLOBAL_CAVEATS),
    }
