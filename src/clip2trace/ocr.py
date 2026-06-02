"""On-instance OCR for keyframes — pip-only, no tesseract binary required.

Order of preference:
  1. **pytesseract** — when the `tesseract` binary is present (fast, local;
     operator-provisioned only — the managed worker has no system binaries);
  2. **EasyOCR** — when the `easyocr` package is installed (pip-only, but the
     torch/model footprint exceeds the 512 MB worker, so this too is an
     operator-provisioned *local* option only — see docs/risks.md);
  3. **Claude vision** via the Sinas OpenAI-compatible adapter
     (`POST {base}/adapters/openai/v1/chat/completions`) — needs only `requests`
     + the function's access token, so it works on the managed worker with no
     system binaries. **This is the on-worker default.**
  4. `""` — the caller still regex-extracts @handles (the strongest retrieval
     signal), so OCR is purely additive.

Tiers 1–2 are import-guarded: if the optional package is absent the tier is
skipped and behaviour is unchanged. `claude_vision_ocr` and `select_backend`
take injectable callables so the request shape, parsing, and selection order are
unit-testable without a live LLM or any heavy dependency.
"""

from __future__ import annotations

import base64
import io
from typing import Callable, Optional

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


# A process-wide EasyOCR reader is expensive to build (loads torch + detection
# and recognition models), so cache it after the first successful construction.
_EASYOCR_READER = None


def easyocr_ocr(rgb, *, languages=("en",), reader=None) -> Optional[str]:
    """OCR via the optional `easyocr` package, or None if unavailable.

    `easyocr` is a heavy, pip-only dependency (pulls in torch); it is an
    operator-provisioned *local* option only — it does not fit the 512 MB
    managed worker. `reader` is injectable for tests so the parsing/joining
    logic is exercised without loading torch or any model weights.
    """
    global _EASYOCR_READER
    if reader is None:
        try:
            import easyocr  # type: ignore
        except Exception:
            return None
        try:
            if _EASYOCR_READER is None:
                _EASYOCR_READER = easyocr.Reader(list(languages), gpu=False)
            reader = _EASYOCR_READER
        except Exception:
            return None
    try:
        # detail=0 returns just the recognised strings, top-to-bottom.
        lines = reader.readtext(rgb, detail=0)
        return "\n".join(s for s in (str(x).strip() for x in lines) if s).strip()
    except Exception:
        return None


def claude_vision_ocr(
    rgb,
    *,
    base_url: Optional[str],
    token: Optional[str],
    model: str = "claude-sonnet-4-6",
    timeout: float = 60.0,
    post=None,
) -> Optional[str]:
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
        "model": model,
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_PROMPT},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                ],
            }
        ],
    }
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    try:
        if post is None:
            import requests  # type: ignore

            # body is a hand-built JSON payload; requests' JsonType is stricter.
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)  # type: ignore[arg-type]
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
    # Falls back to the sinas SDK default base URL (host.docker.internal:8000) — it
    # is hardcoded in the worker, not delivered via env/context. See storage.py.
    base = (
        ctx.get("api_url")
        or ctx.get("base_url")
        or os.environ.get("SINAS_BASE_URL")
        or "http://host.docker.internal:8000"
    )
    token = ctx.get("access_token")
    return base, token


# Operator-provisioned local backends, tried in preference order *before* the
# always-available Claude-vision tier. Each returns a non-empty string on a hit
# or a falsy value (None/"") to fall through to the next tier. Injectable as a
# list so selection order is unit-testable with fake backends.
LOCAL_BACKENDS: tuple[Callable[..., Optional[str]], ...] = (
    tesseract_ocr,
    easyocr_ocr,
)


def select_backend(rgb, *, backends=LOCAL_BACKENDS) -> str:
    """Run local OCR tiers in order; return the first non-empty result, else ''.

    `backends` is an injectable iterable of callables taking the frame and
    returning a string-or-None, so the selection order can be tested with fake
    backends and no heavy dependency present.
    """
    for backend in backends:
        try:
            text = backend(rgb)
        except Exception:
            text = None
        if text:
            return text
    return ""


def ocr_image(
    rgb,
    *,
    context=None,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    model: str = "claude-sonnet-4-6",
    post=None,
    backends=LOCAL_BACKENDS,
) -> str:
    """Best-effort OCR of an RGB frame.

    Tier order: local backends (tesseract -> easyocr, both operator-provisioned
    and import-guarded) -> Claude vision (the on-worker default) -> ''.
    """
    text = select_backend(rgb, backends=backends)
    if text:
        return text
    if (base_url is None or token is None) and context is not None:
        rb, rt = resolve_runtime(context)
        base_url = base_url or rb
        token = token or rt
    return (
        claude_vision_ocr(rgb, base_url=base_url, token=token, model=model, post=post)
        or ""
    )
