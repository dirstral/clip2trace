"""create_job — create a source-tracing job for one input video.

Returns the full job-state shape (status/progress/mode/input metadata) so the
dashboard and downstream steps can track progress. Local/demo persistence uses
an in-memory store; inside Sinas, wire this to the clip2trace/jobs state store
(Ark's #5/#6) via the runtime SDK.
"""

from __future__ import annotations

_META_FIELDS = ("input_video_file_id", "video_context", "date_hint",
                "language_hint", "topic_hint")


def handler(input_data, context):
    input_data = input_data or {}
    mode = input_data.get("mode", "demo")
    if mode not in ("demo", "live", "hybrid"):
        return {"error": "mode must be one of demo|live|hybrid"}
    exec_id = (context or {}).get("execution_id", "local")
    job_id = f"job_{exec_id}"
    meta = {k: input_data.get(k) for k in _META_FIELDS}

    try:
        from clip2trace.storage import build_job_state
        state = build_job_state(job_id, mode=mode, **meta)
    except Exception:
        state = {"job_id": job_id, "status": "created", "mode": mode,
                 "progress": 0.0, "error": None}
        state.update(meta)

    state["next_step"] = "analyze_input_video"
    return state
