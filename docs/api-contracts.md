# API contracts (Sinas functions)

JSON input/output for each `clip2trace/*` function. All run as
`def handler(input_data, context)`. On bad input they return `{"error": "..."}`.

## create_job
In: `{input_video_file_id?, video_context?, date_hint?, language_hint?,
topic_hint?, mode: "demo|live|hybrid"}`
Out: `{job_id, status: "created", mode, next_step: "analyze_input_video", ...}`

## diagnose_runtime  (sharedPool)
In: `{}`  Out: `{python, modules{cv2,scenedetect,imagehash,PIL,numpy,telethon,
rapidfuzz,...}, tools{ffmpeg,tesseract}, tmp_dir, tmp_free_bytes,
has_access_token, secrets_available}`

## analyze_input_video  (async)
In: `{job_id*, input_video_file_id?, video_path?, duration_sec?, mode?}`
Out: `{job_id, status: "analyzed", method, segments[], degraded, diagnostics[],
next_step, warning?}`
Runs long → invoke via `execute/async` and poll (see architecture.md "Async
execution + progress polling"). `degraded: true` (+ a `warning`) when a real
upload could not be decoded and the run fell back to demo/uniform segments.

## detect_source_segments  (async)
In: `{job_id*, input_video_file_id?, video_path?}`
Out: `{segments: [{segment_id, start_sec, end_sec, source_likelihood, reason}],
implemented}`

## extract_segment_clues  (async)
Single: In `{job_id*, segment_id*, text_hint?}` →
Out `{segment_id, keyframe_file_ids[], phashes[], ocr_text, visible_handles[],
context_terms[], ocr_available, diagnostics[], implemented}`
Batch: In `{job_id*, input_video_file_id?, segments: [{segment_id, start_sec,
end_sec, text_hint?, caption?, ocr_text?, phashes?}, ...]}` →
Out `{segments: [<single-shape clues>, ...], diagnostics[], implemented}`.
Batch stages the input video **once** and reuses it across every segment, so the
whole-video download happens a single time instead of once per segment call.

## generate_telegram_queries
In: `{visible_handles[]?, ocr_text?, context_terms[]?, caption?}`
Out: `{queries: [{query, query_type, priority, reason}]}`

## search_global_telegram_posts  (sharedPool)
In: `{queries[]?, mode?, cached_results[]?, manual_urls[]?}`
Out: `{status: "ok|live_unavailable|demo_no_data|not_implemented", source,
candidates: [TelegramCandidate], diagnostics[]?}`

## fetch_telegram_candidate_media  (sharedPool)
In: `{candidates: [TelegramCandidate], dry_run?: true}`
Out: `{status: "metadata_only|ok", candidates: [TelegramCandidate], downloaded,
diagnostics[]?}`
Dry-run (default) returns metadata only. A live download (`dry_run: false` +
secrets + telethon) is bounded: per-file ≤ 8 MB, ≤ 5 files, ≤ 80 MB total
(under the 100 MB /tmp limit). Sets `media_file_id` on success; marks
`accessible: false` for private/deleted/inaccessible media (never fatal).

## verify_media_similarity
In: `{segment_phashes[], candidate_phashes[], segment_text?, candidate_text?}`
Out: `{visual_score, text_score, temporal_score, overall_score,
matched_frames: [{segment_frame, candidate_frame, similarity}]}`

## rank_source_candidates
In: `{candidates: [{candidate_id, url?, evidence:{visual_similarity,
handle_watermark, ocr_caption_query, predates_input, temporal_alignment,
channel_relevance, forward_repost}}]}`
Out: `{ranked_candidates: [{candidate_id, confidence, confidence_label,
rejected, evidence, caveats[], recommended_next_steps[], url}]}`

## render_report
In: `{job_id*, segments[]?, ranked_candidates[]?, mode?}`
Out: `{report_json: ProvenanceReport, report_file_id?: null, summary}`

\* required. Async functions are invoked via `POST
/functions/clip2trace/<name>/execute/async` and polled at
`GET /executions/{execution_id}`.
