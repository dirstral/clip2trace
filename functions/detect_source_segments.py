"""detect_source_segments — find candidate reused-footage windows.

Real implementation uses clip2trace.video.detect_shots (PySceneDetect) and falls
back to uniform windows. Without a downloadable video / OpenCV it returns a
deterministic placeholder segment so the pipeline stays runnable.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    if not input_data.get("job_id"):
        return {"error": "job_id is required"}

    video_path = input_data.get("video_path")
    if video_path:
        try:
            from clip2trace.video import detect_shots
            shots = detect_shots(video_path)
            segments = [
                {"segment_id": f"seg_{i:03d}",
                 "start_sec": round(s["start_sec"], 2),
                 "end_sec": round(s["end_sec"], 2),
                 "source_likelihood": 0.5,
                 "reason": "shot boundary; candidate reused footage"}
                for i, s in enumerate(shots, 1)
            ]
            return {"segments": segments, "implemented": True}
        except Exception as exc:
            return {"segments": [], "implemented": False,
                    "diagnostics": [f"shot detection unavailable: {exc!r}"]}

    return {
        "segments": [
            {"segment_id": "seg_001", "start_sec": 102.4, "end_sec": 118.9,
             "source_likelihood": 0.74, "reason": "candidate reused footage"}
        ],
        "implemented": False,
    }
