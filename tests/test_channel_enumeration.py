"""Channel-scoped enumeration — `enumerate_channel_videos` + telegram_live glue.

Exercises the candidate-shaping logic with a fake Telethon client (no network,
no telethon import needed for the shaping path) and the dev-copy function's
cached/demo/live-unavailable fallbacks.
"""

import importlib.util
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)

from clip2trace.telegram_live import (  # noqa: E402
    TelethonSearchClient,
    is_video_like_msg,
)


def _load(name):
    path = os.path.join(FUNCS, name + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _msg(**kw):
    kw.setdefault("video", None)
    kw.setdefault("file", None)
    kw.setdefault("media", None)
    kw.setdefault("fwd_from", None)
    kw.setdefault("message", "")
    kw.setdefault("date", SimpleNamespace(isoformat=lambda: "2026-06-03T00:00:00"))
    return SimpleNamespace(**kw)


def test_is_video_like_msg_variants():
    assert is_video_like_msg(_msg(video=object()))  # video message
    assert is_video_like_msg(_msg(file=SimpleNamespace(mime_type="video/mp4")))
    # .mkv posted as a document (the real-world case the video filter misses):
    assert is_video_like_msg(
        _msg(file=SimpleNamespace(mime_type="application/octet-stream", name="x.mkv"))
    )
    assert not is_video_like_msg(
        _msg(file=SimpleNamespace(mime_type="image/jpeg", name="x.jpg"))
    )
    assert not is_video_like_msg(_msg(file=None))


class _FakeClient:
    def __init__(self, entity, msgs):
        self._entity, self._msgs = entity, msgs

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_entity(self, channel):
        return self._entity

    def iter_messages(self, entity, limit=None):
        return iter(self._msgs)


def test_enumerate_channel_shapes_candidates():
    entity = SimpleNamespace(username="clip2trace", title="clip2trace demo")
    msgs = [
        _msg(id=5, media=object(), video=object(), message="cap a"),
        _msg(id=4, media=None),  # no media -> skipped
        _msg(
            id=3,
            media=object(),
            file=SimpleNamespace(mime_type="application/octet-stream", name="v.mkv"),
        ),
    ]
    client = TelethonSearchClient(lambda: _FakeClient(entity, msgs))
    out = client.enumerate_channel("clip2trace", max_videos=10)

    assert [c["message_id"] for c in out] == [5, 3]  # the .mkv document is included
    c = out[0]
    assert c["channel"] == "clip2trace"
    assert c["candidate_id"] == "clip2trace_5"
    assert c["url"] == "https://t.me/clip2trace/5"
    assert c["channel_relevance"] == 1.0
    assert c["source_query"] == "channel:clip2trace"
    assert c["has_media"] is True


def test_enumerate_channel_respects_max():
    entity = SimpleNamespace(username="clip2trace")
    msgs = [_msg(id=i, media=object(), video=object()) for i in range(10)]
    client = TelethonSearchClient(lambda: _FakeClient(entity, msgs))
    assert len(client.enumerate_channel("clip2trace", max_videos=3)) == 3


def test_function_cached_demo_and_live_unavailable():
    mod = _load("enumerate_channel_videos")

    cached = mod.handler(
        {"channel": "x", "mode": "demo", "cached_results": [{"candidate_id": "c1"}]}, {}
    )
    assert cached["source"] == "cached"
    assert cached["candidates"] == [{"candidate_id": "c1"}]

    demo = mod.handler({"channel": "x", "mode": "demo"}, {})
    assert demo["status"] == "demo_no_data"

    live = mod.handler({"channel": "x", "mode": "live"}, {"secrets": {}})
    assert live["status"] == "live_unavailable"
    # Empty secrets -> build_client_from_secrets returns None (the "missing
    # secrets" path), NOT a swallowed import/exception error masquerading as
    # live_unavailable. Assert the *reason*, so the test can't pass for the
    # wrong cause.
    live_diag = " ".join(live.get("diagnostics", [])).lower()
    assert "missing" in live_diag
    assert "enumeration error" not in live_diag

    no_channel = mod.handler({"mode": "live"}, {"secrets": {"TELEGRAM_API_ID": "1"}})
    assert no_channel["status"] == "live_unavailable"
    assert "no channel" in " ".join(no_channel.get("diagnostics", [])).lower()


def test_live_path_actually_invokes_build_client(monkeypatch):
    """The live branch must really reach build_client_from_secrets and degrade on
    a None client — not rely on an ImportError being swallowed into the same
    live_unavailable return (which is why asserting status alone is too weak)."""
    import clip2trace.telegram_live as tl

    calls = []

    def fake_build(secrets):
        calls.append(secrets)
        return None

    monkeypatch.setattr(tl, "build_client_from_secrets", fake_build)
    mod = _load("enumerate_channel_videos")
    secrets = {
        "TELEGRAM_API_ID": "1",
        "TELEGRAM_API_HASH": "h",
        "TELEGRAM_SESSION_STRING": "s",
    }
    out = mod.handler({"channel": "clip2trace", "mode": "live"}, {"secrets": secrets})

    assert calls == [secrets]  # reached and called with the real secrets
    assert out["status"] == "live_unavailable"
    assert "missing" in " ".join(out.get("diagnostics", [])).lower()


def test_live_path_returns_client_candidates(monkeypatch):
    """A usable client's enumerate_channel results flow through as source=live."""
    import clip2trace.telegram_live as tl

    class _FakeChannelClient:
        diagnostics = ["scanned 1 channel"]

        def __init__(self):
            self.seen = None

        def enumerate_channel(self, channel, max_videos=10):
            self.seen = (channel, max_videos)
            return [{"candidate_id": f"{channel}_9", "channel_relevance": 1.0}]

    client = _FakeChannelClient()
    monkeypatch.setattr(tl, "build_client_from_secrets", lambda s: client)
    mod = _load("enumerate_channel_videos")
    out = mod.handler(
        {"channel": "clip2trace", "mode": "live", "max_videos": 5},
        {"secrets": {"TELEGRAM_API_ID": "1"}},
    )

    assert out["status"] == "ok"
    assert out["source"] == "live"
    assert out["candidates"] == [
        {"candidate_id": "clip2trace_9", "channel_relevance": 1.0}
    ]
    assert out["diagnostics"] == ["scanned 1 channel"]
    assert client.seen == ("clip2trace", 5)
