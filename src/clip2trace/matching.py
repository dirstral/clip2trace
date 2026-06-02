"""Visual / text / temporal similarity primitives.

Pure functions used by verify_media_similarity. Kept dependency-light so they
import and test without OpenCV/Telethon present.
"""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Protocol, Sequence, runtime_checkable

PHASH_BITS = 64  # default size of a 64-bit perceptual hash (imagehash 8x8)

# Default cosine-similarity threshold above which two frame embeddings are
# considered a visual match. Embedding cosine sims tend to run higher than
# normalised phash sims for re-encoded/cropped footage, so this sits above the
# 0.85 phash default; tune per embedder if needed.
EMBED_MATCH_THRESHOLD = 0.90


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two hex-encoded perceptual hashes.

    Accepts hex strings (e.g. imagehash str()) of equal length.
    """
    if len(hash_a) != len(hash_b):
        raise ValueError("hashes must be the same length")
    a = int(hash_a, 16)
    b = int(hash_b, 16)
    return bin(a ^ b).count("1")


def phash_similarity(hash_a: str, hash_b: str, bits: int = PHASH_BITS) -> float:
    """Convert hamming distance to a [0, 1] similarity (1.0 == identical)."""
    dist = hamming_distance(hash_a, hash_b)
    return max(0.0, 1.0 - dist / float(bits))


def best_frame_similarity(
    hashes_a: Sequence[str], hashes_b: Sequence[str]
) -> tuple[float, int, int]:
    """Best pairwise perceptual-hash similarity across two keyframe sets.

    Returns (best_similarity, index_a, index_b). Returns (0.0, -1, -1) if either
    set is empty.
    """
    best = 0.0
    bi, bj = -1, -1
    for i, ha in enumerate(hashes_a):
        for j, hb in enumerate(hashes_b):
            try:
                sim = phash_similarity(ha, hb)
            except ValueError:
                continue
            if sim > best:
                best, bi, bj = sim, i, j
    return best, bi, bj


def text_overlap_score(text_a: str, text_b: str) -> float:
    """Fuzzy token-set similarity in [0, 1]. Falls back to a Jaccard token
    overlap if rapidfuzz is unavailable so it works in minimal environments."""
    a = (text_a or "").strip().lower()
    b = (text_b or "").strip().lower()
    if not a or not b:
        return 0.0
    try:
        from rapidfuzz import fuzz  # type: ignore

        return fuzz.token_set_ratio(a, b) / 100.0
    except Exception:
        ta, tb = set(a.split()), set(b.split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)


def temporal_alignment_score(
    segment_dur: float, candidate_dur: float, tolerance: float = 0.25
) -> float:
    """Score how well two durations align. 1.0 == identical length.

    `tolerance` is the fractional difference that still scores > 0.
    """
    if segment_dur <= 0 or candidate_dur <= 0:
        return 0.0
    ratio = min(segment_dur, candidate_dur) / max(segment_dur, candidate_dur)
    # ratio in (0,1]; map [1-tolerance, 1] -> [0,1]
    lo = 1.0 - tolerance
    if ratio <= lo:
        return 0.0
    return (ratio - lo) / (1.0 - lo)


def matched_frames(
    hashes_a: Sequence[str], hashes_b: Sequence[str], threshold: float = 0.85
) -> List[dict]:
    """Return all keyframe pairs whose perceptual similarity >= threshold."""
    out: List[dict] = []
    for i, ha in enumerate(hashes_a):
        for j, hb in enumerate(hashes_b):
            try:
                sim = phash_similarity(ha, hb)
            except ValueError:
                continue
            if sim >= threshold:
                out.append(
                    {
                        "segment_frame": i,
                        "candidate_frame": j,
                        "similarity": round(sim, 4),
                    }
                )
    return out


def cluster_segments(segments: Sequence[dict], threshold: float = 0.85) -> List[dict]:
    """Cluster segments that show the same footage (repeated across the video).

    `segments`: dicts with `segment_id` and `phashes` (hex strings). Greedy
    single-link clustering on best cross-segment perceptual-hash similarity.
    Segments without phashes never match and form singleton clusters.
    Returns [{cluster_id, segment_ids[], phashes[]}].
    """
    clusters: List[dict] = []
    for seg in segments:
        sid = seg.get("segment_id")
        ph = list(seg.get("phashes") or [])
        placed = False
        for cl in clusters:
            sim, _, _ = best_frame_similarity(ph, cl["phashes"])
            if sim >= threshold:
                cl["segment_ids"].append(sid)
                cl["phashes"].extend(ph)
                placed = True
                break
        if not placed:
            clusters.append(
                {
                    "cluster_id": f"cluster_{len(clusters) + 1:03d}",
                    "segment_ids": [sid],
                    "phashes": list(ph),
                }
            )
    return clusters


def link_candidate_to_segments(
    candidate_phashes: Sequence[str], segments: Sequence[dict], threshold: float = 0.85
) -> List[str]:
    """segment_ids whose keyframes match one candidate's media.

    Lets a single Telegram candidate link to multiple input-video timestamps.
    """
    out: List[str] = []
    for seg in segments:
        sim, _, _ = best_frame_similarity(
            candidate_phashes, list(seg.get("phashes") or [])
        )
        if sim >= threshold:
            sid = seg.get("segment_id")
            if sid is not None:
                out.append(sid)
    return out


# ── Optional visual-embedding similarity path ───────────────────────────────
#
# Perceptual hashing (above) is the always-available default: it is pure
# Pillow+imagehash and runs on the pip-only / 512 MB Sinas worker. Embedding
# similarity (e.g. CLIP) is an OPTIONAL, operator-provisioned / local upgrade
# path that can beat phash on re-encoded or cropped footage. It requires a heavy
# model (torch) that does NOT fit the worker, so everything below is import- and
# embedder-guarded: when no embedder is supplied the callers fall back to phash.
# See docs/risks.md (row "Visual embedding similarity") for the evaluation.

# An embedder maps an opaque frame reference (e.g. a file path, PIL image, or
# numpy array) to a fixed-length float embedding. It is INJECTABLE so the cosine
# / selection logic stays unit-testable with fake vectors and zero heavy deps.
Embedder = Callable[[object], Sequence[float]]


@runtime_checkable
class SupportsEmbed(Protocol):
    """Structural type for an object exposing an ``embed(frame) -> vector``."""

    def embed(self, frame: object) -> Sequence[float]: ...


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors, clamped to [0, 1].

    Pure Python/math so it is always importable and testable without numpy or
    any model. Negative cosines (opposite vectors) clamp to 0.0; a zero-norm
    vector yields 0.0. Raises ``ValueError`` on a length mismatch.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("embeddings must be the same length")
    if not vec_a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b, strict=True):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    sim = dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
    # Guard floating-point drift just past the unit bounds.
    return max(0.0, min(1.0, sim))


def best_embedding_similarity(
    embeddings_a: Sequence[Sequence[float]],
    embeddings_b: Sequence[Sequence[float]],
) -> tuple[float, int, int]:
    """Best pairwise cosine similarity across two sets of frame embeddings.

    Analogous to :func:`best_frame_similarity` but for embedding vectors.
    Returns (best_similarity, index_a, index_b), or (0.0, -1, -1) if either set
    is empty. Length-mismatched pairs are skipped rather than raising.
    """
    best = 0.0
    bi, bj = -1, -1
    for i, ea in enumerate(embeddings_a):
        for j, eb in enumerate(embeddings_b):
            try:
                sim = cosine_similarity(ea, eb)
            except ValueError:
                continue
            if sim > best:
                best, bi, bj = sim, i, j
    return best, bi, bj


def embed_frames(frames: Sequence[object], embedder: Embedder) -> List[List[float]]:
    """Embed a sequence of frames with an injected embedder.

    Kept trivial so callers can build embeddings once and reuse them across many
    comparisons. The embedder is any callable; see :func:`load_clip_embedder`
    for the optional CLIP-backed one.
    """
    return [list(embedder(frame)) for frame in frames]


def best_visual_similarity(
    *,
    hashes_a: Sequence[str],
    hashes_b: Sequence[str],
    embeddings_a: Optional[Sequence[Sequence[float]]] = None,
    embeddings_b: Optional[Sequence[Sequence[float]]] = None,
) -> tuple[float, int, int, str]:
    """Best visual similarity, using embeddings when present, else phash.

    Returns (best_similarity, index_a, index_b, method) where ``method`` is
    ``"embedding"`` or ``"phash"``. Embeddings are used only when BOTH sides are
    non-empty; otherwise this falls back to the always-available perceptual-hash
    path so behaviour is unchanged when no embedder is wired in.
    """
    if embeddings_a and embeddings_b:
        sim, i, j = best_embedding_similarity(embeddings_a, embeddings_b)
        return sim, i, j, "embedding"
    sim, i, j = best_frame_similarity(hashes_a, hashes_b)
    return sim, i, j, "phash"


def load_clip_embedder(
    model_name: str = "ViT-B-32",
    pretrained: str = "openai",
) -> Embedder:
    """Build a CLIP-backed :data:`Embedder`, or raise if deps are absent.

    This is the OPTIONAL heavy path. It imports ``open_clip`` + ``torch`` + PIL
    lazily and raises ``RuntimeError`` (chaining the underlying ``ImportError``)
    when they are not installed, so import of this module never pulls torch and
    the pip-only Sinas worker is unaffected. Install with the ``embeddings``
    extra (``uv pip install -e ".[embeddings]"``) on a machine that can host the
    model. The returned callable embeds a PIL image or image path into a
    unit-normalised float vector suitable for :func:`cosine_similarity`.
    """
    try:
        import open_clip  # type: ignore
        import torch  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only with deps
        raise RuntimeError(
            "CLIP embeddings require the optional 'embeddings' extra "
            '(uv pip install -e ".[embeddings]"); this does not run on the '
            "pip-only Sinas worker — phash remains the default. "
            f"Underlying import error: {exc}"
        ) from exc

    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained
    )
    model.eval()

    def _embed(frame: object) -> Sequence[float]:  # pragma: no cover - needs model
        src = frame if hasattr(frame, "mode") else Image.open(frame)  # type: ignore
        img = src.convert("RGB")  # type: ignore[attr-defined]
        with torch.no_grad():
            tensor = preprocess(img).unsqueeze(0)
            feats = model.encode_image(tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats[0].tolist()

    return _embed
