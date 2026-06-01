from clip2trace.scoring import (
    WEIGHTS, EvidenceScores, confidence_label, overall_confidence,
    is_rejected, score_candidate,
)


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


def test_overall_confidence_perfect_visual_only():
    scores = EvidenceScores(visual_similarity=1.0)
    assert overall_confidence(scores) == 0.40


def test_overall_confidence_all_max_is_one():
    scores = EvidenceScores(**{k: 1.0 for k in WEIGHTS})
    assert overall_confidence(scores) == 1.0


def test_confidence_labels_bands():
    assert confidence_label(0.90) == "very_strong"
    assert confidence_label(0.75) == "strong"
    assert confidence_label(0.55) == "plausible"
    assert confidence_label(0.35) == "weak"
    assert confidence_label(0.10) == "reject"


def test_rejection_threshold():
    assert is_rejected(0.29)
    assert not is_rejected(0.30)


def test_score_candidate_adds_caveats_and_never_says_original():
    res = score_candidate("c1", EvidenceScores(visual_similarity=0.1))
    assert res.rejected is True
    assert any("repost" in c.lower() for c in res.caveats)
    assert all("original" not in c.lower() for c in res.caveats)


def test_clamping_out_of_range():
    scores = EvidenceScores(visual_similarity=5.0)  # clamps to 1.0
    assert overall_confidence(scores) == 0.40
