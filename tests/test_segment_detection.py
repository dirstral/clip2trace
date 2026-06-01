"""#9/#10 — segment detection (uniform/demo + real shot detection & keyframes)."""

import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)

from clip2trace.video import (uniform_windows, windows_to_segments,  # noqa: E402
                              demo_segments)


def _load(name):
    path = os.path.join(FUNCS, name + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_uniform_windows_cover_duration():
    wins = uniform_windows(20.0, window=8.0, stride=8.0)
    assert wins[0]["start_sec"] == 0.0
    assert wins[-1]["end_sec"] == 20.0
    assert all(w["end_sec"] > w["start_sec"] for w in wins)


def test_windows_to_segments_shape():
    segs = windows_to_segments([{"start_sec": 0, "end_sec": 8},
                                {"start_sec": 8, "end_sec": 16}])
    assert [s["segment_id"] for s in segs] == ["seg_001", "seg_002"]
    assert all(0.0 <= s["source_likelihood"] <= 1.0 for s in segs)


def test_demo_segments_are_timestamped():
    segs = demo_segments()
    assert segs and all(s["end_sec"] > s["start_sec"] for s in segs)


def test_detect_demo_path():
    out = _load("detect_source_segments").handler({"job_id": "j"}, {})
    assert out["implemented"] and out["method"] == "demo_fixture"
    assert out["segments"] and all("start_sec" in s for s in out["segments"])


def test_detect_uniform_fallback_without_video():
    out = _load("detect_source_segments").handler(
        {"job_id": "j", "duration_sec": 20.0}, {})
    assert out["method"] == "uniform_windows" and out["segments"]


def _write_synth_video(path, cv2, np, frames=30, size=(64, 48), fps=10):
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    w, h = size
    vw = cv2.VideoWriter(path, fourcc, fps, (w, h))
    assert vw.isOpened(), "could not open VideoWriter"
    half = frames // 2
    for _ in range(half):  # first scene: black
        vw.write(np.zeros((h, w, 3), dtype=np.uint8))
    for _ in range(frames - half):  # second scene: white
        vw.write(np.full((h, w, 3), 255, dtype=np.uint8))
    vw.release()


def test_real_keyframe_phash_extraction(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    path = str(tmp_path / "synth.avi")
    _write_synth_video(path, cv2, np)

    out = _load("extract_segment_clues").handler(
        {"job_id": "j", "segment_id": "seg_001",
         "video_path": path, "start_sec": 0.2, "end_sec": 2.5}, {})
    assert out["phashes"], "expected perceptual hashes from real keyframes"
    # imagehash hex strings
    assert all(int(h, 16) >= 0 for h in out["phashes"])


def test_real_shot_detection(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    pytest.importorskip("scenedetect")
    path = str(tmp_path / "synth.avi")
    _write_synth_video(path, cv2, np, frames=40)

    out = _load("detect_source_segments").handler(
        {"job_id": "j", "video_path": path}, {})
    assert out["implemented"] and out["method"] == "shot_detection"
