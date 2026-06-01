"""generate_telegram_queries — clues -> small ranked Telegram query set."""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    try:
        from clip2trace.telegram_search import generate_queries
        queries = generate_queries(input_data)
        return {"queries": queries}
    except Exception:
        # Self-contained fallback (mirrors sinas-package.yaml inline code).
        qs, seen = [], set()

        def add(q, t, p, r):
            k = (q or "").strip().lower()
            if q and k not in seen:
                seen.add(k)
                qs.append({"query": q, "query_type": t, "priority": p, "reason": r})

        for h in (input_data.get("visible_handles") or []):
            add("@" + str(h).lstrip("@"), "handle", 1, "Exact handle is strongest signal.")
        ocr = (input_data.get("ocr_text") or "").strip()
        if 0 < len(ocr) <= 120:
            add(ocr, "ocr_exact", 2, "Exact on-screen text.")
        for term in (input_data.get("context_terms") or []):
            add(term, "context", 3, "Contextual term.")
        qs.sort(key=lambda x: x["priority"])
        return {"queries": qs}
