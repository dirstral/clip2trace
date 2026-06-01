"""OCR module: tesseract -> Claude-vision (OpenAI adapter) -> '' selection."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

np = pytest.importorskip("numpy")

from clip2trace.ocr import ocr_image, claude_vision_ocr  # noqa: E402


def _frame():
    return np.zeros((8, 8, 3), dtype=np.uint8)


def test_claude_vision_request_shape_and_parse():
    captured = {}

    def fake_post(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "LIVE FROM DEMO"}}]}

    out = claude_vision_ocr(_frame(), base_url="https://via-10", token="tok",
                            post=fake_post)
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
    out = ocr_image(_frame(), base_url="https://via-10", token="tok",
                    post=lambda u, h, b: {"choices": [{"message": {"content": "X"}}]})
    assert out == "X"


def test_ocr_image_empty_without_anything():
    assert ocr_image(_frame(), base_url=None, token=None) == ""
