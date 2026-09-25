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
        "phashes": list(raw.get("phashes") or []),
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
    max_media: int = 10,
    max_bytes: int = 52_428_800,
    total_budget: int = 300_000_000,
) -> Dict:
    """Fetch metadata for candidates; optionally download bounded media.

    In dry_run (default) we only normalise metadata. On a live download we cap
    the number of items (`max_media`), per-file size (`max_bytes`), and the total
    downloaded bytes (`total_budget`). Each file is deleted right after phashing,
    so peak /tmp is a single file — the per-file cap (default 50 MB) is what must
    stay under the 100 MB container limit, not the sum.
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

    # Preferred: a client that downloads many candidates over one connection
    # while enforcing per-file + total-/tmp byte budgets.
    if hasattr(live_client, "download_candidates"):
        res = live_client.download_candidates(
            normalised,
            max_media=max_media,
            max_bytes=max_bytes,
            total_budget=total_budget,
        )
        return {
            "status": "ok",
            "candidates": res.get("candidates", normalised),
            "downloaded": res.get("downloaded", 0),
            "diagnostics": diagnostics + list(res.get("diagnostics", [])),
        }

    # Fallback: per-candidate download_media(cand, max_bytes=...).
    downloaded = 0
    for cand in normalised[:max_media]:
        if not cand.get("has_media") or not cand.get("accessible"):
            continue
        try:
            file_id = live_client.download_media(cand, max_bytes=max_bytes)
            cand["media_file_id"] = file_id
            # Compute candidate phashes so visual verification has input (the
            # primary download_candidates path does the same).
            try:
                from clip2trace.video import phashes_for_media

                ph = phashes_for_media(file_id) if file_id else []
                if ph:
                    cand["phashes"] = list(cand.get("phashes") or []) + ph
            except Exception as exc:
                diagnostics.append(f"phash failed for {cand['candidate_id']}: {exc!r}")
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
