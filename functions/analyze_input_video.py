"""analyze_input_video — high-level orchestration of input-video analysis.

Reads input metadata, then (intended) calls detect_source_segments and
extract_segment_clues. In demo mode returns fixture-shaped output.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    job_id = input_data.get("job_id")
    if not job_id:
        return {"error": "job_id is required"}
    mode = input_data.get("mode", "demo")
    return {
        "job_id": job_id,
        "status": "analyzed",
        "mode": mode,
        "segments_ref": f"clip2trace/segments/{job_id}",
        "next_step": "detect_source_segments",
        "note": ("stub: orchestrate detect_source_segments + "
                 "extract_segment_clues; returns fixture in demo mode"),
    }
