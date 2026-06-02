"""cluster_segments — group repeated footage across an input video (#25).

Clusters segments whose keyframes share perceptual hashes, so the same footage
reused at multiple timestamps collapses into one cluster. When `candidate_phashes`
is supplied, also returns the segment_ids a single Telegram candidate links to —
letting one candidate map to many input-video timestamps.

Pure transform. Reuses the tested primitives in clip2trace.matching; the inline
sinas-package.yaml copy is self-contained for the sandbox.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    segments = input_data.get("segments") or []
    threshold = input_data.get("threshold")
    threshold = 0.85 if threshold is None else float(threshold)

    from clip2trace.matching import cluster_segments, link_candidate_to_segments

    clusters = cluster_segments(segments, threshold=threshold)
    out = [
        {"cluster_id": c["cluster_id"], "segment_ids": c["segment_ids"]}
        for c in clusters
    ]
    result = {"clusters": out, "cluster_count": len(out), "implemented": True}

    candidate_phashes = list(input_data.get("candidate_phashes") or [])
    if candidate_phashes:
        result["linked_segment_ids"] = link_candidate_to_segments(
            candidate_phashes, segments, threshold=threshold
        )
    return result
