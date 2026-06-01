"""verify_media_similarity — compare segment keyframes vs candidate media."""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    seg = input_data.get("segment_phashes") or []
    cand = input_data.get("candidate_phashes") or []
    seg_text = input_data.get("segment_text", "")
    cand_text = input_data.get("candidate_text", "")

    try:
        from clip2trace.matching import (best_frame_similarity,
                                         matched_frames, text_overlap_score)
        visual, _, _ = best_frame_similarity(seg, cand)
        frames = matched_frames(seg, cand)
        text = text_overlap_score(seg_text, cand_text)
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
        text = 0.0

    overall = round(0.7 * visual + 0.3 * text, 4)
    return {"visual_score": round(visual, 4), "text_score": round(text, 4),
            "temporal_score": 0.0, "overall_score": overall,
            "matched_frames": frames}
