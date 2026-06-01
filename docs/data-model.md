# Data model

Canonical shapes (see `src/clip2trace/schemas.py`). Stored across Sinas state
stores; media in collections.

## Job  (store: clip2trace/jobs, key: job_id)
| field | type | notes |
|---|---|---|
| job_id | str | `job_<execution_id>` |
| status | enum | created/analyzing/searching/verifying/ranking/reporting/done/failed |
| mode | enum | demo / live / hybrid |
| input_video_file_id | str? | collection file id |
| video_context, date_hint, language_hint, topic_hint | str? | hints |
| progress | float | 0..1 |
| error | str? | persisted failure message |

## SourceSegment  (store: clip2trace/segments)
`segment_id, start_sec, end_sec, source_likelihood (0..1), reason`. Derived:
`duration`.

## SegmentClues
`segment_id, keyframe_file_ids[], phashes[], ocr_text, visible_handles[],
context_terms[], ocr_available`.

## TelegramQuery
`query, query_type (handle|ocr_exact|context|hashtag), priority (1..n), reason`.

## TelegramCandidate  (store: clip2trace/search-results)
`candidate_id, channel, message_id, url, posted_at (ISO8601), caption,
has_media, media_file_id, is_forward, forward_origin, source_query, accessible`.

## MediaMatch  (store: clip2trace/candidate-matches)
`candidate_id, visual_score, text_score, temporal_score, overall_score,
matched_frames[] ({segment_frame, candidate_frame, similarity})`.

## RankedCandidate
`candidate_id, confidence (0..1), confidence_label
(very_strong|strong|plausible|weak|reject), rejected, evidence{dimension→score},
caveats[], recommended_next_steps[], url`.

## ProvenanceReport  (collection: clip2trace/reports)
`job_id, summary, generated_mode, segments[], ranked_candidates[],
label_counts{}, caveats[]`. Never contains the word "original" in automated text.

## Evidence dimensions (RankedCandidate.evidence → scoring rubric)
`visual_similarity, handle_watermark, ocr_caption_query, predates_input,
temporal_alignment, channel_relevance, forward_repost` — each 0..1; weighted per
`skills/evidence-scoring-rubric.md`.
