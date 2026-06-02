"""analyze_input_video — produce candidate source segments for a job.

Thin orchestrator: runs segment detection (shot detection → uniform windows →
demo fixture) and returns timestamped segments. Per-segment clues are produced
by extract_segment_clues (called next by the coordinator). Long videos should be
invoked via /execute/async; see docs/architecture.md.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    job_id = input_data.get("job_id")
    if not job_id:
        return {"error": "job_id is required"}
    mode = input_data.get("mode", "demo")
    video_path = input_data.get("video_path")
    duration = input_data.get("duration_sec")
    diagnostics = []

    # #36: for a real upload, download the input-videos file to /tmp so PyAV can
    # decode it. The inline YAML copy carries a self-contained equivalent.
    file_id = input_data.get("input_video_file_id")
    if not video_path and file_id:
        try:
            from clip2trace.storage import stage_input_file
            video_path = stage_input_file(file_id, context)
        except Exception as exc:
            diagnostics.append(f"input staging failed: {exc!r}")
        diagnostics.append(
            f"staged input video {file_id}" if video_path
            else f"input video {file_id} could not be staged")

    segments = []
    method = "demo_fixture"
    if video_path:
        try:
            from clip2trace.video import detect_shots, windows_to_segments

            segments = windows_to_segments(
                detect_shots(video_path),
                likelihood=0.5,
                reason="shot boundary; candidate reused footage",
            )
            method = "shot_detection"
        except Exception as exc:
            diagnostics.append(f"shot detection unavailable: {exc!r}")

    if not segments and duration:
        try:
            from clip2trace.video import uniform_windows, windows_to_segments

            segments = windows_to_segments(
                uniform_windows(float(duration)),
                likelihood=0.3,
                reason="uniform window; candidate reused footage",
            )
            method = "uniform_windows"
        except Exception as exc:
            diagnostics.append(f"uniform fallback failed: {exc!r}")

    if not segments:
        try:
            from clip2trace.video import demo_segments

            segments = demo_segments()
        except Exception:
            segments = [
                {
                    "segment_id": "seg_001",
                    "start_sec": 12.0,
                    "end_sec": 24.5,
                    "source_likelihood": 0.81,
                    "reason": "candidate reused footage",
                },
            ]

    return {
        "job_id": job_id,
        "status": "analyzed",
        "mode": mode,
        "method": method,
        "segments": segments,
        "diagnostics": diagnostics,
        "next_step": "extract_segment_clues",
    }
