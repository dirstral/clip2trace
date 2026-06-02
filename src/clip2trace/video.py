"""Video analysis helpers: shot detection, keyframe extraction, perceptual hash.

Two decode backends, tried in order so the pipeline runs on minimal workers:
  1. OpenCV / PySceneDetect — preferred when the system libs are present;
  2. **PyAV** (`av`) — its manylinux wheel bundles ffmpeg, so it needs no system
     `libGL`/`ffmpeg` and works on the managed Sinas worker (pip-only).
Perceptual hashing uses only Pillow + imagehash + numpy (no OpenCV), all of which
import on the managed worker. See docs/research/runtime-diagnostics.md.
"""

from __future__ import annotations

from typing import List, Optional


def capabilities() -> dict:
    """Report which optional video libraries are importable right now."""
    caps = {}
    for mod in ("av", "cv2", "scenedetect", "imagehash", "PIL", "numpy"):
        try:
            __import__(mod)
            caps[mod] = True
        except Exception:
            caps[mod] = False
    return caps


# ── Shot detection ────────────────────────────────────────────────────────────


def _detect_shots_av(
    video_path: str,
    threshold: float = 0.30,
    sample_fps: float = 3.0,
    max_dim: int = 128,
) -> List[dict]:
    """Lightweight shot detection with PyAV + numpy (no OpenCV).

    Samples ~`sample_fps` downscaled grayscale frames and marks a cut when the
    mean absolute frame-to-frame difference exceeds `threshold` (0..1).
    """
    import av  # type: ignore
    import numpy as np  # type: ignore

    container = av.open(video_path)
    try:
        stream = container.streams.video[0]
        tb = stream.time_base
        prev = None
        cuts = [0.0]
        last_t = 0.0
        next_sample = 0.0
        step = 1.0 / sample_fps if sample_fps > 0 else 0.0
        for frame in container.decode(stream):
            t = float(frame.pts * tb) if frame.pts is not None else last_t
            last_t = t
            if t + 1e-9 < next_sample:
                continue
            next_sample = t + step
            arr = frame.to_ndarray(format="gray8")
            h, w = arr.shape
            scale = max(1, int(max(h, w) / max_dim))
            small = arr[::scale, ::scale].astype("float32") / 255.0
            if prev is not None and prev.shape == small.shape:
                if float(np.mean(np.abs(small - prev))) > threshold:
                    cuts.append(t)
            prev = small
        duration = (
            float(stream.duration * tb) if stream.duration else last_t
        ) or last_t
    finally:
        container.close()

    bounds = sorted(set(cuts + [duration]))
    windows = [
        {"start_sec": round(s, 2), "end_sec": round(e, 2)}
        for s, e in zip(bounds, bounds[1:], strict=False)
        if e - s > 0.1
    ]
    return windows or [{"start_sec": 0.0, "end_sec": round(duration, 2)}]


def detect_shots(video_path: str, threshold: float = 27.0) -> List[dict]:
    """Detect shot boundaries: PySceneDetect if available, else PyAV+numpy.

    Returns a list of {start_sec, end_sec}. Raises RuntimeError only if neither
    backend is usable, so the caller can fall back to uniform windows / fixtures.
    """
    try:
        from scenedetect import ContentDetector, detect  # type: ignore

        def _secs(tc):  # `.seconds` (newer scenedetect) else get_seconds()
            return tc.seconds if hasattr(tc, "seconds") else tc.get_seconds()

        scenes = detect(video_path, ContentDetector(threshold=threshold))
        if scenes:
            return [{"start_sec": _secs(s), "end_sec": _secs(e)} for s, e in scenes]
    except Exception:
        pass
    try:
        return _detect_shots_av(video_path)
    except Exception as exc:
        raise RuntimeError(
            f"shot detection unavailable (scenedetect/av): {exc!r}"
        ) from exc


def uniform_windows(
    duration_sec: float, window: float = 8.0, stride: float = 8.0
) -> List[dict]:
    """Fallback segmentation: fixed windows across the whole video."""
    out, t = [], 0.0
    while t < duration_sec:
        out.append(
            {
                "start_sec": round(t, 2),
                "end_sec": round(min(t + window, duration_sec), 2),
            }
        )
        t += stride
    return out


def windows_to_segments(
    windows: List[dict],
    *,
    prefix: str = "seg",
    likelihood: float = 0.5,
    reason: str = "candidate reused footage",
) -> List[dict]:
    """Turn {start_sec,end_sec} windows into SourceSegment-shaped dicts."""
    return [
        {
            "segment_id": f"{prefix}_{i:03d}",
            "start_sec": round(float(w["start_sec"]), 2),
            "end_sec": round(float(w["end_sec"]), 2),
            "source_likelihood": likelihood,
            "reason": reason,
        }
        for i, w in enumerate(windows, 1)
    ]


# Deterministic demo segments for fixture/demo mode (no video runtime needed).
# Each carries its clues inline (phashes/ocr_text/handles) so the demo produces a
# real match without a video: seg_001's phash matches the cached cand_demo_1
# candidate (-> strong); seg_002's does not (-> stays low, showing discrimination).
DEMO_SEGMENTS = [
    {
        "segment_id": "seg_001",
        "start_sec": 12.0,
        "end_sec": 24.5,
        "source_likelihood": 0.81,
        "reason": "candidate reused footage",
        "phashes": ["c3e1c3e1c3e1c3e1"],
        "ocr_text": "LIVE FROM DEMO",
        "visible_handles": ["@demo_channel"],
        "context_terms": ["demo", "street", "crowd"],
    },
    {
        "segment_id": "seg_002",
        "start_sec": 58.2,
        "end_sec": 67.0,
        "source_likelihood": 0.64,
        "reason": "candidate reused footage",
        "phashes": ["5a5a5a5a5a5a5a5a"],
        "ocr_text": "",
        "visible_handles": [],
        "context_terms": [],
    },
]


def demo_segments() -> List[dict]:
    """Copy of the deterministic demo segments."""
    return [dict(s) for s in DEMO_SEGMENTS]


# ── Keyframe extraction (returns RGB uint8 ndarrays from either backend) ────────


def _extract_keyframes_cv2(
    video_path: str, start_sec: float, end_sec: float, n: int
) -> List["object"]:
    import cv2  # type: ignore

    cap = cv2.VideoCapture(video_path)
    try:
        frames = []
        step = (end_sec - start_sec) / (n + 1)
        for i in range(1, n + 1):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start_sec + step * i) * 1000.0)
            ok, frame = cap.read()
            if ok:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return frames
    finally:
        cap.release()


def _extract_keyframes_av(
    video_path: str, start_sec: float, end_sec: float, n: int
) -> List["object"]:
    import av  # type: ignore

    frames: List[object] = []
    container = av.open(video_path)
    try:
        stream = container.streams.video[0]
        tb = stream.time_base
        step = (end_sec - start_sec) / (n + 1)
        for i in range(1, n + 1):
            t = start_sec + step * i
            try:
                container.seek(int(t / tb), stream=stream, backward=True)
            except Exception:
                pass
            picked = None
            for frame in container.decode(stream):
                picked = frame
                ft = float(frame.pts * tb) if frame.pts is not None else t
                if ft >= t:
                    break
            if picked is not None:
                frames.append(picked.to_ndarray(format="rgb24"))
        return frames
    finally:
        container.close()


def extract_keyframes(
    video_path: str, start_sec: float, end_sec: float, n: int = 3
) -> List["object"]:
    """Up to n evenly spaced frames in [start_sec, end_sec] as RGB uint8 ndarrays.

    Tries OpenCV, then PyAV. Raises RuntimeError if neither decoder is available.
    """
    if n <= 0 or end_sec <= start_sec:
        return []
    try:
        import cv2  # type: ignore  # noqa: F401

        return _extract_keyframes_cv2(video_path, start_sec, end_sec, n)
    except Exception:
        pass
    try:
        import av  # type: ignore  # noqa: F401

        return _extract_keyframes_av(video_path, start_sec, end_sec, n)
    except Exception as exc:
        raise RuntimeError(f"no video decoder available (opencv/av): {exc!r}") from exc


# ── Perceptual hashing (Pillow + imagehash + numpy only — no OpenCV) ────────────


def phash_of_frame(frame, hash_size: int = 8) -> Optional[str]:
    """Perceptual hash (hex) of an RGB uint8 frame, or None if libs missing."""
    try:
        import imagehash  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    return str(imagehash.phash(Image.fromarray(frame), hash_size=hash_size))


def center_crop_phash(frame, hash_size: int = 8, crop: float = 0.6) -> Optional[str]:
    """Perceptual hash of a center crop, to ignore lower-third overlays/banners."""
    try:
        import imagehash  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    h, w = frame.shape[:2]
    ch, cw = int(h * crop), int(w * crop)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    cropped = frame[y0 : y0 + ch, x0 : x0 + cw]
    return str(imagehash.phash(Image.fromarray(cropped), hash_size=hash_size))
