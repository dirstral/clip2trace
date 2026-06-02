"""verify_media_similarity — compare segment keyframes vs candidate media.

Returns visual (perceptual-hash), text (caption/overlap) and temporal (duration
alignment) scores plus matched-frame references. The combined overall_score is a
quick triage signal; the authoritative weighting happens in rank_source_candidates.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    seg = input_data.get("segment_phashes") or []
    cand = input_data.get("candidate_phashes") or []
    seg_text = input_data.get("segment_text", "")
    cand_text = input_data.get("candidate_text", "")
    seg_dur = input_data.get("segment_duration") or 0.0
    cand_dur = input_data.get("candidate_duration") or 0.0

    try:
        from clip2trace.matching import (best_frame_similarity, matched_frames,
                                         text_overlap_score,
                                         temporal_alignment_score)
        visual, _, _ = best_frame_similarity(seg, cand)
        frames = matched_frames(seg, cand)
        text = text_overlap_score(seg_text, cand_text)
        temporal = (temporal_alignment_score(float(seg_dur), float(cand_dur))
                    if seg_dur and cand_dur else 0.0)
    except Exception:
        def ham(a, b):
            return bin(int(a, 16) ^ int(b, 16)).count("1")
        visual, frames = 0.0, []
        for i, a in enumerate(seg):
            for j, b in enumerate(cand):
                if len(a) != len(b):
                    continue
                sim = max(0.0, 1.0 - ham(a, b) / 64.0)
                if sim >= 0.85:
                    frames.append({"segment_frame": i, "candidate_frame": j,
                                   "similarity": round(sim, 4)})
                visual = max(visual, sim)
        ta, tb = set(str(seg_text).lower().split()), set(str(cand_text).lower().split())
        text = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
        if seg_dur and cand_dur:
            r = min(float(seg_dur), float(cand_dur)) / max(float(seg_dur), float(cand_dur))
            temporal = max(0.0, (r - 0.75) / 0.25)
        else:
            temporal = 0.0

    overall = round(0.6 * visual + 0.25 * text + 0.15 * temporal, 4)
    return {"visual_score": round(visual, 4), "text_score": round(text, 4),
            "temporal_score": round(temporal, 4), "overall_score": overall,
            "matched_frames": frames}
