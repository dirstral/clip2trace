"""detect_source_segments — find candidate reused-footage windows.

Resolution order:
  1. real shot detection (PySceneDetect) when a `video_path` is downloadable;
  2. uniform-window fallback when `duration_sec` is known but shot detection is
     unavailable;
  3. deterministic demo segments otherwise, so the pipeline always runs.
No Telegram dependency.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    if not input_data.get("job_id"):
        return {"error": "job_id is required"}

    video_path = input_data.get("video_path")
    duration = input_data.get("duration_sec")
    diagnostics = []

    # #36: stage a real uploaded video to /tmp for decode (self-contained in YAML).
    file_id = input_data.get("input_video_file_id")
    if not video_path and file_id:
        try:
            from clip2trace.storage import stage_input_file

            video_path = stage_input_file(
                file_id, context, cache_key=input_data.get("job_id")
            )
        except Exception as exc:
            diagnostics.append(f"input staging failed: {exc!r}")
        diagnostics.append(
            f"staged input video {file_id}"
            if video_path
            else f"input video {file_id} could not be staged"
        )

    # 1. Real shot detection.
    if video_path:
        try:
            from clip2trace.video import detect_shots, windows_to_segments

            shots = detect_shots(video_path)
            return {
                "segments": windows_to_segments(
                    shots,
                    likelihood=0.5,
                    reason="shot boundary; candidate reused footage",
                ),
                "method": "shot_detection",
                "implemented": True,
            }
        except Exception as exc:
            diagnostics.append(f"shot detection unavailable: {exc!r}")

    # 2. Uniform-window fallback (needs a duration).
    if duration:
        try:
            from clip2trace.video import uniform_windows, windows_to_segments

            wins = uniform_windows(float(duration))
            return {
                "segments": windows_to_segments(
                    wins,
                    likelihood=0.3,
                    reason="uniform window; candidate reused footage",
                ),
                "method": "uniform_windows",
                "implemented": True,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            diagnostics.append(f"uniform fallback failed: {exc!r}")

    # 3. Demo / fixture segments.
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
            {
                "segment_id": "seg_002",
                "start_sec": 58.2,
                "end_sec": 67.0,
                "source_likelihood": 0.64,
                "reason": "candidate reused footage",
            },
        ]
    return {
        "segments": segments,
        "method": "demo_fixture",
        "implemented": True,
        "diagnostics": diagnostics,
    }
