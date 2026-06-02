#!/usr/bin/env python3
"""Local end-to-end test of the #36 input-delivery + #25 clustering path.

Runs the AUTHORITATIVE inline `code:` blocks from sinas-package.yaml against a
real video, with a local folder standing in for the Sinas `input-videos`
collection and a tiny stub HTTP server mimicking the real files API
(GET /files/{ns}/{collection}/{name} -> {content_base64, ...}).

It forces the pure PyAV path (blocks cv2/scenedetect) so it mirrors the Sinas
worker, where cv2 is unavailable. So this exercises exactly the deployed code:

  stage download -> base64 decode -> PyAV shot detection -> keyframe phashes ->
  cluster_segments -> render_report (repeated_footage).

Usage:
    uv run python scripts/try_local_pipeline.py                  # synthetic clip
    uv run python scripts/try_local_pipeline.py --video PATH     # your own clip
    uv run python scripts/try_local_pipeline.py --keep           # keep artifacts
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading

import numpy as np

# Mirror the Sinas worker: cv2/scenedetect are NOT importable there, so force the
# PyAV+numpy+imagehash path (also dodges the local av/cv2 dylib clash). Safe after
# the imports above — none of them load cv2; the inline detector exec'd at runtime
# is what must see cv2 absent.
sys.modules["cv2"] = None
sys.modules["scenedetect"] = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sinas-package.yaml")

W, H, FPS, SCENE_SECS = 320, 240, 8, 3


def _scene_frame(kind: int) -> np.ndarray:
    """A deterministic frame for scene `kind`, distinct in BOTH luma (so the
    grayscale shot detector fires on cuts) and spatial structure (so perceptual
    hashes differ between scenes but match a scene to its identical repeat)."""
    img = np.zeros((H, W, 3), dtype=np.uint8)
    if kind == 0:                       # dark field + bright block, upper-left
        img[:] = 20
        img[20:120, 20:160, :] = 255
    elif kind == 1:                     # bright field + dark block, lower-right
        img[:] = 225
        img[120:220, 160:300, :] = 15
    else:                               # mid-gray checkerboard
        tile = 40
        for yy in range(0, H, tile):
            for xx in range(0, W, tile):
                v = 200 if ((yy // tile + xx // tile) % 2 == 0) else 60
                img[yy:yy + tile, xx:xx + tile, :] = v
    return img


def make_compilation(path: str) -> float:
    """Encode A,B,C,A — scene A repeats, so two segments should cluster."""
    import av
    order = [0, 1, 2, 0]  # the last scene is identical to the first
    container = av.open(path, mode="w")
    stream = container.add_stream("mpeg4", rate=FPS)
    stream.width, stream.height, stream.pix_fmt = W, H, "yuv420p"
    for kind in order:
        frame_arr = _scene_frame(kind)
        for _ in range(FPS * SCENE_SECS):
            frame = av.VideoFrame.from_ndarray(frame_arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return len(order) * SCENE_SECS


def load_inline_handlers():
    import yaml
    data = yaml.safe_load(open(PKG))
    code_by_name = {f["name"]: f["code"] for f in data["spec"]["functions"]}
    handlers = {}
    for name, code in code_by_name.items():
        ns: dict = {}
        exec(compile(code, f"<inline:{name}>", "exec"), ns)
        handlers[name] = ns["handler"]
    return handlers


def start_files_stub(instance_dir: str):
    """Serve GET /files/{ns}/{collection}/{name} like the real Sinas files API."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            from urllib.parse import unquote
            name = unquote(self.path.rstrip("/").split("/")[-1].split("?")[0])
            fp = os.path.join(instance_dir, "input-videos", name)
            if not os.path.isfile(fp):
                self.send_response(404)
                self.end_headers()
                return
            with open(fp, "rb") as fh:
                raw = fh.read()
            body = json.dumps({
                "content_base64": base64.b64encode(raw).decode("ascii"),
                "content_type": "video/mp4", "file_metadata": {}, "version": 1,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", help="path to a real video (else synthetic)")
    ap.add_argument("--instance-dir", default=os.path.join(ROOT, ".localinstance"))
    ap.add_argument("--keep", action="store_true", help="keep generated artifacts")
    args = ap.parse_args()

    coll = os.path.join(args.instance_dir, "input-videos")
    os.makedirs(coll, exist_ok=True)

    if args.video:
        name = os.path.basename(args.video)
        dest = os.path.join(coll, name)
        if os.path.abspath(args.video) != os.path.abspath(dest):
            import shutil
            shutil.copyfile(args.video, dest)
        duration = None
        print(f"[setup] using real video {args.video} -> {dest}")
    else:
        name = "compilation.mp4"
        dest = os.path.join(coll, name)
        duration = make_compilation(dest)
        size = os.path.getsize(dest)
        print(f"[setup] generated synthetic compilation {dest} "
              f"({size/1024:.0f} KB, ~{duration:.0f}s, scene A repeats)")

    httpd, port = start_files_stub(args.instance_dir)
    base_url = f"http://127.0.0.1:{port}"
    context = {"access_token": "local-test", "base_url": base_url}
    print(f"[setup] files-API stub on {base_url} (folder = {coll})")

    fns = load_inline_handlers()
    print(f"[setup] loaded {len(fns)} inline functions from sinas-package.yaml\n")

    # 1) analyze_input_video — stages via the stub, PyAV-decodes, returns segments
    analyzed = fns["analyze_input_video"]({
        "job_id": "job_local", "mode": "hybrid", "input_video_file_id": name,
    }, context)
    print("=== analyze_input_video ===")
    print("  method   :", analyzed.get("method"))
    print("  segments :", len(analyzed.get("segments") or []))
    for d in analyzed.get("diagnostics") or []:
        print("  diag     :", d)
    segments = analyzed.get("segments") or []
    if analyzed.get("method") not in ("shot_detection_pyav", "shot_detection"):
        print("  !! did NOT decode the real file — check staging above")

    # 2) extract_segment_clues per segment — re-stages, extracts keyframe phashes
    print("\n=== extract_segment_clues (per segment) ===")
    enriched = []
    for seg in segments:
        clues = fns["extract_segment_clues"]({
            "job_id": "job_local", "segment_id": seg["segment_id"],
            "input_video_file_id": name,
            "start_sec": seg.get("start_sec"), "end_sec": seg.get("end_sec"),
        }, context)
        phashes = clues.get("phashes") or []
        enriched.append({"segment_id": seg["segment_id"],
                         "start_sec": seg.get("start_sec"),
                         "end_sec": seg.get("end_sec"), "phashes": phashes})
        print(f"  {seg['segment_id']} "
              f"[{seg.get('start_sec')}-{seg.get('end_sec')}s] "
              f"phashes={len(phashes)} sample={phashes[:1]}")

    # 3) cluster_segments — group footage reused at multiple timestamps
    clustered = fns["cluster_segments"]({"segments": enriched}, context)
    print("\n=== cluster_segments ===")
    for c in clustered.get("clusters") or []:
        tag = "  <-- repeated footage" if len(c["segment_ids"]) > 1 else ""
        print(f"  {c['cluster_id']}: {c['segment_ids']}{tag}")

    # 4) render_report — surfaces repeated_footage
    report = fns["render_report"]({
        "job_id": "job_local", "mode": "hybrid", "segments": enriched,
        "clusters": clustered.get("clusters") or [], "ranked_candidates": [],
        "output_format": "both",
    }, context)
    repeated = report["report_json"].get("repeated_footage") or []
    print("\n=== render_report ===")
    print("  repeated_footage:", [c["cluster_id"] for c in repeated] or "none")

    httpd.shutdown()

    # Verdict
    multi = [c for c in (clustered.get("clusters") or [])
             if len(c["segment_ids"]) > 1]
    ok_decode = analyzed.get("method") in ("shot_detection_pyav", "shot_detection")
    ok_phash = all(e["phashes"] for e in enriched) and bool(enriched)
    ok_cluster = bool(multi) if not args.video else True  # repeat only guaranteed
    print("\n=== VERDICT ===")
    print(f"  staged + decoded real file : {'OK' if ok_decode else 'FAIL'}")
    print(f"  real perceptual hashes     : {'OK' if ok_phash else 'FAIL'}")
    print(f"  clustered repeated footage : "
          f"{'OK' if ok_cluster else ('n/a' if args.video else 'FAIL')}")

    if not args.keep and not args.video:
        os.remove(dest)
        for p in os.listdir(tempfile.gettempdir()):
            if p == name:
                try:
                    os.remove(os.path.join(tempfile.gettempdir(), p))
                except OSError:
                    pass

    return 0 if (ok_decode and ok_phash and ok_cluster) else 1


if __name__ == "__main__":
    raise SystemExit(main())
