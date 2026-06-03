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

    # 3. Demo mode: serve a pre-staged, pre-phashed channel corpus from the
    # clip2trace/demo-fixtures collection (file: <channel>_corpus.json), so the
    # channel pipeline can be demoed end-to-end with NO live Telegram calls and
    # zero rate-limit risk. Reads via the files API (same path
    # analyze_input_video uses to stage videos).
    if channel:
        import base64
        import json as _json
        import os
        from urllib.parse import quote

        token = context.get("access_token")
        if token:
            base = (
                context.get("api_url")
                or context.get("base_url")
                or os.environ.get("SINAS_BASE_URL")
                or "http://host.docker.internal:8000"
            ).rstrip("/")
            fname = "%s_corpus.json" % str(channel).lstrip("@")
            try:
                import requests

                url = "%s/files/clip2trace/demo-fixtures/%s" % (
                    base,
                    quote(fname, safe=""),
                )
                resp = requests.get(
                    url, timeout=30, headers={"Authorization": "Bearer %s" % token}
                )
                if resp.status_code == 200:
                    b64 = (resp.json() or {}).get("content_base64")
                    if b64:
                        data = _json.loads(base64.b64decode(b64).decode("utf-8"))
                        cands = (
                            data.get("candidates") if isinstance(data, dict) else data
                        ) or []
                        if cands:
                            return {
                                "status": "ok",
                                "source": "demo_fixture",
                                "candidates": cands[:max_videos],
                                "diagnostics": [],
                            }
            except Exception as exc:
                return {
                    "status": "demo_no_data",
                    "source": "none",
                    "candidates": [],
                    "diagnostics": [f"demo fixture read failed: {exc!r}"],
                }

    # 4. Demo mode with no fixture / no cached data.
    return {
        "status": "demo_no_data",
        "source": "none",
        "candidates": [],
        "diagnostics": ["demo mode and no cached_results/fixture supplied"],
    }
