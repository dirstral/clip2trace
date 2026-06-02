"""OCR module: tesseract -> easyocr -> Claude-vision adapter -> '' selection."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

np = pytest.importorskip("numpy")

from clip2trace.ocr import (  # noqa: E402
    claude_vision_ocr,
    easyocr_ocr,
    ocr_image,
    select_backend,
)


def _frame():
    return np.zeros((8, 8, 3), dtype=np.uint8)


def test_claude_vision_request_shape_and_parse():
    captured = {}

    def fake_post(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "LIVE FROM DEMO"}}]}

    out = claude_vision_ocr(
        _frame(), base_url="https://via-10", token="tok", post=fake_post
    )
    assert out == "LIVE FROM DEMO"
    assert captured["url"].endswith("/adapters/openai/v1/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer tok"
    content = captured["body"]["messages"][0]["content"]
    img = [p for p in content if p.get("type") == "image"]
    assert img and img[0]["source"]["type"] == "base64"
    assert img[0]["source"]["media_type"] == "image/png"
    assert img[0]["source"]["data"]  # base64 payload present


def test_claude_vision_returns_none_without_runtime():
    assert claude_vision_ocr(_frame(), base_url=None, token=None) is None


def test_ocr_image_uses_claude_when_tesseract_blank():
    # blank frame → tesseract yields '' (or is absent) → Claude path is used
    out = ocr_image(
        _frame(),
        base_url="https://via-10",
        token="tok",
        post=lambda u, h, b: {"choices": [{"message": {"content": "X"}}]},
    )
    assert out == "X"


def test_ocr_image_empty_without_anything():
    assert ocr_image(_frame(), base_url=None, token=None) == ""


# --- backend selection order (testable with fake backends, no heavy deps) ----


def test_select_backend_returns_first_non_empty():
    calls = []

    def empty(_):
        calls.append("empty")
        return ""

    def none_backend(_):
        calls.append("none")
        return None

    def hit(_):
        calls.append("hit")
        return "FOUND"

    def later(_):
        calls.append("later")
        return "SHOULD-NOT-RUN"

    out = select_backend(_frame(), backends=[empty, none_backend, hit, later])
    assert out == "FOUND"
    # later backend must not run once one hits
    assert calls == ["empty", "none", "hit"]


def test_select_backend_empty_when_all_miss():
    assert select_backend(_frame(), backends=[lambda _: None, lambda _: ""]) == ""


def test_select_backend_swallows_backend_errors():
    def boom(_):
        raise RuntimeError("backend exploded")

    out = select_backend(_frame(), backends=[boom, lambda _: "OK"])
    assert out == "OK"


def test_ocr_image_prefers_local_backend_over_claude():
    # an injected local backend that hits short-circuits before Claude vision
    out = ocr_image(
        _frame(),
        base_url="https://via-10",
        token="tok",
        backends=[lambda _: "LOCAL"],
        post=lambda u, h, b: {"choices": [{"message": {"content": "CLAUDE"}}]},
    )
    assert out == "LOCAL"


def test_ocr_image_falls_through_to_claude_when_local_miss():
    out = ocr_image(
        _frame(),
        base_url="https://via-10",
        token="tok",
        backends=[lambda _: None],
        post=lambda u, h, b: {"choices": [{"message": {"content": "CLAUDE"}}]},
    )
    assert out == "CLAUDE"


def test_easyocr_absent_returns_none():
    # With no real easyocr reader injected and the package absent in CI, the tier
    # must gracefully return None (purely additive — behaviour unchanged).
    import importlib.util

    if importlib.util.find_spec("easyocr") is None:
        assert easyocr_ocr(_frame()) is None


def test_easyocr_parses_injected_reader_lines():
    class FakeReader:
        def readtext(self, _rgb, detail=0):
            assert detail == 0
            return ["@channel", " caption ", ""]

    out = easyocr_ocr(_frame(), reader=FakeReader())
    assert out == "@channel\ncaption"


def test_easyocr_real_smoke():
    pytest.importorskip("easyocr")
    # If easyocr is actually installed locally, the tier must run without raising
    # and return a string (possibly empty for a blank frame).
    out = easyocr_ocr(_frame())
    assert out is None or isinstance(out, str)
