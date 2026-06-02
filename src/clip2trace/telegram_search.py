"""Telegram query generation + a search abstraction with live/demo modes.

`generate_queries` is pure and testable. `search_posts` is the seam between the
demo/cached path and the live Telethon path; the live path is intentionally
guarded so we NEVER silently pretend a live search ran. See
docs/telegram-global-search.md.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

HANDLE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{3,31})")
HASHTAG_RE = re.compile(r"#(\w{2,64})")

# Generic words we should not turn into standalone context queries.
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "video",
    "live",
    "breaking",
    "news",
    "watch",
    "today",
    "footage",
}


def extract_handles(text: str) -> List[str]:
    """Pull @handles out of free text, de-duplicated, order preserved."""
    seen, out = set(), []
    for m in HANDLE_RE.findall(text or ""):
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def extract_hashtags(text: str) -> List[str]:
    seen, out = set(), []
    for m in HASHTAG_RE.findall(text or ""):
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")


def derive_context_terms(text: str, limit: int = 8) -> List[str]:
    """Pull meaningful free-text terms (for `context` queries) from a blob.

    Strips @handles and #hashtags first (they have their own query families),
    drops stopwords and tokens shorter than 3 chars, de-duplicates
    case-insensitively, preserves order, and caps the result at `limit`.
    """
    cleaned = HASHTAG_RE.sub(" ", HANDLE_RE.sub(" ", text or ""))
    seen, out = set(), []
    for w in _WORD_RE.findall(cleaned):
        key = w.lower()
        if key in _STOPWORDS or key in seen:
            continue
        seen.add(key)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def generate_queries(clues: Dict) -> List[Dict]:
    """Turn segment clues into a small, ranked Telegram query set.

    Query families, in priority order:
      1 handle      — exact visible @handle (highest signal)
      2 ocr_exact   — exact OCR phrase
      3 context     — caption / context terms
      4 hashtag     — hashtags

    `clues` keys (all optional): visible_handles, ocr_text, context_terms,
    caption. Returns dicts matching schemas.TelegramQuery.
    """
    queries: List[Dict] = []
    seen = set()

    def add(query: str, qtype: str, priority: int, reason: str) -> None:
        q = (query or "").strip()
        if not q or q.lower() in seen:
            return
        seen.add(q.lower())
        queries.append(
            {"query": q, "query_type": qtype, "priority": priority, "reason": reason}
        )

    text_blob = " ".join(
        [
            clues.get("ocr_text", "") or "",
            clues.get("caption", "") or "",
            " ".join(clues.get("context_terms", []) or []),
        ]
    )

    # 1. Exact handles (from clue field + discovered in text).
    handles = list(clues.get("visible_handles", []) or [])
    handles += [h for h in extract_handles(text_blob) if h not in handles]
    for h in handles:
        add(
            f"@{h.lstrip('@')}",
            "handle",
            1,
            "Exact visible handle is the strongest retrieval signal.",
        )

    # 2. Exact OCR phrase (whole, if reasonably short).
    ocr = (clues.get("ocr_text") or "").strip()
    if 0 < len(ocr) <= 120:
        add(
            ocr,
            "ocr_exact",
            2,
            "Exact on-screen text should match a verbatim caption/overlay.",
        )

    # 3. Context terms (filtered).
    for term in clues.get("context_terms") or []:
        t = (term or "").strip()
        if len(t) >= 3 and t.lower() not in _STOPWORDS:
            add(t, "context", 3, "Contextual term to broaden retrieval.")

    # 4. Hashtags (free, unmetered global search path).
    for tag in extract_hashtags(text_blob):
        add(
            f"#{tag}",
            "hashtag",
            4,
            "Hashtag search is the unmetered global path on Telegram.",
        )

    queries.sort(key=lambda q: q["priority"])
    return queries


def search_posts(
    queries: List[Dict],
    *,
    mode: str = "demo",
    live_client=None,
    fallback_provider=None,
    cached_results: Optional[List[Dict]] = None,
    manual_urls: Optional[List[str]] = None,
) -> Dict:
    """Dispatch search across manual/live/third-party/cached paths.

    Returns {"status", "source", "candidates", "diagnostics"}. Resolution order
    on live/hybrid: live Telethon client -> `fallback_provider` (a managed
    third-party search adapter, issue #28) -> cached. Each is tried only if the
    prior is unavailable or errors; we always report why a path was skipped.
    """
    diagnostics: List[str] = []

    if manual_urls:
        cands = [
            {"candidate_id": f"manual_{i}", "url": u, "source": "manual"}
            for i, u in enumerate(manual_urls)
        ]
        return {
            "status": "ok",
            "source": "manual_urls",
            "candidates": cands,
            "diagnostics": diagnostics,
        }

    if mode in ("live", "hybrid") and live_client is not None:
        try:
            cands = live_client.search(queries)
            return {
                "status": "ok",
                "source": "live",
                "candidates": cands,
                "diagnostics": diagnostics,
            }
        except Exception as exc:  # never crash the pipeline on a flood-wait etc.
            diagnostics.append(f"live search failed: {exc!r}")
            # fall through to the third-party fallback / cached

    # Record why the direct path was skipped (before any fallback succeeds, so
    # the reason is always reported per the contract above).
    if mode in ("live", "hybrid") and live_client is None:
        diagnostics.append(
            "live search unavailable: no Telethon client (missing "
            "TELEGRAM_API_ID/HASH/SESSION_STRING or live not enabled)."
        )

    # Third-party managed search adapter — used when the direct Telethon path is
    # unavailable or failed (issue #28). Same `search(queries)` contract.
    if mode in ("live", "hybrid") and fallback_provider is not None:
        try:
            cands = fallback_provider.search(queries)
            return {
                "status": "ok",
                "source": "third_party",
                "candidates": cands,
                "diagnostics": diagnostics,
            }
        except Exception as exc:
            diagnostics.append(f"third-party search failed: {exc!r}")
            # fall through to cached/demo

    if cached_results is not None:
        return {
            "status": "ok",
            "source": "cached",
            "candidates": cached_results,
            "diagnostics": diagnostics,
        }

    return {
        "status": "live_unavailable" if mode != "demo" else "demo_no_data",
        "source": "none",
        "candidates": [],
        "diagnostics": diagnostics,
    }
