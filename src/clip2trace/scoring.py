"""Evidence scoring rubric for ranking Telegram source candidates.

Single source of truth for the weights and confidence labels documented in
skills/evidence-scoring-rubric.md. Keep this in sync with that skill.

Provenance language rule: we never output "original". The strongest label is
"very strong candidate". See report.py and skills/report-style.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

# Rubric weights. MUST sum to 1.0.
WEIGHTS: Dict[str, float] = {
    "visual_similarity": 0.40,      # perceptual/visual match of keyframes
    "handle_watermark": 0.15,       # visible @handle / watermark match
    "ocr_caption_query": 0.15,      # OCR / caption / query text match
    "predates_input": 0.15,         # Telegram post predates input video / date hint
    "temporal_alignment": 0.05,     # duration / temporal alignment of the segment
    "channel_relevance": 0.05,      # channel / source relevance
    "forward_repost": 0.05,         # forward / repost metadata
}

# (lower_bound_inclusive, label). Checked high-to-low.
CONFIDENCE_BANDS = [
    (0.85, "very_strong"),
    (0.70, "strong"),
    (0.50, "plausible"),
    (0.30, "weak"),
    (0.0, "reject"),
]

REJECT_THRESHOLD = 0.30


def _assert_weights() -> None:
    total = round(sum(WEIGHTS.values()), 6)
    if total != 1.0:
        raise ValueError(f"Rubric weights must sum to 1.0, got {total}")


def clamp01(x: float) -> float:
    """Clamp a value to the [0, 1] range."""
    if x != x:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, float(x)))


@dataclass
class EvidenceScores:
    """Per-dimension scores in [0, 1]. Missing dimensions default to 0.0."""

    visual_similarity: float = 0.0
    handle_watermark: float = 0.0
    ocr_caption_query: float = 0.0
    predates_input: float = 0.0
    temporal_alignment: float = 0.0
    channel_relevance: float = 0.0
    forward_repost: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {k: clamp01(getattr(self, k)) for k in WEIGHTS}


def overall_confidence(scores: EvidenceScores) -> float:
    """Weighted sum of evidence dimensions, clamped to [0, 1]."""
    _assert_weights()
    d = scores.as_dict()
    return clamp01(sum(WEIGHTS[k] * d[k] for k in WEIGHTS))


def confidence_label(score: float) -> str:
    """Map a confidence score to a human label per the rubric bands."""
    s = clamp01(score)
    for lower, label in CONFIDENCE_BANDS:
        if s >= lower:
            return label
    return "reject"


def is_rejected(score: float) -> bool:
    return clamp01(score) < REJECT_THRESHOLD


@dataclass
class RankedResult:
    candidate_id: str
    confidence: float
    confidence_label: str
    rejected: bool
    evidence: Dict[str, float] = field(default_factory=dict)
    caveats: list = field(default_factory=list)


def score_candidate(candidate_id: str, scores: EvidenceScores,
                    caveats: list | None = None) -> RankedResult:
    """Compute confidence + label + standard caveats for one candidate."""
    conf = overall_confidence(scores)
    caveats = list(caveats or [])
    if scores.visual_similarity < 0.3:
        caveats.append("Weak visual evidence; match may be coincidental.")
    if scores.predates_input < 0.5:
        caveats.append("Could not confirm the Telegram post predates the input video.")
    caveats.append("Telegram post may itself be a repost, not the earliest appearance.")
    return RankedResult(
        candidate_id=candidate_id,
        confidence=conf,
        confidence_label=confidence_label(conf),
        rejected=is_rejected(conf),
        evidence=scores.as_dict(),
        caveats=caveats,
    )
