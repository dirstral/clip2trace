"""Tests for the live Telegram search engine.

Pure helpers are tested directly. The Telethon glue (`TelethonSearchClient.search`)
is exercised against a fake `telethon` injected into sys.modules, so no real
network or library is needed.
"""

import sys
import types as pytypes
from datetime import datetime, timezone

import pytest

from clip2trace.telegram_live import (
    route_query, is_free_text, normalize_message, accumulate,
    _index_chats, _peer_channel_id, build_client_from_secrets,
    TelethonSearchClient,
)


# --------------------------- pure helpers ---------------------------

def test_route_query_hashtag_by_type():
    assert route_query({"query": "#breaking", "query_type": "hashtag"}) == ("breaking", None)


def test_route_query_hashtag_by_prefix():
    assert route_query({"query": "#war", "query_type": "context"}) == ("war", None)


def test_route_query_free_text():
    assert route_query({"query": "@demo_channel", "query_type": "handle"}) == (None, "@demo_channel")


def test_route_query_empty():
    assert route_query({"query": "  ", "query_type": "context"}) == (None, None)


def test_is_free_text():
    assert is_free_text(None, "x") is True
    assert is_free_text("tag", None) is False


def _msg(mid, channel_id=999, media=True, fwd=False, caption="hi"):
    return pytypes.SimpleNamespace(
        id=mid, message=caption,
        date=datetime(2026, 5, 20, 8, 14, tzinfo=timezone.utc),
        peer_id=pytypes.SimpleNamespace(channel_id=channel_id),
        media=object() if media else None,
        fwd_from=object() if fwd else None,
    )


def _chat(cid=999, username="demo_channel", title="Demo"):
    return pytypes.SimpleNamespace(id=cid, username=username, title=title)


def test_normalize_message_full():
    chats = _index_chats([_chat()])
    cand = normalize_message(_msg(4521), chats, source_query="@demo_channel")
    assert cand["candidate_id"] == "demo_channel_4521"
    assert cand["channel"] == "demo_channel"
    assert cand["url"] == "https://t.me/demo_channel/4521"
    assert cand["posted_at"] == "2026-05-20T08:14:00+00:00"
    assert cand["has_media"] is True
    assert cand["is_forward"] is False
    assert cand["source_query"] == "@demo_channel"


def test_normalize_message_unknown_channel():
    cand = normalize_message(_msg(1, channel_id=None, media=False), {}, None)
    assert cand["channel"] is None
    assert cand["url"] is None
    assert cand["has_media"] is False
    assert cand["candidate_id"] == "unknown_1"


def test_peer_channel_id():
    assert _peer_channel_id(pytypes.SimpleNamespace(channel_id=7)) == 7
    assert _peer_channel_id(None) is None


def test_accumulate_dedup_and_budget():
    pages = [[{"candidate_id": "a"}, {"candidate_id": "b"}],
             [{"candidate_id": "b"}, {"candidate_id": "c"}]]
    assert [c["candidate_id"] for c in accumulate(pages, max_results=10)] == ["a", "b", "c"]
    assert len(accumulate(pages, max_results=2)) == 2


# --------------------------- build_client ---------------------------

def test_build_client_none_without_secrets():
    assert build_client_from_secrets({}) is None
    assert build_client_from_secrets({"TELEGRAM_API_ID": "1"}) is None  # incomplete


# --------------------------- fake telethon glue ---------------------------

class _FakeClient:
    """Context-manager client that answers flood + search requests from canned pages."""

    def __init__(self, pages, flood_remaining=10):
        self.pages = pages
        self.flood_remaining = flood_remaining
        self.calls = []
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __call__(self, req):
        kind = req[0]
        if kind == "flood":
            return pytypes.SimpleNamespace(remaining=self.flood_remaining)
        # search
        self.calls.append(req[1])
        if self._i >= len(self.pages):
            return pytypes.SimpleNamespace(messages=[], chats=[], next_rate=None)
        msgs, chats, next_rate = self.pages[self._i]
        self._i += 1
        return pytypes.SimpleNamespace(messages=msgs, chats=chats, next_rate=next_rate)


@pytest.fixture
def fake_telethon():
    """Inject a minimal fake `telethon` + `telethon.errors` for the glue."""
    class _Channels:
        def SearchPostsRequest(self, **kw):
            return ("search", kw)

        def CheckSearchPostsFloodRequest(self):
            return ("flood",)

    tele = pytypes.ModuleType("telethon")
    tele.functions = pytypes.SimpleNamespace(channels=_Channels())
    tele.types = pytypes.SimpleNamespace(InputPeerEmpty=lambda: "EMPTY")
    errors = pytypes.ModuleType("telethon.errors")

    class FloodWaitError(Exception):
        def __init__(self, seconds=0):
            self.seconds = seconds

    errors.FloodWaitError = FloodWaitError
    saved = {k: sys.modules.get(k) for k in ("telethon", "telethon.errors")}
    sys.modules["telethon"] = tele
    sys.modules["telethon.errors"] = errors
    try:
        yield FloodWaitError
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_search_paginates_and_dedups(fake_telethon):
    chats = [_chat()]
    pages = [([_msg(10), _msg(11)], chats, 5),
             ([_msg(11), _msg(12)], chats, None)]  # 11 repeats -> deduped
    client = _FakeClient(pages)
    sc = TelethonSearchClient(lambda: client)
    cands = sc.search([{"query": "protest", "query_type": "context"}])
    assert [c["candidate_id"] for c in cands] == ["demo_channel_10", "demo_channel_11", "demo_channel_12"]
    # free-text query routed to the `query` param, not `hashtag`
    assert client.calls[0]["query"] == "protest" and client.calls[0]["hashtag"] is None


def test_search_skips_metered_when_no_slots(fake_telethon):
    client = _FakeClient([], flood_remaining=0)
    sc = TelethonSearchClient(lambda: client)
    cands = sc.search([{"query": "protest", "query_type": "context"}])
    assert cands == []
    assert any("skipped metered free-text" in d for d in sc.diagnostics)


def test_search_hashtag_is_unmetered(fake_telethon):
    pages = [([_msg(20)], [_chat()], None)]
    client = _FakeClient(pages, flood_remaining=0)  # no slots, but hashtag is free
    sc = TelethonSearchClient(lambda: client)
    cands = sc.search([{"query": "#breaking", "query_type": "hashtag"}])
    assert [c["candidate_id"] for c in cands] == ["demo_channel_20"]
    assert client.calls[0]["hashtag"] == "breaking" and client.calls[0]["query"] is None


def test_search_handles_flood_wait(fake_telethon):
    FloodWaitError = fake_telethon

    class _Flooder(_FakeClient):
        def __call__(self, req):
            if req[0] == "flood":
                return pytypes.SimpleNamespace(remaining=10)
            raise FloodWaitError(seconds=30)

    sc = TelethonSearchClient(lambda: _Flooder([]))
    cands = sc.search([{"query": "protest", "query_type": "context"}])
    assert cands == []
    assert any("flood wait" in d for d in sc.diagnostics)


# --------------------------- function handler branches ---------------------------

import importlib.util  # noqa: E402
import os  # noqa: E402

_FUNC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "functions", "search_global_telegram_posts.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("fn_search", _FUNC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


def test_handler_manual_urls():
    out = _load_handler()({"manual_urls": ["https://t.me/x/1"]}, {})
    assert out["status"] == "ok" and out["source"] == "manual_urls"
    assert out["candidates"][0]["url"] == "https://t.me/x/1"


def test_handler_cached():
    out = _load_handler()({"cached_results": [{"candidate_id": "c1"}]}, {})
    assert out["status"] == "ok" and out["source"] == "cached"


def test_handler_demo_no_data():
    out = _load_handler()({"mode": "demo"}, {})
    assert out["status"] == "demo_no_data" and out["candidates"] == []


def test_handler_live_unavailable_without_secrets():
    out = _load_handler()({"mode": "live", "queries": []}, {"secrets": {}})
    assert out["status"] == "live_unavailable"
    assert any("missing Telegram secrets" in d for d in out["diagnostics"])
