"""fetch_telegram_candidate_media — metadata + optional bounded media (dry-run default)."""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    candidates = input_data.get("candidates") or []
    dry_run = input_data.get("dry_run", True)
    try:
        from clip2trace.telegram_media import fetch_candidate_media
        result = fetch_candidate_media(candidates, dry_run=dry_run, live_client=None)
        return result
    except Exception:
        out = []
        for c in candidates:
            ch, mid = c.get("channel"), c.get("message_id")
            url = c.get("url")
            if not url and ch and mid:
                url = f"https://t.me/{str(ch).lstrip('@')}/{mid}"
            out.append({"candidate_id": c.get("candidate_id", "cand_unknown"),
                        "url": url, "caption": c.get("caption", ""),
                        "has_media": bool(c.get("has_media")),
                        "accessible": c.get("accessible", True)})
        return {"status": "metadata_only", "candidates": out, "downloaded": 0}
