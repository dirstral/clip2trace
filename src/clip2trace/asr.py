"""Optional ASR / transcript extraction — spoken context for query planning.

ASR is an **optional, operator-provisioned/local upgrade path**, not part of the
default pipeline. Both real backends are heavy and will not realistically run on
the pip-only, 512 MB / 300 s Sinas worker (see docs/risks.md, row 14), but for
different reasons: **faster-whisper** (the default here) is built on the
CTranslate2 native runtime (plus onnxruntime for VAD) and downloads a
multi-hundred-MB model — it does *not* use torch; **openai-whisper** instead
pulls in torch + ffmpeg. So:

- the heavy backend is **import-guarded** — if the dep is absent we return ``""``
  (no transcript) and the rest of the pipeline behaves exactly as before;
- the transcription backend is **injectable** (`transcriber=`), so the
  integration is unit-testable WITHOUT any heavy model — inject a fake callable
  that returns known text.

The extracted transcript feeds the same context-term derivation the query
planner already uses (see `telegram_search.generate_queries`), so spoken context
broadens Telegram retrieval. Scope stays provenance/source-tracing: we use the
transcript only as retrieval clues, never as translation or analysis output.
"""

from __future__ import annotations

from typing import Callable, Optional

# A transcriber maps an audio/video path to plain transcript text.
Transcriber = Callable[[str], str]


def _load_default_transcriber() -> Optional[Transcriber]:
    """Return a faster-whisper-backed transcriber, or ``None`` if unavailable.

    Import-guarded: faster-whisper (CTranslate2 native runtime + a
    multi-hundred-MB model download, no torch) is an optional `asr` extra. Absent
    it, we return ``None`` and callers degrade gracefully.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None

    def _transcribe(media_path: str, *, model_size: str = "tiny") -> str:
        # `tiny` is the smallest model; even so this is heavy (see module docs).
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(media_path)
        return " ".join(seg.text.strip() for seg in segments).strip()

    return _transcribe


def extract_transcript(
    media_path: str,
    *,
    transcriber: Optional[Transcriber] = None,
) -> str:
    """Extract a spoken-word transcript from a media file.

    Args:
        media_path: path to the audio/video to transcribe.
        transcriber: optional injected backend ``(path) -> text``. When omitted,
            we try to load the optional faster-whisper backend; if that dep is
            not installed we return ``""`` (graceful no-op, pipeline unchanged).

    Returns:
        The transcript text, or ``""`` when no backend is available or the
        backend fails. We never raise: a missing/broken ASR path must not break
        the surrounding pipeline.
    """
    backend = transcriber if transcriber is not None else _load_default_transcriber()
    if backend is None:
        return ""
    try:
        return (backend(media_path) or "").strip()
    except Exception:
        # ASR is best-effort context; a failure degrades to "no transcript".
        return ""
