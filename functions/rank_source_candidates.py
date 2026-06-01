"""rank_source_candidates — apply the evidence scoring rubric, add caveats.

Never emits an "original" claim; strongest label is "very_strong".
"""

from __future__ import annotations

_NEXT_STEPS = [
    "Open the Telegram link and confirm the media visually.",
    "Check whether the post is itself a forward/repost.",
    "Compare post timestamp against the input video's publication date.",
]


def handler(input_data, context):
    input_data = input_data or {}
    candidates = input_data.get("candidates") or []
    try:
        from clip2trace.scoring import EvidenceScores, score_candidate
        ranked = []
        for c in candidates:
            ev = c.get("evidence", {}) or {}
            res = score_candidate(c.get("candidate_id", "cand_unknown"),
                                  EvidenceScores(**{k: ev.get(k, 0.0)
                                                    for k in EvidenceScores().__dict__}))
            ranked.append({"candidate_id": res.candidate_id,
                           "confidence": round(res.confidence, 4),
                           "confidence_label": res.confidence_label,
                           "rejected": res.rejected, "evidence": res.evidence,
                           "caveats": res.caveats,
                           "recommended_next_steps": _NEXT_STEPS,
                           "url": c.get("url")})
    except Exception:
        W = {"visual_similarity": 0.40, "handle_watermark": 0.15,
             "ocr_caption_query": 0.15, "predates_input": 0.15,
             "temporal_alignment": 0.05, "channel_relevance": 0.05,
             "forward_repost": 0.05}

        def label(s):
            for lo, name in [(0.85, "very_strong"), (0.70, "strong"),
                             (0.50, "plausible"), (0.30, "weak")]:
                if s >= lo:
                    return name
            return "reject"

        ranked = []
        for c in candidates:
            ev = c.get("evidence", {}) or {}
            score = sum(W[k] * max(0.0, min(1.0, float(ev.get(k, 0.0)))) for k in W)
            ranked.append({"candidate_id": c.get("candidate_id"),
                           "confidence": round(score, 4),
                           "confidence_label": label(score),
                           "rejected": score < 0.30, "evidence": ev,
                           "caveats": ["Telegram post may itself be a repost.",
                                       "Automated score; verify manually."],
                           "recommended_next_steps": _NEXT_STEPS,
                           "url": c.get("url")})

    ranked.sort(key=lambda x: x["confidence"], reverse=True)
    return {"ranked_candidates": ranked}
