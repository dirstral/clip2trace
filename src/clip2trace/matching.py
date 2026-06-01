"""Visual / text / temporal similarity primitives.

Pure functions used by verify_media_similarity. Kept dependency-light so they
import and test without OpenCV/Telethon present.
"""

from __future__ import annotations

from typing import List, Sequence

PHASH_BITS = 64  # default size of a 64-bit perceptual hash (imagehash 8x8)


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


def best_frame_similarity(hashes_a: Sequence[str],
                          hashes_b: Sequence[str]) -> tuple[float, int, int]:
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


def temporal_alignment_score(segment_dur: float, candidate_dur: float,
                             tolerance: float = 0.25) -> float:
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


def matched_frames(hashes_a: Sequence[str], hashes_b: Sequence[str],
                   threshold: float = 0.85) -> List[dict]:
    """Return all keyframe pairs whose perceptual similarity >= threshold."""
    out: List[dict] = []
    for i, ha in enumerate(hashes_a):
        for j, hb in enumerate(hashes_b):
            try:
                sim = phash_similarity(ha, hb)
            except ValueError:
                continue
            if sim >= threshold:
                out.append({"segment_frame": i, "candidate_frame": j,
                            "similarity": round(sim, 4)})
    return out
