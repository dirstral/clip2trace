"""search_global_telegram_posts — live Telethon search or demo/cached fallback.

NEVER silently pretend a live search ran. The live path requires a sharedPool
function so context["secrets"] holds TELEGRAM_API_ID/HASH/SESSION_STRING, and a
USER-account Telethon session (channels.searchPosts is user-only).
See docs/telegram-global-search.md.

Resolution order: manual_urls -> cached_results -> live (live/hybrid + secrets +
telethon) -> explicit live_unavailable / demo_no_data with diagnostics.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    context = context or {}
    mode = input_data.get("mode", "demo")
    queries = input_data.get("queries") or []

    # 1. Operator-provided links always win.
    manual = input_data.get("manual_urls") or []
    if manual:
        return {"status": "ok", "source": "manual_urls",
                "candidates": [{"candidate_id": f"manual_{i}", "url": u}
                               for i, u in enumerate(manual)]}

    # 2. Cached results (used by the demo).
    cached = input_data.get("cached_results")
    if cached is not None:
        return {"status": "ok", "source": "cached", "candidates": cached}

    # 3. Live search (only on live/hybrid, only with a usable client).
    if mode in ("live", "hybrid"):
        secrets = context.get("secrets") or {}
        allow_paid = bool(input_data.get("allow_paid_search", False))
        try:
            from clip2trace.telegram_live import build_client_from_secrets
            from clip2trace.telegram_search import search_posts
            client = build_client_from_secrets(secrets, allow_paid=allow_paid)
            if client is None:
                return {"status": "live_unavailable", "source": "none",
                        "candidates": [],
                        "diagnostics": ["missing Telegram secrets/session or "
                                        "telethon unavailable, or not a "
                                        "sharedPool/trusted function"]}
            result = search_posts(queries, mode=mode, live_client=client)
            diags = list(result.get("diagnostics", [])) + list(
                getattr(client, "diagnostics", []))
            return {"status": result.get("status", "ok"),
                    "source": result.get("source", "live"),
                    "candidates": result.get("candidates", []),
                    "diagnostics": diags}
        except Exception as exc:  # never crash; degrade visibly
            return {"status": "live_unavailable", "source": "none",
                    "candidates": [],
                    "diagnostics": [f"live search error: {exc!r}"]}

    # 4. Demo mode with no cached/manual data.
    return {"status": "demo_no_data", "source": "none", "candidates": [],
            "diagnostics": ["demo mode and no cached_results/manual_urls supplied"]}
