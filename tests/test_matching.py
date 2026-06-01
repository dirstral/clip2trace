import pytest

from clip2trace.matching import (
    hamming_distance, phash_similarity, best_frame_similarity,
    text_overlap_score, temporal_alignment_score, matched_frames,
)


def test_hamming_identical():
    assert hamming_distance("ffff", "ffff") == 0


def test_hamming_one_bit():
    assert hamming_distance("0", "1") == 1


def test_hamming_length_mismatch_raises():
    with pytest.raises(ValueError):
        hamming_distance("ff", "f")


def test_phash_similarity_identical_is_one():
    h = "c3e1c3e1c3e1c3e1"
    assert phash_similarity(h, h) == 1.0


def test_best_frame_similarity_empty():
    assert best_frame_similarity([], ["ffff"]) == (0.0, -1, -1)


def test_best_frame_similarity_finds_match():
    sim, i, j = best_frame_similarity(["0000", "c3e1"], ["ffff", "c3e1"])
    assert sim == 1.0 and i == 1 and j == 1


def test_text_overlap_bounds():
    assert text_overlap_score("", "x") == 0.0
    assert text_overlap_score("live from demo", "live from demo") == 1.0
    assert 0.0 < text_overlap_score("live from demo", "demo live") <= 1.0


def test_temporal_alignment():
    assert temporal_alignment_score(10, 10) == 1.0
    assert temporal_alignment_score(10, 0) == 0.0
    assert temporal_alignment_score(10, 100) == 0.0


def test_matched_frames_threshold():
    frames = matched_frames(["c3e1"], ["c3e1"], threshold=0.85)
    assert frames and frames[0]["similarity"] == 1.0
