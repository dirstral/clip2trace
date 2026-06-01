"""create_job — create a source-tracing job for one input video."""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    mode = input_data.get("mode", "demo")
    if mode not in ("demo", "live", "hybrid"):
        return {"error": "mode must be one of demo|live|hybrid"}
    exec_id = (context or {}).get("execution_id", "local")
    job_id = f"job_{exec_id}"
    return {
        "job_id": job_id,
        "status": "created",
        "mode": mode,
        "input_video_file_id": input_data.get("input_video_file_id"),
        "video_context": input_data.get("video_context"),
        "date_hint": input_data.get("date_hint"),
        "language_hint": input_data.get("language_hint"),
        "topic_hint": input_data.get("topic_hint"),
        "next_step": "analyze_input_video",
    }
