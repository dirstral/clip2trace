"""On-instance OCR for keyframes — pip-only, no tesseract binary required.

Order of preference:
  1. **pytesseract** — when the `tesseract` binary is present (fast, local);
  2. **Claude vision** via the Sinas OpenAI-compatible adapter
     (`POST {base}/adapters/openai/v1/chat/completions`) — needs only `requests`
     + the function's access token, so it works on the managed worker with no
     system binaries;
  3. `""` — the caller still regex-extracts @handles (the strongest retrieval
     signal), so OCR is purely additive.

`claude_vision_ocr` takes an injectable `post` callable so the request shape and
parsing are unit-testable without a live LLM.
"""

from __future__ import annotations

import base64
import io
from typing import Optional

_OCR_PROMPT = (
    "Output ONLY the visible on-screen text in this video frame (overlays, "
    "captions, channel handles, watermarks), verbatim. No preamble, labels, "
    "quotes, or markdown. If there is no text, output nothing."
)


def _png_b64(rgb) -> Optional[str]:
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def tesseract_ocr(rgb) -> Optional[str]:
    """OCR via a local tesseract binary, or None if unavailable."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        return (pytesseract.image_to_string(Image.fromarray(rgb)) or "").strip()
    except Exception:
        return None


def claude_vision_ocr(rgb, *, base_url: Optional[str], token: Optional[str],
                      model: str = "claude-sonnet-4-6", timeout: float = 60.0,
                      post=None) -> Optional[str]:
    """OCR a frame via the Sinas OpenAI-compatible chat-completions adapter.

    `post(url, headers, json_body) -> dict` is injectable for tests; when None a
    real `requests.post` is used. Returns the transcribed text or None on any
    failure (so OCR never breaks the pipeline).
    """
    b64 = _png_b64(rgb)
    if not b64 or not base_url or not token:
        return None
    url = base_url.rstrip("/") + "/adapters/openai/v1/chat/completions"
    # The Sinas OpenAI adapter routes the model by name but passes Anthropic-native
    # content blocks through to the provider. The OpenAI `image_url` shape 500s;
    # the Anthropic `image` block works. (See docs/research/runtime-diagnostics.md.)
    body = {
        "model": model, "max_tokens": 512,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _OCR_PROMPT},
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png",
                                         "data": b64}}]}],
    }
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/json"}
    try:
        if post is None:
            import requests  # type: ignore
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
        else:
            data = post(url, headers, body)
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return None


def resolve_runtime(context) -> tuple:
    """Best-effort (base_url, token) for the runtime, from a function context."""
    import os
    ctx = context or {}
    base = (ctx.get("api_url") or ctx.get("base_url")
            or os.environ.get("SINAS_BASE_URL"))
    token = ctx.get("access_token")
    return base, token


def ocr_image(rgb, *, context=None, base_url: Optional[str] = None,
              token: Optional[str] = None, model: str = "claude-sonnet-4-6",
              post=None) -> str:
    """Best-effort OCR of an RGB frame: tesseract -> Claude vision -> ''."""
    text = tesseract_ocr(rgb)
    if text:
        return text
    if (base_url is None or token is None) and context is not None:
        rb, rt = resolve_runtime(context)
        base_url = base_url or rb
        token = token or rt
    return claude_vision_ocr(rgb, base_url=base_url, token=token, model=model,
                             post=post) or ""
