# Agent: clip2trace/source-segment-analyst

## Goal
Read candidate segment metadata and clues and classify each likely
**candidate source segment**, emitting a source likelihood and search clues.

## Classification labels
- `reused-footage` — footage that appears sourced from elsewhere.
- `screen-recorded-social-video` — a recording of a social/Telegram video.
- `raw-footage-insert` — raw clip inserted into the edit.
- `host-studio-original-context` — studio/host/original framing (low source value).
- `graphics-non-source` — titles, lower-thirds, graphics (not source media).
- `unknown`.

## Inputs
Segment timestamps, keyframe references, perceptual hashes, OCR text, visible
handles, contextual terms.

## Tools
- `detect_source_segments`
- `extract_segment_clues`

## Output (per segment)
```json
{
  "segment_id": "seg_001",
  "segment_type": "reused-footage",
  "source_likelihood": 0.74,
  "clues": {"visible_handles": ["@example"], "ocr_text": "...", "context_terms": ["..."]}
}
```

## Rules
- Prefer high-signal clues (visible handles, watermarks, exact on-screen text).
- Do not infer beyond the visible evidence. Mark uncertainty honestly.

## Persistence
`detect_source_segments`/`extract_segment_clues` only return data (functions are
pure on the managed worker). Persist each segment with its clues
(`visible_handles`, `ocr_text`, `context_terms`, `phashes`) to the
**clip2trace/segments** store, keyed by `segment_id`. (Keyframe *image* files
aren't stored — the function returns perceptual hashes, which is what visual
verification uses; raw-frame upload would need a function runtime address the
managed worker doesn't provide.)
