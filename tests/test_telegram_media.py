"""Tests for bounded Telegram media fetching (#14).

Pure helpers tested directly. `download_candidates` is exercised against a fake
Telethon client + a stubbed `telethon.errors` — no network or real library.
"""

import importlib.util
import os
import sys
import types as pytypes

import pytest

from clip2trace.telegram_live import (
    media_within_cap, MAX_MEDIA_BYTES, TelethonSearchClient,
)
from clip2trace.telegram_media import normalise_candidate, fetch_candidate_media


# --------------------------- pure helpers ---------------------------

def test_media_within_cap():
    assert media_within_cap(None) is True            # unknown size allowed
    assert media_within_cap(1000, 8000) is True
    assert media_within_cap(9000, 8000) is False
    assert media_within_cap(MAX_MEDIA_BYTES) is True


def test_normalise_candidate_builds_url():
    c = normalise_candidate({"channel": "demo", "message_id": 5})
    assert c["url"] == "https://t.me/demo/5"
    assert c["accessible"] is True and c["has_media"] is False


def test_fetch_dry_run_is_metadata_only():
    out = fetch_candidate_media([{"channel": "demo", "message_id": 1, "has_media": True}])
    assert out["status"] == "metadata_only" and out["downloaded"] == 0


def test_fetch_not_dry_run_without_client_is_metadata_only():
    out = fetch_candidate_media([{"channel": "d", "message_id": 1}],
                                dry_run=False, live_client=None)
    assert out["status"] == "metadata_only"
    assert any("no live client" in d for d in out["diagnostics"])


# --------------------------- fake telethon download glue ---------------------------

def _msg(mid, size, dl_none=False):
    return pytypes.SimpleNamespace(
        file=(pytypes.SimpleNamespace(size=size) if size is not None else None),
        _mid=mid, _dl_none=dl_none)


class _DLClient:
    """Context-manager client answering get_messages/download_media from a map."""

    def __init__(self, get_map):
        self.get_map = get_map  # mid -> msg | None | Exception instance
        self.downloaded = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_messages(self, channel, ids):
        v = self.get_map[ids]
        if isinstance(v, Exception):
            raise v
        return v

    def download_media(self, msg, file=None):
        if getattr(msg, "_dl_none", False):
            return None
        self.downloaded.append(msg._mid)
        return f"{file}/{msg._mid}.bin"


@pytest.fixture
def flood_error():
    """Stub telethon.errors so download_candidates can import FloodWaitError."""
    errors = pytypes.ModuleType("telethon.errors")

    class FloodWaitError(Exception):
        def __init__(self, seconds=0):
            self.seconds = seconds

    errors.FloodWaitError = FloodWaitError
    saved = sys.modules.get("telethon.errors")
    sys.modules["telethon.errors"] = errors
    try:
        yield FloodWaitError
    finally:
        if saved is None:
            sys.modules.pop("telethon.errors", None)
        else:
            sys.modules["telethon.errors"] = saved


def _cands(*ids):
    return [{"candidate_id": f"c{m}", "channel": "demo", "message_id": m,
             "has_media": True, "accessible": True} for m in ids]


def _client_with(get_map):
    return TelethonSearchClient(lambda: _DLClient(get_map))


def test_download_success(flood_error):
    sc = _client_with({10: _msg(10, 1000), 11: _msg(11, 2000)})
    res = sc.download_candidates(_cands(10, 11), dest_dir="/tmp")
    assert res["downloaded"] == 2
    assert res["candidates"][0]["media_file_id"] == "/tmp/10.bin"
    assert all(c["accessible"] for c in res["candidates"])


def test_download_skips_over_cap(flood_error):
    sc = _client_with({10: _msg(10, 99_000_000)})  # over per-file cap
    res = sc.download_candidates(_cands(10))
    assert res["downloaded"] == 0
    assert any("over per-file cap" in d for d in res["diagnostics"])
    assert res["candidates"][0]["accessible"] is True  # skipped, not inaccessible


def test_download_deleted_marks_inaccessible(flood_error):
    sc = _client_with({10: None})
    res = sc.download_candidates(_cands(10))
    assert res["downloaded"] == 0
    assert res["candidates"][0]["accessible"] is False
    assert any("not found or deleted" in d for d in res["diagnostics"])


def test_download_private_marks_inaccessible(flood_error):
    class ChannelPrivateError(Exception):
        pass

    sc = _client_with({10: ChannelPrivateError()})
    res = sc.download_candidates(_cands(10))
    assert res["candidates"][0]["accessible"] is False
    assert any("inaccessible" in d for d in res["diagnostics"])


def test_download_empty_media(flood_error):
    sc = _client_with({10: _msg(10, 1000, dl_none=True)})
    res = sc.download_candidates(_cands(10))
    assert res["downloaded"] == 0
    assert res["candidates"][0]["accessible"] is False
    assert any("no downloadable media" in d for d in res["diagnostics"])


def test_download_flood_stops(flood_error):
    sc = _client_with({10: flood_error(30), 11: _msg(11, 1000)})
    res = sc.download_candidates(_cands(10, 11))
    assert res["downloaded"] == 0
    assert any("flood wait" in d for d in res["diagnostics"])


def test_download_respects_max_media(flood_error):
    sc = _client_with({10: _msg(10, 100), 11: _msg(11, 100), 12: _msg(12, 100)})
    res = sc.download_candidates(_cands(10, 11, 12), max_media=2)
    assert res["downloaded"] == 2


def test_download_respects_total_budget(flood_error):
    sc = _client_with({10: _msg(10, 60), 11: _msg(11, 60)})
    res = sc.download_candidates(_cands(10, 11), total_budget=100)  # 2nd would exceed
    assert res["downloaded"] == 1
    assert any("tmp byte budget" in d for d in res["diagnostics"])


def test_download_skips_no_media_or_inaccessible(flood_error):
    cands = [{"candidate_id": "a", "channel": "demo", "message_id": 1,
              "has_media": False, "accessible": True},
             {"candidate_id": "b", "channel": "demo", "message_id": 2,
              "has_media": True, "accessible": False}]
    sc = _client_with({1: _msg(1, 100), 2: _msg(2, 100)})
    res = sc.download_candidates(cands)
    assert res["downloaded"] == 0  # neither attempted


def test_fetch_delegates_to_download_candidates():
    class _Live:
        def download_candidates(self, candidates, **kw):
            for c in candidates:
                c["media_file_id"] = "/tmp/x.bin"
            return {"candidates": candidates, "downloaded": len(candidates),
                    "diagnostics": ["did 1"]}

    out = fetch_candidate_media([{"channel": "demo", "message_id": 1, "has_media": True}],
                                dry_run=False, live_client=_Live())
    assert out["status"] == "ok" and out["downloaded"] == 1
    assert out["candidates"][0]["media_file_id"] == "/tmp/x.bin"


# --------------------------- function handler ---------------------------

_FUNC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "functions", "fetch_telegram_candidate_media.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("fn_fetch", _FUNC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


def test_handler_dry_run_metadata_only():
    out = _load_handler()({"candidates": [{"channel": "d", "message_id": 1,
                                           "has_media": True}]}, {})
    assert out["status"] == "metadata_only" and out["downloaded"] == 0


def test_handler_live_without_secrets_metadata_only():
    out = _load_handler()({"candidates": [{"channel": "d", "message_id": 1}],
                           "dry_run": False}, {"secrets": {}})
    assert out["status"] == "metadata_only"
