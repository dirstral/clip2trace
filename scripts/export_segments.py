#!/usr/bin/env python3
"""Export each detected segment of a video as a playable clip — so the
segmentation can be VISUALLY inspected (not just trusted from timecodes/hashes).

Runs the AUTHORITATIVE inline `detect_source_segments` from sinas-package.yaml
(forcing the PyAV+numpy path that the Sinas worker uses) to get the cut
boundaries, then cuts the real file into one mp4 per segment plus a keyframe
thumbnail. **No LLM is used** — segmentation/decoding is pure PyAV+numpy; OCR
(the only LLM step in the pipeline) is never invoked here, so this costs $0.

Usage:
    uv run python scripts/export_segments.py --all
    uv run python scripts/export_segments.py --video "samples/<name>.mkv"
    uv run python scripts/export_segments.py --all --out segmented
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import av
import numpy as np

# Mirror the Sinas worker (cv2/scenedetect unavailable there) -> PyAV path. Safe
# after the imports above — none of them load cv2; the inline detector exec'd at
# runtime is what must see cv2 absent.
sys.modules["cv2"] = None
sys.modules["scenedetect"] = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sinas-package.yaml")
SAMPLES = os.path.join(ROOT, "samples")


def inline_detect():
    import yaml

    data = yaml.safe_load(open(PKG))
    code = next(
        f["code"]
        for f in data["spec"]["functions"]
        if f["name"] == "detect_source_segments"
    )
    ns: dict = {}
    exec(compile(code, "<inline:detect_source_segments>", "exec"), ns)
    return ns["handler"]


def _even(arr: np.ndarray) -> np.ndarray:
    """yuv420p needs even dimensions."""
    h, w = arr.shape[:2]
    return arr[: h - (h % 2), : w - (w % 2)]


def export_one(video_path: str, out_root: str, detect) -> dict:
    stem = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(out_root, stem)
    os.makedirs(out_dir, exist_ok=True)

    result = detect({"job_id": "export", "video_path": video_path}, {})
    segments = result.get("segments") or []
    method = result.get("method")
    print(f"\n=== {os.path.basename(video_path)} ===")
    print(f"  method: {method} | segments: {len(segments)}")
    if not segments:
        return {"video": video_path, "method": method, "segments": []}

    # Source fps for re-encoding.
    probe = av.open(video_path)
    vstream0 = probe.streams.video[0]
    fps = float(vstream0.average_rate or vstream0.guessed_rate or 25)
    probe.close()
    fps = max(1.0, min(fps, 60.0))

    bounds = [
        (float(s["start_sec"]), float(s["end_sec"]), s["segment_id"]) for s in segments
    ]

    # One decode pass; route each frame to the segment whose window contains it.
    container = av.open(video_path)
    vstream = container.streams.video[0]
    tb = vstream.time_base
    writers = {}  # segment_id -> (out_container, out_stream)
    thumb_saved = set()
    counts = {sid: 0 for _, _, sid in bounds}
    paths = {}
    idx = 0

    def open_writer(sid, start, end, sample_rgb):
        h, w = sample_rgb.shape[:2]
        clip_path = os.path.join(out_dir, f"{sid}_{start:.1f}-{end:.1f}s.mp4")
        oc = av.open(clip_path, mode="w")
        ostream = oc.add_stream("mpeg4", rate=int(round(fps)))
        ostream.width, ostream.height, ostream.pix_fmt = w, h, "yuv420p"
        writers[sid] = (oc, ostream)
        paths[sid] = clip_path
        return writers[sid]

    try:
        for frame in container.decode(vstream):
            t = float(frame.pts * tb) if frame.pts is not None else None
            if t is None:
                continue
            while idx < len(bounds) - 1 and t >= bounds[idx][1]:
                idx += 1
            start, end, sid = bounds[idx]
            if t < start or t >= end:
                continue
            rgb = _even(frame.to_ndarray(format="rgb24"))
            if sid not in writers:
                open_writer(sid, start, end, rgb)
            oc, ostream = writers[sid]
            vf = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            for pkt in ostream.encode(vf):
                oc.mux(pkt)
            counts[sid] += 1
            if sid not in thumb_saved:
                from PIL import Image

                Image.fromarray(rgb).save(os.path.join(out_dir, f"{sid}.png"))
                thumb_saved.add(sid)
    finally:
        for oc, ostream in writers.values():
            for pkt in ostream.encode():  # flush
                oc.mux(pkt)
            oc.close()
        container.close()

    seg_info = []
    for start, end, sid in bounds:
        info = {
            "segment_id": sid,
            "start": start,
            "end": end,
            "frames": counts.get(sid, 0),
            "path": paths.get(sid),
        }
        seg_info.append(info)
        print(
            f"  {sid} [{start:6.2f}-{end:6.2f}s] frames={info['frames']:4d} "
            f"-> {os.path.relpath(info['path'], ROOT) if info['path'] else '(empty)'}"
        )
    print(f"  clips in: {os.path.relpath(out_dir, ROOT)}/")
    return {
        "video": video_path,
        "method": method,
        "out_dir": out_dir,
        "segments": seg_info,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", help="a single video (else use --all)")
    ap.add_argument("--all", action="store_true", help="every samples/*.mkv|mp4|mov")
    ap.add_argument("--out", default=os.path.join(ROOT, "segmented"))
    args = ap.parse_args()

    if args.video:
        videos = [args.video]
    elif args.all:
        videos = sorted(
            glob.glob(os.path.join(SAMPLES, "*.mkv"))
            + glob.glob(os.path.join(SAMPLES, "*.mp4"))
            + glob.glob(os.path.join(SAMPLES, "*.mov"))
        )
    else:
        ap.error("pass --video PATH or --all")

    if not videos:
        print("no videos found")
        return 1

    detect = inline_detect()
    print(
        f"loaded inline detect_source_segments; exporting {len(videos)} video(s) "
        f"(PyAV path, no LLM) -> {os.path.relpath(args.out, ROOT)}/"
    )
    for v in videos:
        try:
            export_one(v, args.out, detect)
        except Exception as exc:  # keep going across the batch
            print(f"  !! failed on {v}: {exc!r}")
    print(
        f"\nDone. Open {os.path.relpath(args.out, ROOT)}/ and play the seg_*.mp4 clips."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
