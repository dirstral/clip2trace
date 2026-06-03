"""enumerate_channel_videos — list a known channel's video posts (channel mode).

The channel-scoped counterpart to search_global_telegram_posts: instead of a
global text search, enumerate the videos of ONE known public channel directly
(Telethon iter_messages, catching .mkv documents too), so an input video can be
matched into the channel BY CONTENT — no premium, no caption dependency, no
global-index lag. Emits the same candidate dict shape the fetch→verify→rank→
render chain already consumes, each tagged channel_relevance=1.0 (it is, by
construction, from the chosen channel).

NEVER silently fake a live enumeration. The live path needs a sharedPool
function (context["secrets"] holds TELEGRAM_API_ID/HASH/SESSION_STRING) and a
USER-account Telethon session.

Resolution order: cached_results -> live (live/hybrid + secrets + telethon) ->
explicit live_unavailable / demo_no_data with diagnostics.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    context = context or {}
    mode = input_data.get("mode", "demo")
    channel = input_data.get("channel")
    max_videos = int(input_data.get("max_videos", 10) or 10)

    # 1. Cached results (used by the demo / tests).
    cached = input_data.get("cached_results")
    if cached is not None:
        return {"status": "ok", "source": "cached", "candidates": cached}

    # 2. Live enumeration (only on live/hybrid, only with a usable client).
    if mode in ("live", "hybrid"):
        if not channel:
            return {
                "status": "live_unavailable",
                "source": "none",
                "candidates": [],
                "diagnostics": ["no channel supplied for channel-scoped enumeration"],
            }
        secrets = context.get("secrets") or {}
        try:
            from clip2trace.telegram_live import build_client_from_secrets

            client = build_client_from_secrets(secrets)
            if client is None:
                return {
                    "status": "live_unavailable",
                    "source": "none",
                    "candidates": [],
                    "diagnostics": [
                        "missing Telegram secrets/session or telethon "
                        "unavailable, or not a sharedPool/trusted function"
                    ],
                }
            candidates = client.enumerate_channel(channel, max_videos=max_videos)
            return {
                "status": "ok",
                "source": "live",
                "candidates": candidates,
                "diagnostics": list(getattr(client, "diagnostics", [])),
            }
        except Exception as exc:  # never crash; degrade visibly
            return {
                "status": "live_unavailable",
                "source": "none",
                "candidates": [],
                "diagnostics": [f"channel enumeration error: {exc!r}"],
            }

    # 3. Demo mode with no cached data.
    return {
        "status": "demo_no_data",
        "source": "none",
        "candidates": [],
        "diagnostics": ["demo mode and no cached_results supplied"],
    }
