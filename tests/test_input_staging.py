"""#36 — stage_input_file downloads an input-videos file to a local path.

Mocks the runtime files API so no live instance is needed. The Sinas files API is
name-addressed and returns a JSON envelope `{content_base64, content_type, ...}`
(confirmed against via-10's /openapi.json), so the helper base64-decodes it.
"""

import base64

import requests

from clip2trace.storage import (
    SINAS_RUNTIME_BASE_URL,
    resolve_runtime_base_url,
    stage_input_file,
)


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _fake_get(captured, status=200, content=b"video-bytes"):
    def _get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        payload = {
            "content_base64": base64.b64encode(content).decode("ascii"),
            "content_type": "video/mp4",
            "file_metadata": {},
            "version": 1,
        }
        return _FakeResp(status, payload)

    return _get


def test_resolve_base_url_defaults_to_sdk_host():
    assert resolve_runtime_base_url({}) == SINAS_RUNTIME_BASE_URL
    assert resolve_runtime_base_url({"base_url": "http://x:1"}) == "http://x:1"


def test_stage_input_file_decodes_base64_to_tmp(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(requests, "get", _fake_get(captured))
    path = stage_input_file("vid123", {"access_token": "tok"}, dest_dir=str(tmp_path))
    assert path is not None and path.endswith("vid123.mp4")
    with open(path, "rb") as fh:
        assert fh.read() == b"video-bytes"
    # name-addressed download from the SDK-default base + input-videos collection
    assert captured["url"] == (
        SINAS_RUNTIME_BASE_URL + "/files/clip2trace/input-videos/vid123"
    )
    assert captured["headers"]["Authorization"] == "Bearer tok"


def test_stage_input_file_keeps_existing_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", _fake_get({}))
    path = stage_input_file("clip.mov", {"access_token": "t"}, dest_dir=str(tmp_path))
    assert path is not None and path.endswith("clip.mov")


def test_stage_input_file_url_encodes_spaces_and_brackets(monkeypatch, tmp_path):
    # Sinas file names may contain spaces/brackets (pattern ^[^/]+$); the path
    # segment must be percent-encoded so the request reaches the right file.
    captured = {}
    monkeypatch.setattr(requests, "get", _fake_get(captured))
    name = "Israel castle [CtaT27mc3bU].mkv"
    path = stage_input_file(name, {"access_token": "t"}, dest_dir=str(tmp_path))
    assert path is not None and path.endswith(name)  # local file keeps real name
    assert "Israel%20castle%20%5BCtaT27mc3bU%5D.mkv" in captured["url"]
    assert " " not in captured["url"] and "[" not in captured["url"]


def test_stage_input_file_requires_token_and_file_id(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", _fake_get({}))
    assert stage_input_file("vid", {}, dest_dir=str(tmp_path)) is None
    assert stage_input_file("", {"access_token": "t"}, dest_dir=str(tmp_path)) is None


def test_stage_input_file_non_200_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", _fake_get({}, status=403))
    assert (
        stage_input_file("vid", {"access_token": "t"}, dest_dir=str(tmp_path)) is None
    )


def test_stage_input_file_rejects_oversize(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", _fake_get({}, content=b"x" * 500))
    assert (
        stage_input_file(
            "vid", {"access_token": "t"}, dest_dir=str(tmp_path), max_bytes=100
        )
        is None
    )


def test_stage_input_file_reuses_cached_copy(monkeypatch, tmp_path):
    # If the file is already staged, return it WITHOUT downloading again — so
    # per-segment extract_segment_clues calls don't re-fetch the whole video.
    (tmp_path / "vid.mp4").write_bytes(b"already-here")

    def _boom(*a, **k):
        raise AssertionError("should not download when a staged copy exists")

    monkeypatch.setattr(requests, "get", _boom)
    path = stage_input_file("vid", {"access_token": "t"}, dest_dir=str(tmp_path))
    assert path == str(tmp_path / "vid.mp4")
    with open(path, "rb") as fh:
        assert fh.read() == b"already-here"
