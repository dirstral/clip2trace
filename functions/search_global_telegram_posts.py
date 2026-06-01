"""search_global_telegram_posts — live Telethon search or demo/cached fallback.

NEVER silently pretend a live search ran. The live path requires a sharedPool
function so context["secrets"] holds TELEGRAM_API_ID/HASH/SESSION_STRING, and a
USER-account Telethon session (channels.searchPosts is user-only).
See docs/telegram-global-search.md.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    context = context or {}
    mode = input_data.get("mode", "demo")

    manual = input_data.get("manual_urls") or []
    if manual:
        return {"status": "ok", "source": "manual_urls",
                "candidates": [{"candidate_id": f"manual_{i}", "url": u}
                               for i, u in enumerate(manual)]}

    cached = input_data.get("cached_results")
    if cached is not None:
        return {"status": "ok", "source": "cached", "candidates": cached}

    secrets = context.get("secrets") or {}
    have_creds = all(secrets.get(k) for k in
                     ("TELEGRAM_API_ID", "TELEGRAM_API_HASH",
                      "TELEGRAM_SESSION_STRING"))

    if mode in ("live", "hybrid"):
        if not have_creds:
            return {"status": "live_unavailable", "candidates": [],
                    "diagnostics": ["missing Telegram secrets or not a "
                                    "sharedPool/trusted function"]}
        # Live Telethon search via functions.channels.SearchPostsRequest goes
        # here. Must handle FloodWaitError and the free-text paid-search quota.
        return {"status": "not_implemented", "candidates": [],
                "diagnostics": ["live Telethon search stub; see issue "
                                "'Implement global Telegram post search function'"]}

    return {"status": "demo_no_data", "candidates": [],
            "diagnostics": ["demo mode and no cached_results/manual_urls supplied"]}
