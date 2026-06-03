"""load_demo_corpus — read a pre-staged, pre-phashed channel corpus.

Regular-pool (NOT sharedPool) reader for the demo channel corpus, so a demo
never depends on the secrets-only sharedPool workers. Reads
clip2trace/demo-fixtures/<channel>_corpus.json via the files API (the same
mechanism analyze_input_video uses to stage videos) and returns its pre-phashed
candidates — NO Telegram calls, no rate-limit risk.
"""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    context = context or {}
    channel = input_data.get("channel")
    if not channel:
        return {
            "status": "error",
            "candidates": [],
            "diagnostics": ["channel is required"],
        }

    import base64
    import os
    from urllib.parse import quote

    token = context.get("access_token")
    if not token:
        return {
            "status": "unavailable",
            "candidates": [],
            "diagnostics": ["no access_token in context"],
        }
    base = (
        context.get("api_url")
        or context.get("base_url")
        or os.environ.get("SINAS_BASE_URL")
        or "http://host.docker.internal:8000"
    ).rstrip("/")
    fname = "%s_corpus.json" % str(channel).lstrip("@")
    try:
        import json as _json

        import requests

        url = "%s/files/clip2trace/demo-fixtures/%s" % (base, quote(fname, safe=""))
        resp = requests.get(
            url, timeout=30, headers={"Authorization": "Bearer %s" % token}
        )
        if resp.status_code != 200:
            return {
                "status": "unavailable",
                "candidates": [],
                "diagnostics": ["fixture %s -> HTTP %s" % (fname, resp.status_code)],
            }
        b64 = (resp.json() or {}).get("content_base64")
        data = _json.loads(base64.b64decode(b64).decode("utf-8"))
        cands = (data.get("candidates") if isinstance(data, dict) else data) or []
        return {
            "status": "ok",
            "source": "demo_fixture",
            "channel": channel,
            "candidates": cands,
            "diagnostics": [],
        }
    except Exception as exc:
        return {
            "status": "error",
            "candidates": [],
            "diagnostics": ["demo corpus read failed: %r" % (exc,)],
        }
