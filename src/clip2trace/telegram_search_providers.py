"""Pluggable third-party search providers — a fallback for the direct Telethon
path when it is unavailable or flaky (issue #28).

A *provider* duck-types ``search(queries: list[dict]) -> list[dict]`` — the same
contract as ``TelethonSearchClient`` and the ``live_client`` used by
``telegram_search.search_posts`` — so a provider slots into the existing seam
with no pipeline changes.

``HttpSearchAdapter`` is a generic, provider-agnostic HTTP adapter: the concrete
service's request/response shape is supplied via ``build_request`` /
``parse_results`` callables, so a specific provider implementation is **optional
and swappable**. The base URL + API key come from Sinas secrets (read in a
sharedPool function). Results are normalised to the ``TelegramCandidate`` shape
(see docs/data-model.md) and tagged ``source: "third_party"``.

This is *retrieval, not proof* — exactly like the direct path — so downstream
visual verification still decides. See docs/telegram-global-search.md.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

# Sinas secret/variable names for the optional managed search provider.
SEARCH_API_URL_VAR = "TELEGRAM_SEARCH_API_URL"
SEARCH_API_KEY_SECRET = "TELEGRAM_SEARCH_API_KEY"


def default_build_request(queries: List[Dict], *, limit: int) -> Dict:
    """Default request body: the query terms + a result limit.

    Override per provider via ``build_request`` for a service-specific shape.
    """
    terms = [q.get("query") for q in (queries or []) if q.get("query")]
    return {"q": terms, "limit": limit}


def default_parse_results(payload) -> List[Dict]:
    """Default response parser → list of TelegramCandidate-shaped dicts.

    Expects ``{"results": [{channel, message_id, url, caption, ...}]}``. Override
    per provider via ``parse_results``. Tolerant of missing fields.
    """
    results = payload.get("results", []) if isinstance(payload, dict) else []
    out: List[Dict] = []
    for i, r in enumerate(results):
        ch = r.get("channel") or r.get("chat")
        mid = r.get("message_id") or r.get("id")
        url = r.get("url")
        if not url and ch and mid:
            url = f"https://t.me/{str(ch).lstrip('@')}/{mid}"
        out.append(
            {
                "candidate_id": r.get("candidate_id")
                or (f"{ch}_{mid}" if ch and mid else f"thirdparty_{i}"),
                "channel": ch,
                "message_id": mid,
                "url": url,
                "posted_at": r.get("posted_at") or r.get("date"),
                "caption": r.get("caption") or r.get("text") or r.get("message") or "",
                "has_media": bool(r.get("has_media", r.get("media"))),
                "is_forward": bool(r.get("is_forward")),
                "accessible": r.get("accessible", True),
                "source_query": r.get("source_query"),
            }
        )
    return out


class HttpSearchAdapter:
    """Generic HTTP search provider conforming to the ``search(queries)`` contract.

    ``post(url, headers, json_body) -> dict`` is injectable for tests; when None a
    real ``requests.post`` is used. ``build_request`` / ``parse_results`` make the
    concrete provider's wire format pluggable. Never spends Telegram resources —
    it talks to a managed search service, not Telegram directly.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        name: str = "third_party",
        path: str = "/search",
        limit: int = 50,
        timeout: float = 30.0,
        post: Optional[Callable] = None,
        build_request: Optional[Callable] = None,
        parse_results: Optional[Callable] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.name = name
        self.path = path
        self.limit = limit
        self.timeout = timeout
        self._post = post
        self._build_request = build_request or default_build_request
        self._parse_results = parse_results or default_parse_results

    def search(self, queries: List[Dict]) -> List[Dict]:
        body = self._build_request(queries or [], limit=self.limit)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = self.base_url + self.path
        if self._post is not None:
            payload = self._post(url, headers, body)
        else:
            import requests  # type: ignore

            resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        candidates = self._parse_results(payload)
        # Tag provenance consistently even if a custom parser omits it.
        for c in candidates:
            c.setdefault("source", self.name)
        return candidates


def build_search_fallback_from_secrets(
    secrets: Optional[Dict], *, post: Optional[Callable] = None, **kwargs
) -> Optional[HttpSearchAdapter]:
    """Build the fallback provider from Sinas secrets, or None if unconfigured.

    Returns None (never raises) when the base URL or API key is absent, so the
    caller simply skips the fallback rather than failing.
    """
    secrets = secrets or {}
    url = secrets.get(SEARCH_API_URL_VAR)
    key = secrets.get(SEARCH_API_KEY_SECRET)
    if not (url and key):
        return None
    return HttpSearchAdapter(url, key, post=post, **kwargs)
