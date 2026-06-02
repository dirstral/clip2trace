"""rank_source_candidates — apply the evidence scoring rubric, add caveats.

Each candidate may supply either a pre-built `evidence` dict (rubric dimensions)
or a `verification` dict from verify_media_similarity (visual/text/temporal
scores), which is mapped onto the rubric. Never emits an "original" claim; the
strongest label is "very_strong".
"""

from __future__ import annotations

_NEXT_STEPS = [
    "Open the Telegram link and confirm the media visually.",
    "Check whether the post is itself a forward/repost.",
    "Compare post timestamp against the input video's publication date.",
]

_EVIDENCE_KEYS = ("visual_similarity", "handle_watermark", "ocr_caption_query",
                  "predates_input", "temporal_alignment", "channel_relevance",
                  "forward_repost")


def _evidence_for(c):
    """Resolve a candidate's rubric evidence dict, mapping a verify result if needed."""
    ev = c.get("evidence")
    if ev:
        return ev
    v = c.get("verification") or {}
    if v:
        return {
            "visual_similarity": v.get("visual_score", 0.0),
            "ocr_caption_query": v.get("text_score", 0.0),
            "temporal_alignment": v.get("temporal_score", 0.0),
            "handle_watermark": c.get("handle_match", 0.0),
            "predates_input": c.get("predates_input", 0.0),
            "channel_relevance": c.get("channel_relevance", 0.0),
            "forward_repost": c.get("forward_repost", 0.0),
        }
    return {}


def handler(input_data, context):
    input_data = input_data or {}
    candidates = input_data.get("candidates") or []
    try:
        from clip2trace.scoring import EvidenceScores, score_candidate
        ranked = []
        for c in candidates:
            ev = _evidence_for(c)
            res = score_candidate(c.get("candidate_id", "cand_unknown"),
                                  EvidenceScores(**{k: ev.get(k, 0.0)
                                                    for k in _EVIDENCE_KEYS}))
            ranked.append({"candidate_id": res.candidate_id,
                           "confidence": round(res.confidence, 4),
                           "confidence_label": res.confidence_label,
                           "rejected": res.rejected, "evidence": res.evidence,
                           "caveats": res.caveats,
                           "recommended_next_steps": _NEXT_STEPS,
                           "url": c.get("url"),
                           "thumbnail_url": c.get("thumbnail_url")})
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
            ev = _evidence_for(c)
            score = sum(W[k] * max(0.0, min(1.0, float(ev.get(k, 0.0)))) for k in W)
            ranked.append({"candidate_id": c.get("candidate_id"),
                           "confidence": round(score, 4),
                           "confidence_label": label(score),
                           "rejected": score < 0.30, "evidence": ev,
                           "caveats": ["Telegram post may itself be a repost.",
                                       "Automated score; verify manually."],
                           "recommended_next_steps": _NEXT_STEPS,
                           "url": c.get("url"),
                           "thumbnail_url": c.get("thumbnail_url")})

    ranked.sort(key=lambda x: x["confidence"], reverse=True)
    return {"ranked_candidates": ranked}
