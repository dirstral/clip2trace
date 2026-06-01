# Skill: evidence-scoring-rubric

Single source of truth for candidate scoring. Mirrors `src/clip2trace/scoring.py`.

## Weights (sum = 1.00)
| Dimension | Weight | Meaning |
|---|---|---|
| visual_similarity | 0.40 | perceptual/visual keyframe match |
| handle_watermark | 0.15 | visible @handle / watermark match |
| ocr_caption_query | 0.15 | OCR / caption / query text match |
| predates_input | 0.15 | Telegram post predates input video / date hint |
| temporal_alignment | 0.05 | duration / temporal alignment |
| channel_relevance | 0.05 | channel / source relevance |
| forward_repost | 0.05 | forward / repost metadata |

`confidence = Σ (weight × dimension_score)`, each dimension in [0, 1].

## Confidence labels
| Score | Label |
|---|---|
| 0.85–1.00 | very_strong |
| 0.70–0.84 | strong |
| 0.50–0.69 | plausible |
| 0.30–0.49 | weak |
| < 0.30 | reject |

## Penalties / caveats (always consider)
- Weak visual evidence caps confidence regardless of text match.
- A post dated **after** the input video cannot be the source (predates = 0).
- Caption-only matches without visual support are weak.
- Inaccessible/private/deleted media → reduce confidence and add a caveat.
- Always add the caveat: "A matched post may itself be a repost."

## Hard rule
Automated output never uses the word "original". Strongest automated label is
"very_strong candidate".
