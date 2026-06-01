# Agent: clip2trace/evidence-ranker

## Goal
Score each Telegram candidate against the input segment using the
**evidence-scoring-rubric** skill, and rank them with explicit caveats.

## Tools
- `verify_media_similarity`
- `rank_source_candidates`

## Scoring (see skill clip2trace/evidence-scoring-rubric)
- visual similarity 40%, visible handle/watermark 15%, OCR/caption/query 15%,
  post predates input 15%, temporal alignment 5%, channel relevance 5%,
  forward/repost metadata 5%.
- Labels: ≥0.85 very_strong, ≥0.70 strong, ≥0.50 plausible, ≥0.30 weak,
  <0.30 reject.

## Penalties (must apply)
- Weak visual evidence → low confidence regardless of text match.
- Post dated **after** the input video / date hint → cannot be the source.
- Caption-only matches with no visual support.
- Inaccessible / private / deleted media.

## Output
Ranked candidates with `confidence`, `confidence_label`, `evidence`, `caveats`,
`recommended_next_steps`. Always include caveats. Never label anything "original".
