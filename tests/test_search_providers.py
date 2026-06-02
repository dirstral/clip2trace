"""Tests for the third-party search fallback adapter (#28). No network."""

from clip2trace.telegram_search import search_posts
from clip2trace.telegram_search_providers import (
    HttpSearchAdapter,
    build_search_fallback_from_secrets,
    default_build_request,
    default_parse_results,
)

QUERIES = [
    {"query": "@demo_channel", "query_type": "handle", "priority": 1},
    {"query": "protest", "query_type": "context", "priority": 3},
]


def _fake_post(captured):
    def post(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return {
            "results": [
                {
                    "channel": "demo_channel",
                    "message_id": 7,
                    "caption": "hi",
                    "has_media": True,
                }
            ]
        }

    return post


# --------------------------- pure helpers ---------------------------


def test_default_build_request_collects_terms():
    body = default_build_request(QUERIES, limit=10)
    assert body == {"q": ["@demo_channel", "protest"], "limit": 10}


def test_default_parse_results_normalises():
    out = default_parse_results({"results": [{"channel": "c", "message_id": 4}]})
    assert out[0]["url"] == "https://t.me/c/4"
    assert out[0]["candidate_id"] == "c_4"
    # the parser itself does not tag source; the adapter does (see search()).
    assert "source" not in out[0]


def test_default_parse_results_caption_from_message():
    out = default_parse_results(
        {"results": [{"channel": "c", "message_id": 1, "message": "hello"}]}
    )
    assert out[0]["caption"] == "hello"


def test_default_parse_results_tolerates_garbage():
    assert default_parse_results(None) == []
    assert default_parse_results({"results": []}) == []


# --------------------------- adapter ---------------------------


def test_adapter_search_calls_endpoint_and_maps():
    captured = {}
    ad = HttpSearchAdapter("https://svc.example/", "k3y", post=_fake_post(captured))
    cands = ad.search(QUERIES)
    assert captured["url"] == "https://svc.example/search"
    assert captured["headers"]["Authorization"] == "Bearer k3y"
    assert captured["body"]["q"] == ["@demo_channel", "protest"]
    assert cands[0]["candidate_id"] == "demo_channel_7"
    assert cands[0]["url"] == "https://t.me/demo_channel/7"
    assert cands[0]["source"] == "third_party"


def test_adapter_custom_request_and_parser():
    captured = {}

    def post(url, headers, body):
        captured["body"] = body
        return {"hits": [{"id": 1, "chan": "x"}]}

    ad = HttpSearchAdapter(
        "https://svc",
        "k",
        post=post,
        build_request=lambda qs, *, limit: {"query": " ".join(q["query"] for q in qs)},
        parse_results=lambda p: [{"candidate_id": str(h["id"])} for h in p["hits"]],
    )
    out = ad.search(QUERIES)
    assert captured["body"] == {"query": "@demo_channel protest"}
    # adapter tags source (= its name) even when the custom parser omits it.
    assert out == [{"candidate_id": "1", "source": "third_party"}]


# --------------------------- build from secrets ---------------------------


def test_build_none_without_config():
    assert build_search_fallback_from_secrets({}) is None
    assert build_search_fallback_from_secrets({"TELEGRAM_SEARCH_API_URL": "u"}) is None
    assert build_search_fallback_from_secrets({"TELEGRAM_SEARCH_API_KEY": "k"}) is None


def test_build_adapter_when_configured():
    ad = build_search_fallback_from_secrets(
        {"TELEGRAM_SEARCH_API_URL": "https://s", "TELEGRAM_SEARCH_API_KEY": "k"}
    )
    assert isinstance(ad, HttpSearchAdapter)
    assert ad.base_url == "https://s" and ad.api_key == "k"


# --------------------------- search_posts integration ---------------------------


class _Provider:
    def __init__(self, result=None, raises=None):
        self.result = result or [{"candidate_id": "tp1", "source": "third_party"}]
        self.raises = raises
        self.called = False

    def search(self, queries):
        self.called = True
        if self.raises:
            raise self.raises
        return self.result


def test_fallback_used_when_no_live_client():
    prov = _Provider()
    out = search_posts(QUERIES, mode="live", fallback_provider=prov)
    assert prov.called and out["source"] == "third_party"
    assert out["candidates"][0]["candidate_id"] == "tp1"


def test_fallback_used_when_live_errors():
    class _BadLive:
        def search(self, q):
            raise RuntimeError("flood")

    prov = _Provider()
    out = search_posts(
        QUERIES, mode="hybrid", live_client=_BadLive(), fallback_provider=prov
    )
    assert out["source"] == "third_party"
    assert any("live search failed" in d for d in out["diagnostics"])


def test_fallback_error_falls_through_to_cached():
    prov = _Provider(raises=RuntimeError("provider down"))
    out = search_posts(
        QUERIES,
        mode="live",
        fallback_provider=prov,
        cached_results=[{"candidate_id": "c1"}],
    )
    assert out["source"] == "cached"
    assert any("third-party search failed" in d for d in out["diagnostics"])


def test_demo_mode_does_not_call_fallback():
    prov = _Provider()
    out = search_posts(QUERIES, mode="demo", fallback_provider=prov)
    assert not prov.called
    assert out["status"] == "demo_no_data"
