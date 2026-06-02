import math

import pytest

from clip2trace.matching import (
    best_embedding_similarity,
    best_frame_similarity,
    best_visual_similarity,
    cluster_segments,
    cosine_similarity,
    embed_frames,
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


# ── Embedding-similarity path (no heavy deps; injected fake vectors) ─────────


def test_cosine_identical_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_scaled_vector_is_one():
    # Cosine is scale-invariant: a re-encoded frame that scales the embedding
    # should still read as identical.
    assert cosine_similarity([1.0, 0.0], [4.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_clamps_to_zero():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_cosine_zero_norm_is_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_empty_is_zero():
    assert cosine_similarity([], []) == 0.0


def test_cosine_length_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 2.0])


def test_cosine_known_value():
    # 45 degrees between (1,0) and (1,1) -> cos = 1/sqrt(2).
    assert cosine_similarity([1.0, 0.0], [1.0, 1.0]) == pytest.approx(
        1.0 / math.sqrt(2)
    )


def test_best_embedding_similarity_empty():
    assert best_embedding_similarity([], [[1.0]]) == (0.0, -1, -1)


def test_best_embedding_similarity_finds_match():
    sim, i, j = best_embedding_similarity(
        [[1.0, 0.0], [0.0, 1.0]],
        [[0.0, 2.0], [9.0, 0.1]],
    )
    # a[1]=(0,1) is identical-direction to b[0]=(0,2).
    assert sim == pytest.approx(1.0) and i == 1 and j == 0


def test_best_embedding_similarity_skips_mismatched_lengths():
    # Mismatched-length pairs are skipped, not raised; the valid pair wins.
    sim, i, j = best_embedding_similarity([[1.0, 0.0]], [[1.0, 2.0, 3.0], [2.0, 0.0]])
    assert sim == pytest.approx(1.0) and i == 0 and j == 1


def test_embed_frames_uses_injected_embedder():
    # Fake embedder: map a frame label to a vector. No heavy model involved.
    table = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    embs = embed_frames(["a", "b"], lambda f: table[f])
    assert embs == [[1.0, 0.0], [0.0, 1.0]]


def test_best_visual_similarity_uses_embeddings_when_present():
    sim, i, j, method = best_visual_similarity(
        hashes_a=["0000"],
        hashes_b=["ffff"],  # phash would say dissimilar
        embeddings_a=[[1.0, 0.0]],
        embeddings_b=[[2.0, 0.0]],  # embeddings say identical
    )
    assert method == "embedding"
    assert sim == pytest.approx(1.0) and i == 0 and j == 0


def test_best_visual_similarity_falls_back_to_phash_without_embeddings():
    sim, i, j, method = best_visual_similarity(
        hashes_a=["c3e1"],
        hashes_b=["c3e1"],
    )
    assert method == "phash"
    assert sim == 1.0 and i == 0 and j == 0


def test_best_visual_similarity_falls_back_when_one_side_lacks_embeddings():
    # Only one side has embeddings -> cannot compare embeddings, use phash.
    sim, _, _, method = best_visual_similarity(
        hashes_a=["c3e1"],
        hashes_b=["c3e1"],
        embeddings_a=[[1.0, 0.0]],
        embeddings_b=None,
    )
    assert method == "phash" and sim == 1.0


def test_load_clip_embedder_real_model():
    # Only runs where the optional 'embeddings' extra is installed; CI skips it.
    pytest.importorskip("open_clip")
    pytest.importorskip("torch")
    from clip2trace.matching import load_clip_embedder

    embedder = load_clip_embedder()
    assert callable(embedder)
