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
    MAX_MEDIA_BYTES,
    TelethonSearchClient,
    media_within_cap,
)
from clip2trace.telegram_media import fetch_candidate_media, normalise_candidate

# --------------------------- pure helpers ---------------------------


def test_media_within_cap():
    assert media_within_cap(None) is True  # unknown size allowed
    assert media_within_cap(1000, 8000) is True
    assert media_within_cap(9000, 8000) is False
    assert media_within_cap(MAX_MEDIA_BYTES) is True


def test_normalise_candidate_builds_url():
    c = normalise_candidate({"channel": "demo", "message_id": 5})
    assert c["url"] == "https://t.me/demo/5"
    assert c["accessible"] is True and c["has_media"] is False


def test_fetch_dry_run_is_metadata_only():
    out = fetch_candidate_media(
        [{"channel": "demo", "message_id": 1, "has_media": True}]
    )
    assert out["status"] == "metadata_only" and out["downloaded"] == 0


def test_fetch_not_dry_run_without_client_is_metadata_only():
    out = fetch_candidate_media(
        [{"channel": "d", "message_id": 1}], dry_run=False, live_client=None
    )
    assert out["status"] == "metadata_only"
    assert any("no live client" in d for d in out["diagnostics"])


# --------------------------- fake telethon download glue ---------------------------


def _msg(mid, size, dl_none=False, actual=None):
    # `size` is what msg.file.size reports (None = unknown, e.g. some photos);
    # `actual` is the real byte count written to disk (defaults to size or 0).
    return pytypes.SimpleNamespace(
        file=(pytypes.SimpleNamespace(size=size) if size is not None else None),
        _mid=mid,
        _dl_none=dl_none,
        _actual=(actual if actual is not None else (size or 0)),
    )


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
        # Write a real file of `_actual` bytes so the downloader's post-download
        # os.path.getsize budget enforcement is genuinely exercised.
        path = os.path.join(file, f"{msg._mid}.bin")
        with open(path, "wb") as fh:
            fh.write(b"x" * int(getattr(msg, "_actual", 0)))
        self.downloaded.append(msg._mid)
        return path


@pytest.fixture
def flood_error():
    """Stub `telethon` + `telethon.errors` so download_candidates can import
    FloodWaitError even when Telethon isn't installed. Injecting the parent
    package too keeps it robust regardless of import-machinery details."""
    telethon = pytypes.ModuleType("telethon")
    errors = pytypes.ModuleType("telethon.errors")

    class FloodWaitError(Exception):
        def __init__(self, seconds=0):
            self.seconds = seconds

    errors.FloodWaitError = FloodWaitError
    telethon.errors = errors
    saved = {k: sys.modules.get(k) for k in ("telethon", "telethon.errors")}
    sys.modules["telethon"] = telethon
    sys.modules["telethon.errors"] = errors
    try:
        yield FloodWaitError
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _cands(*ids):
    return [
        {
            "candidate_id": f"c{m}",
            "channel": "demo",
            "message_id": m,
            "has_media": True,
            "accessible": True,
        }
        for m in ids
    ]


def _client_with(get_map):
    return TelethonSearchClient(lambda: _DLClient(get_map))


def test_download_success(flood_error, tmp_path):
    sc = _client_with({10: _msg(10, 1000), 11: _msg(11, 2000)})
    res = sc.download_candidates(_cands(10, 11), dest_dir=str(tmp_path))
    assert res["downloaded"] == 2
    assert res["candidates"][0]["media_file_id"] == str(tmp_path / "10.bin")
    assert all(c["accessible"] for c in res["candidates"])


def test_download_cleans_up_tmp_after_phash(flood_error, tmp_path):
    """Downloaded media is deleted right after phashing so the worker's 100 MB
    /tmp does not fill across calls (the real cause of OSError 28 / 'No space
    left on device'). media_file_id stays set as a marker that media was
    fetched, and the phashes are retained."""
    sc = _client_with({10: _msg(10, 1000), 11: _msg(11, 2000)})
    res = sc.download_candidates(_cands(10, 11), dest_dir=str(tmp_path))
    assert res["downloaded"] == 2
    paths = [c["media_file_id"] for c in res["candidates"]]
    assert paths == [str(tmp_path / "10.bin"), str(tmp_path / "11.bin")]  # marker kept
    assert not any(os.path.exists(p) for p in paths)  # bytes freed
    assert os.listdir(tmp_path) == []  # no leftover media in the dir


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


def test_download_transient_error_keeps_accessible(flood_error):
    # A non-inaccessible (transient/network/disk) error must NOT poison
    # `accessible` — the post may still be reachable on a later retry.
    sc = _client_with({10: ConnectionError("network blip")})
    res = sc.download_candidates(_cands(10))
    assert res["downloaded"] == 0
    assert res["candidates"][0]["accessible"] is True
    assert any("may be transient" in d for d in res["diagnostics"])


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


def test_download_respects_max_media(flood_error, tmp_path):
    sc = _client_with({10: _msg(10, 100), 11: _msg(11, 100), 12: _msg(12, 100)})
    res = sc.download_candidates(
        _cands(10, 11, 12), max_media=2, dest_dir=str(tmp_path)
    )
    assert res["downloaded"] == 2


def test_download_respects_total_budget(flood_error, tmp_path):
    sc = _client_with({10: _msg(10, 60), 11: _msg(11, 60)})
    res = sc.download_candidates(
        _cands(10, 11), total_budget=100, dest_dir=str(tmp_path)  # 2nd would exceed
    )
    assert res["downloaded"] == 1
    assert any("tmp byte budget" in d for d in res["diagnostics"])


def test_download_unknown_size_enforces_budget(flood_error, tmp_path):
    # size reported None (e.g. photos) but real bytes counted via os.path.getsize.
    sc = _client_with({10: _msg(10, None, actual=60), 11: _msg(11, None, actual=60)})
    res = sc.download_candidates(
        _cands(10, 11), total_budget=100, dest_dir=str(tmp_path)
    )
    assert res["downloaded"] == 1  # 2nd would push spent (60+60) over 100
    assert any("tmp byte budget" in d for d in res["diagnostics"])


def test_download_unknown_size_over_cap_removed(flood_error, tmp_path):
    # size None, but the downloaded file is over the per-file cap -> skipped + removed.
    sc = _client_with({10: _msg(10, None, actual=200)})
    res = sc.download_candidates(_cands(10), max_bytes=100, dest_dir=str(tmp_path))
    assert res["downloaded"] == 0
    assert any("over per-file cap" in d for d in res["diagnostics"])
    assert list(tmp_path.iterdir()) == []  # cleaned up


def test_download_skips_no_media_or_inaccessible(flood_error):
    cands = [
        {
            "candidate_id": "a",
            "channel": "demo",
            "message_id": 1,
            "has_media": False,
            "accessible": True,
        },
        {
            "candidate_id": "b",
            "channel": "demo",
            "message_id": 2,
            "has_media": True,
            "accessible": False,
        },
    ]
    sc = _client_with({1: _msg(1, 100), 2: _msg(2, 100)})
    res = sc.download_candidates(cands)
    assert res["downloaded"] == 0  # neither attempted


def test_fetch_delegates_to_download_candidates():
    class _Live:
        def download_candidates(self, candidates, **kw):
            for c in candidates:
                c["media_file_id"] = "/tmp/x.bin"
            return {
                "candidates": candidates,
                "downloaded": len(candidates),
                "diagnostics": ["did 1"],
            }

    out = fetch_candidate_media(
        [{"channel": "demo", "message_id": 1, "has_media": True}],
        dry_run=False,
        live_client=_Live(),
    )
    assert out["status"] == "ok" and out["downloaded"] == 1
    assert out["candidates"][0]["media_file_id"] == "/tmp/x.bin"


# --------------------------- function handler ---------------------------

_FUNC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "functions",
    "fetch_telegram_candidate_media.py",
)


def _load_handler():
    spec = importlib.util.spec_from_file_location("fn_fetch", _FUNC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handler


def test_handler_dry_run_metadata_only():
    out = _load_handler()(
        {"candidates": [{"channel": "d", "message_id": 1, "has_media": True}]}, {}
    )
    assert out["status"] == "metadata_only" and out["downloaded"] == 0


def test_handler_live_without_secrets_metadata_only():
    out = _load_handler()(
        {"candidates": [{"channel": "d", "message_id": 1}], "dry_run": False},
        {"secrets": {}},
    )
    assert out["status"] == "metadata_only"


# --------------------------- #59: candidate-media phashes ---------------------------


def _write_av_clip(path, av, np, frames=18, size=(64, 48), fps=10):
    with av.open(path, mode="w") as c:
        st = c.add_stream("mpeg4", rate=fps)
        st.width, st.height, st.pix_fmt = size[0], size[1], "yuv420p"
        for val in (40, 200):  # two scenes so there's content to hash
            block = np.full((size[1], size[0], 3), val, dtype=np.uint8)
            for _ in range(frames):
                fr = av.VideoFrame.from_ndarray(block, format="rgb24")
                for p in st.encode(fr):
                    c.mux(p)
        for p in st.encode():
            c.mux(p)


def test_phashes_for_media_video(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    pytest.importorskip("imagehash")
    from clip2trace.video import phashes_for_media

    path = str(tmp_path / "clip.mp4")
    _write_av_clip(path, av, np)
    ph = phashes_for_media(path)
    assert ph, "expected perceptual hashes from a decodable candidate clip"
    assert all(int(h, 16) >= 0 for h in ph)  # valid hex hashes


def test_phashes_for_media_image(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("imagehash")
    Image = pytest.importorskip("PIL.Image")
    from clip2trace.video import phashes_for_media

    path = str(tmp_path / "still.png")
    Image.fromarray(np.full((48, 64, 3), 120, dtype=np.uint8)).save(path)
    assert phashes_for_media(path), "expected a phash from a still image candidate"


def test_phashes_for_media_undecodable_is_empty(tmp_path):
    from clip2trace.video import phashes_for_media

    path = str(tmp_path / "notmedia.bin")
    with open(path, "wb") as fh:
        fh.write(b"this is not media")
    assert phashes_for_media(path) == []  # graceful, never raises


class _VideoDLClient:
    """Fake telethon client that 'downloads' a real video clip (for phash test)."""

    def __init__(self, src_mp4):
        self.src = src_mp4

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_messages(self, channel, ids):
        return pytypes.SimpleNamespace(
            file=pytypes.SimpleNamespace(size=2000), _mid=ids
        )

    def download_media(self, msg, file=None):
        import shutil

        dst = os.path.join(file, "cand.mp4")
        shutil.copy(self.src, dst)
        return dst


def test_download_candidates_attaches_phashes(flood_error, tmp_path):
    # The decisive #59 path: a downloaded candidate clip gets perceptual hashes,
    # so verify_media_similarity has candidate_phashes (else visual score is 0).
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    pytest.importorskip("imagehash")
    src = str(tmp_path / "src.mp4")
    _write_av_clip(src, av, np)
    sc = TelethonSearchClient(lambda: _VideoDLClient(src))
    res = sc.download_candidates(_cands(10), dest_dir=str(tmp_path))
    assert res["downloaded"] == 1
    assert res["candidates"][0].get("phashes"), "candidate should carry phashes"
