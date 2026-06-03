#!/usr/bin/env python3
"""Enumerate a public Telegram channel's videos, segment + phash each locally,
and report footage reused ACROSS the channel's posts.

This is the *channel-scoped* counterpart to the global text-search pipeline: it
lists the channel's video messages directly (Telethon `iter_messages` with the
video filter — no global index, no premium, no caption matching), downloads each
(bounded), and runs the SAME pip-only video path the Sinas worker uses
(PyAV+numpy color-histogram shot detector + Pillow/imagehash perceptual hashes).
Because there is no separate "input" video to trace, the meaningful result is
**cross-video reuse**: `cluster_segments` over the union of every channel video's
segments flags which posts share the same footage.

Local dev/inspection tool — uses the premium `.env` Telegram session, downloads
to a temp dir, makes NO changes to the Sinas instance, and costs $0 (no LLM/OCR).

Usage:
    # TELEGRAM_API_ID / API_HASH / SESSION_STRING in .env (gitignored)
    uv run --extra video --extra telegram python scripts/enumerate_channel.py \
        --channel clip2trace
    uv run ... python scripts/enumerate_channel.py --channel clip2trace \
        --max 10 --keep-dir /tmp/clip2trace_channel
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

# Mirror the Sinas worker (no opencv/scenedetect there) -> force the PyAV+numpy
# path. Safe before importing clip2trace: the detector reads sys.modules at call
# time, and none of the imports below pull cv2.
sys.modules["cv2"] = None
sys.modules["scenedetect"] = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from clip2trace.matching import cluster_segments  # noqa: E402
from clip2trace.video import (  # noqa: E402
    center_crop_phash,
    detect_shots,
    extract_keyframes,
    phash_of_frame,
    windows_to_segments,
)

# Bounds (this downloads real media — stay courteous + bounded).
MAX_VIDEOS = 10
MAX_FILE_BYTES = 90_000_000  # per-file cap
MAX_TOTAL_BYTES = 300_000_000  # total across the run
KEYFRAMES_PER_SEGMENT = 3
# Cap how many recent messages we scan to find video-like media.
SCAN_LIMIT = 300
VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".webm", ".avi", ".m4v")


def _load_dotenv() -> None:
    """Populate the three TELEGRAM_* vars from repo-root .env if not in env."""
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return
    wanted = {"TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("'\"")
                if key in wanted and not os.environ.get(key):
                    os.environ[key] = val
    except Exception:
        pass


def _segment_video(path: str) -> list[dict]:
    """Detect shots (PyAV color-histogram), then phash each segment's keyframes."""
    windows = detect_shots(path)
    segments = windows_to_segments(windows)
    for seg in segments:
        phashes: list[str] = []
        try:
            frames = extract_keyframes(
                path, seg["start_sec"], seg["end_sec"], KEYFRAMES_PER_SEGMENT
            )
            for fr in frames:
                for h in (phash_of_frame(fr), center_crop_phash(fr)):
                    if h:
                        phashes.append(h)
        except Exception as exc:  # never let one segment break the run
            seg["phash_error"] = repr(exc)
        seg["phashes"] = phashes
    return segments


def _is_video_like(msg) -> bool:
    """True for a video message OR a document that is video by mime/extension.

    Telegram posts `.mkv` as a *document*, not a streamable video message, so
    `InputMessagesFilterVideo` alone misses them — match on mime/extension too.
    """
    if getattr(msg, "video", None) is not None:
        return True
    f = getattr(msg, "file", None)
    if f is None:
        return False
    mime = (getattr(f, "mime_type", None) or "").lower()
    if mime.startswith("video/"):
        return True
    name = (getattr(f, "name", None) or "").lower()
    ext = (getattr(f, "ext", None) or "").lower()
    return name.endswith(VIDEO_EXTS) or ext in VIDEO_EXTS


def enumerate_and_segment(channel: str, max_videos: int, dest_dir: str) -> list[dict]:
    from telethon.sessions import StringSession
    from telethon.sync import TelegramClient

    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session = os.environ["TELEGRAM_SESSION_STRING"]

    videos: list[dict] = []
    spent = 0
    with TelegramClient(StringSession(session), api_id, api_hash) as client:
        entity = client.get_entity(channel)
        title = getattr(entity, "title", channel)
        username = getattr(entity, "username", None)
        print(
            f"channel: {title} (@{username})  "
            f"scanning up to {SCAN_LIMIT} msgs for video media  max={max_videos}"
        )
        # Scan recent messages (no server-side filter, so video *documents* like
        # .mkv are included) and pick the video-like ones up to max_videos.
        for msg in client.iter_messages(entity, limit=SCAN_LIMIT):
            if len(videos) >= max_videos:
                break
            if not getattr(msg, "media", None) or not _is_video_like(msg):
                continue
            mid = msg.id
            size = getattr(getattr(msg, "file", None), "size", None)
            if size and size > MAX_FILE_BYTES:
                print(f"  msg {mid}: {size} bytes over per-file cap, skipping")
                continue
            if size and spent + size > MAX_TOTAL_BYTES:
                print("  total byte budget reached, stopping")
                break
            print(f"  msg {mid}: downloading ({size or '?'} bytes)...")
            local = client.download_media(msg, file=dest_dir)
            if not local:
                print(f"  msg {mid}: no downloadable media, skipping")
                continue
            try:
                spent += os.path.getsize(local)
            except OSError:
                pass
            segments = _segment_video(local)
            url = f"https://t.me/{username}/{mid}" if username else None
            videos.append(
                {
                    "message_id": mid,
                    "url": url,
                    "caption": (msg.message or "")[:80],
                    "path": local,
                    "segments": segments,
                }
            )
            print(f"  msg {mid}: {len(segments)} segment(s)")
    return videos


def report(videos: list[dict]) -> None:
    print("\n" + "=" * 70)
    print(f"ENUMERATED {len(videos)} video(s)")
    print("=" * 70)

    union: list[dict] = []
    for v in videos:
        print(f"\n• msg {v['message_id']}  {v['url'] or ''}")
        if v["caption"]:
            print(f"  caption: {v['caption']!r}")
        for seg in v["segments"]:
            tag = f"{v['message_id']}:{seg['segment_id']}"
            print(
                f"    {tag:>16}  [{seg['start_sec']:6.2f}-{seg['end_sec']:6.2f}s]  "
                f"phashes={len(seg.get('phashes') or [])}"
            )
            # Namespace the segment id by message so the cross-video cluster can
            # report which post each segment came from.
            union.append({**seg, "segment_id": tag})

    clusters = cluster_segments(union)
    multi = [c for c in clusters if len(c["segment_ids"]) > 1]

    def _msg(seg_id: str) -> str:
        return seg_id.split(":", 1)[0]

    # A cluster is cross-post only if its segments span >1 distinct message.
    cross = [c for c in multi if len({_msg(s) for s in c["segment_ids"]}) > 1]
    within = [c for c in multi if c not in cross]

    print("\n" + "-" * 70)
    print("CROSS-POST REUSE (same footage in two DIFFERENT channel posts)")
    print("-" * 70)
    if not cross:
        print("  none — no segment visually matched a segment in another post.")
    else:
        for c in cross:
            print(f"  {c['cluster_id']}: {', '.join(c['segment_ids'])}")

    print("\n" + "-" * 70)
    print("WITHIN-POST REPEATS (same shot repeated inside one compilation)")
    print("-" * 70)
    if not within:
        print("  none.")
    else:
        for c in within:
            print(f"  {c['cluster_id']}: {', '.join(c['segment_ids'])}")

    print(
        f"\n  ({len(clusters)} cluster(s) over {len(union)} segment(s); "
        f"{len(cross)} cross-post, {len(within)} within-post)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--channel",
        default="clip2trace",
        help="channel @username or t.me link (default: clip2trace)",
    )
    ap.add_argument("--max", type=int, default=MAX_VIDEOS, help="max videos to pull")
    ap.add_argument(
        "--keep-dir",
        default=None,
        help="download dir to keep (default: a temp dir, removed on exit)",
    )
    args = ap.parse_args()

    _load_dotenv()
    missing = [
        k
        for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"ERROR: missing env/.env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    if args.keep_dir:
        os.makedirs(args.keep_dir, exist_ok=True)
        videos = enumerate_and_segment(args.channel, args.max, args.keep_dir)
        report(videos)
    else:
        with tempfile.TemporaryDirectory(prefix="clip2trace_channel_") as tmp:
            videos = enumerate_and_segment(args.channel, args.max, tmp)
            report(videos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
