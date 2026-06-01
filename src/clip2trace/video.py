"""Video analysis helpers: shot detection, keyframe extraction, perceptual hash.

All heavy dependencies (OpenCV, scenedetect, imagehash, Pillow) are imported
lazily so this module imports cleanly in minimal environments and so callers can
degrade gracefully when the Sinas runtime lacks them. See
docs/research/runtime-diagnostics.md.
"""

from __future__ import annotations

from typing import List, Optional


def capabilities() -> dict:
    """Report which optional video libraries are importable right now."""
    caps = {}
    for mod in ("cv2", "scenedetect", "imagehash", "PIL", "numpy"):
        try:
            __import__(mod)
            caps[mod] = True
        except Exception:
            caps[mod] = False
    return caps


def detect_shots(video_path: str, threshold: float = 27.0) -> List[dict]:
    """Detect shot boundaries with PySceneDetect if available.

    Returns a list of {start_sec, end_sec}. Raises RuntimeError if scenedetect
    is unavailable so the caller can fall back to a fixture / uniform windows.
    """
    try:
        from scenedetect import detect, ContentDetector  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"scenedetect unavailable: {exc!r}")

    scenes = detect(video_path, ContentDetector(threshold=threshold))
    return [{"start_sec": s.get_seconds(), "end_sec": e.get_seconds()}
            for s, e in scenes]


def uniform_windows(duration_sec: float, window: float = 8.0,
                    stride: float = 8.0) -> List[dict]:
    """Fallback segmentation: fixed windows across the whole video."""
    out, t = [], 0.0
    while t < duration_sec:
        out.append({"start_sec": round(t, 2),
                    "end_sec": round(min(t + window, duration_sec), 2)})
        t += stride
    return out


def extract_keyframes(video_path: str, start_sec: float, end_sec: float,
                      n: int = 3) -> List["object"]:
    """Grab up to n evenly spaced frames in [start_sec, end_sec] as numpy arrays.

    Raises RuntimeError if OpenCV is unavailable.
    """
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"opencv unavailable: {exc!r}")

    cap = cv2.VideoCapture(video_path)
    try:
        frames = []
        if n <= 0 or end_sec <= start_sec:
            return frames
        step = (end_sec - start_sec) / (n + 1)
        for i in range(1, n + 1):
            cap.set(cv2.CAP_PROP_POS_MSEC, (start_sec + step * i) * 1000.0)
            ok, frame = cap.read()
            if ok:
                frames.append(frame)
        return frames
    finally:
        cap.release()


def phash_of_frame(frame, hash_size: int = 8) -> Optional[str]:
    """Perceptual hash (hex string) of a single BGR frame, or None if libs missing."""
    try:
        import cv2  # type: ignore
        import imagehash  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return str(imagehash.phash(Image.fromarray(rgb), hash_size=hash_size))


def center_crop_phash(frame, hash_size: int = 8, crop: float = 0.6) -> Optional[str]:
    """Perceptual hash of a center crop, to ignore lower-third overlays/banners."""
    try:
        import cv2  # type: ignore
        import imagehash  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    h, w = frame.shape[:2]
    ch, cw = int(h * crop), int(w * crop)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    cropped = frame[y0:y0 + ch, x0:x0 + cw]
    rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
    return str(imagehash.phash(Image.fromarray(rgb), hash_size=hash_size))
