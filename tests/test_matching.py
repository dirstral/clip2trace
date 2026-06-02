import pytest

from clip2trace.matching import (
    best_frame_similarity,
    cluster_segments,
    hamming_distance,
    link_candidate_to_segments,
    matched_frames,
    phash_similarity,
    temporal_alignment_score,
    text_overlap_score,
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


def test_cluster_segments_groups_repeated_footage():
    segs = [
        {"segment_id": "seg_001", "phashes": ["c3e1c3e1c3e1c3e1"]},
        {"segment_id": "seg_002", "phashes": ["0f0f0f0f0f0f0f0f"]},
        {"segment_id": "seg_003", "phashes": ["c3e1c3e1c3e1c3e1"]},  # repeat of 001
    ]
    clusters = cluster_segments(segs)
    by_members = sorted(sorted(c["segment_ids"]) for c in clusters)
    assert ["seg_001", "seg_003"] in by_members
    assert ["seg_002"] in by_members


def test_cluster_segments_without_phashes_are_singletons():
    clusters = cluster_segments(
        [{"segment_id": "a", "phashes": []}, {"segment_id": "b", "phashes": []}]
    )
    assert len(clusters) == 2


def test_link_candidate_to_multiple_segments():
    segs = [
        {"segment_id": "seg_001", "phashes": ["c3e1c3e1c3e1c3e1"]},
        {"segment_id": "seg_002", "phashes": ["0f0f0f0f0f0f0f0f"]},
        {"segment_id": "seg_003", "phashes": ["c3e1c3e1c3e1c3e1"]},
    ]
    linked = link_candidate_to_segments(["c3e1c3e1c3e1c3e1"], segs)
    assert linked == ["seg_001", "seg_003"]
