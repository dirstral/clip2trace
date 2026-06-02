"""Fetch metadata (and optionally bounded media) for Telegram candidates.

Designed around a dry-run/demo default: by default we only normalise metadata
that a search already returned and do NOT download bytes. Real downloads are
opt-in, bounded, and only happen on the live path with a Telethon client.
"""

from __future__ import annotations

from typing import Dict, List


def normalise_candidate(raw: Dict) -> Dict:
    """Normalise a raw search hit into the TelegramCandidate shape.

    Tolerant of missing fields; never raises on a malformed hit.
    """
    channel = raw.get("channel") or raw.get("chat")
    msg_id = raw.get("message_id") or raw.get("id")
    url = raw.get("url")
    if not url and channel and msg_id:
        url = f"https://t.me/{str(channel).lstrip('@')}/{msg_id}"
    return {
        "candidate_id": (
            raw.get("candidate_id") or f"{channel}_{msg_id}"
            if channel and msg_id
            else raw.get("candidate_id", "cand_unknown")
        ),
        "channel": channel,
        "message_id": msg_id,
        "url": url,
        "posted_at": raw.get("posted_at") or raw.get("date"),
        "caption": raw.get("caption") or raw.get("message") or "",
        "has_media": bool(raw.get("has_media", raw.get("media"))),
        "media_file_id": raw.get("media_file_id"),
        "is_forward": bool(raw.get("is_forward", raw.get("fwd_from"))),
        "forward_origin": raw.get("forward_origin"),
        "source_query": raw.get("source_query"),
        "accessible": raw.get("accessible", True),
    }


def fetch_candidate_media(
    candidates: List[Dict],
    *,
    dry_run: bool = True,
    live_client=None,
    max_media: int = 5,
    max_bytes: int = 8_000_000,
) -> Dict:
    """Fetch metadata for candidates; optionally download bounded media.

    In dry_run (default) we only normalise metadata. On a live download we cap
    both the number of items (`max_media`) and per-file size (`max_bytes`) to
    respect the 100 MB /tmp limit of Sinas function containers.
    """
    normalised = [normalise_candidate(c) for c in candidates]
    diagnostics: List[str] = []

    if dry_run or live_client is None:
        if not dry_run and live_client is None:
            diagnostics.append("media download skipped: no live client available.")
        return {
            "status": "metadata_only",
            "candidates": normalised,
            "downloaded": 0,
            "diagnostics": diagnostics,
        }

    downloaded = 0
    for cand in normalised[:max_media]:
        if not cand.get("has_media") or not cand.get("accessible"):
            continue
        try:
            file_id = live_client.download_media(cand, max_bytes=max_bytes)
            cand["media_file_id"] = file_id
            downloaded += 1
        except Exception as exc:
            cand["accessible"] = False
            diagnostics.append(f"download failed for {cand['candidate_id']}: {exc!r}")
    return {
        "status": "ok",
        "candidates": normalised,
        "downloaded": downloaded,
        "diagnostics": diagnostics,
    }
