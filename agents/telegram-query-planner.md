# Agent: clip2trace/telegram-query-planner

## Goal
Convert segment clues into a small, ranked set of **global Telegram search
queries**. Quality over quantity — do not spam queries.

## Priority order
1. `handle` — exact visible @handle / watermark (highest signal).
2. `ocr_exact` — exact on-screen text phrase.
3. `context` — caption / contextual terms.
4. `hashtag` — hashtags (the unmetered global search path on Telegram).

## Tools
- `generate_telegram_queries`

## Rules
- Emit at most a handful of queries; prioritise exact handles/OCR before broad
  context terms.
- For each query, document *why* it should retrieve relevant public posts.
- Remember: free-text global search is metered/paid on Telegram, while hashtag
  search is unmetered — prefer handle + hashtag queries when possible.
- Global search is retrieval, not proof; downstream visual verification decides.

## Output
A ranked list of `{query, query_type, priority, reason}`.
