"""fetch_telegram_candidate_media — metadata + optional bounded media.

Dry-run by default (metadata only). A real download requires `dry_run: false`,
a sharedPool function (so context["secrets"] holds the Telegram credentials), and
Telethon. Downloads are bounded by per-file size, item count, and a total /tmp
byte budget. Inaccessible/private/deleted media is marked, never fatal.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    context = context or {}
    candidates = input_data.get("candidates") or []
    dry_run = input_data.get("dry_run", True)
    max_media = int(input_data.get("max_media", 10) or 10)
    max_bytes = int(input_data.get("max_bytes", 52_428_800) or 52_428_800)
    total_budget = int(input_data.get("total_budget", 300_000_000) or 300_000_000)

    live_client = None
    if not dry_run:
        try:
            from clip2trace.telegram_live import build_client_from_secrets

            live_client = build_client_from_secrets(context.get("secrets") or {})
        except Exception:
            live_client = None

    try:
        from clip2trace.telegram_media import fetch_candidate_media

        return fetch_candidate_media(
            candidates,
            dry_run=dry_run,
            live_client=live_client,
            max_media=max_media,
            max_bytes=max_bytes,
            total_budget=total_budget,
        )
    except Exception as exc:
        # Self-contained metadata-only fallback (mirrors the inline YAML block).
        # Surface the cause so import/packaging regressions are diagnosable.
        out = []
        for c in candidates:
            ch, mid = c.get("channel"), c.get("message_id")
            url = c.get("url")
            if not url and ch and mid:
                url = f"https://t.me/{str(ch).lstrip('@')}/{mid}"
            out.append(
                {
                    "candidate_id": c.get("candidate_id", "cand_unknown"),
                    "url": url,
                    "caption": c.get("caption", ""),
                    "has_media": bool(c.get("has_media")),
                    "accessible": c.get("accessible", True),
                }
            )
        return {
            "status": "metadata_only",
            "candidates": out,
            "downloaded": 0,
            "diagnostics": [f"fell back to metadata-only: {exc!r}"],
        }
