# clip2trace — 5-minute demo runbook

A step-by-step for the hackathon pitch. Demonstrates **Sinas** (the organizer's
platform) and shows a **real video traced to a real Telegram channel**, live,
with zero rate-limit risk.

**The finding (verified):** the input clip `dzerzhinsky.mp4` is traced to
**https://t.me/meduzalive/143127** at **visual similarity 1.000**.

> Why it's reliable: the demo runs against a **cached, pre-hashed corpus** of
> `@meduzalive` posts (stored as a Sinas demo-fixture) read by the regular-pool
> function `load_demo_corpus`. **No live Telegram calls happen during the demo**,
> so flood-waits / rate limits can't break it. It's deterministic — the same
> message always returns the same result.

---

## 0. One-time setup (do this the morning of — ~3 minutes)

1. Log into the Sinas console: **https://via-10.sinas.wearebrain.com:51245**
2. The two demo videos are already uploaded to `clip2trace/input-videos`:
   `dzerzhinsky.mp4` (the find) and `paris.mp4` (the integrity beat). Nothing to do.
3. **Cold rehearsal:** go to **Agents → `clip2trace/coordinator`**, open its chat,
   paste **Message A** (below), send. In ~2 minutes it should return a report whose
   top candidate is **`meduzalive_143127`, Visual 1.000**. If it does, you're ready.
   (Do this twice so you know the timing.)
4. Open these browser tabs and leave them ready:
   - Tab 1: Sinas console **Dashboard**
   - Tab 2: Sinas console **Agents → clip2trace/coordinator** (the chat)
   - Tab 3: **https://t.me/meduzalive/143127** (the source post — for the reveal)

> If conference wi-fi is shaky, the backup reports are saved in
> `demo/backup/` (`find_dzerzhinsky_report.txt`, `integrity_paris_report.txt`).
> Screenshot them beforehand as a fallback.

---

## 1. The 5-minute run — beat by beat

### Beat 1 · Problem (0:00–0:40) — on the **Dashboard** tab
> "Edited news and war videos reuse footage from everywhere. The key question for
> verification is: *where did this clip originally appear?* clip2trace traces a
> clip back to a likely **Telegram** source — carefully, never overclaiming."

### Beat 2 · Built on Sinas (0:40–1:20) — still on the **Dashboard**
Point at the tiles and say it out loud:
- **Active Agents: 5**, **Functions: 13**, **Tool Calls**.
- Click **Agents** in the left nav → show **`clip2trace/coordinator`** plus the 4
  specialists (`source-segment-analyst`, `telegram-query-planner`,
  `evidence-ranker`, `report-writer`).
> "Everything — agents, functions, secrets, a dashboard component — is built and
> running on **Sinas**. The coordinator orchestrates the specialists across 13
> functions: PyAV video decode, OCR via Claude vision, perceptual hashing,
> Telegram retrieval, and evidence scoring."

### Beat 3 · The live trace — THE MONEY SHOT (1:20–3:30) — **Agents → coordinator chat**
1. In the coordinator's chat box, **paste Message A** (below) and send.
2. It runs the full pipeline live on Sinas (~90–130 s). Narrate while it works:
   *"It's decoding the real video, extracting perceptual hashes, pulling the
   channel's posts, and visually comparing each one."*
3. When the report appears, read the headline:
   > **"Most likely source: https://t.me/meduzalive/143127 — visual score 1.000,
   > all 6 keyframes matched."**
4. **The reveal:** click that `t.me` link (or switch to Tab 3). Put the Telegram
   post **next to the input clip** — it's visibly the same footage (the Dzerzhinsky
   statue clip). 🎯
> "Found in a real Telegram channel — live, on Sinas."

### Beat 4 · We never fabricate (3:30–4:20) — same chat
1. Paste **Message B** (the `paris.mp4` clip — it has **no** match in the corpus).
2. It returns **"No confident match — candidates rejected, ranked list empty."**
> "When there's no real source, it says so — it refuses to invent one. We actually
> caught and fixed a case where the model hallucinated a polished-but-fake source.
> clip2trace is built to never overclaim: every candidate is *'likely, not proof.'*"

### Beat 5 · Close (4:20–5:00)
> "clip2trace turns a reused clip into a **provenance report** — timestamps,
> confidence scores, caveats, and a Telegram link for a human to verify. Next:
> more channels and a content index for discovery. Built entirely on Sinas.
> Thank you."

---

## 2. Exact messages to paste

### Message A — the find (`dzerzhinsky.mp4`)
```
Trace this video to its Telegram source in the meduzalive channel (cached demo corpus):
1) create_job(mode='hybrid', input_video_file_id='dzerzhinsky.mp4').
2) analyze_input_video with input_video_file_id='dzerzhinsky.mp4'.
3) extract_segment_clues ONCE in batch (pass input_video_file_id + the segments array) to get the input's real phashes.
4) load_demo_corpus(channel='meduzalive') — returns cached candidates that ALREADY include phashes. Do NOT call fetch_telegram_candidate_media (no download needed).
5) For EACH candidate, verify_media_similarity(segment_phashes=the input's combined phashes, candidate_phashes=that candidate's phashes).
6) rank_source_candidates, then render_report.
State the single most likely meduzalive source post: its t.me URL and visual score. Likely candidate only — never claim 'the original'.
```

### Message B — the integrity beat (`paris.mp4`)
```
Trace this video to its Telegram source in the meduzalive channel (cached demo corpus):
1) create_job(mode='hybrid', input_video_file_id='paris.mp4').
2) analyze_input_video with input_video_file_id='paris.mp4'.
3) extract_segment_clues ONCE in batch to get the input's phashes.
4) load_demo_corpus(channel='meduzalive') — cached candidates WITH phashes. Do NOT download.
5) verify_media_similarity for EACH candidate (segment_phashes vs candidate phashes).
6) rank_source_candidates, render_report.
If nothing matches confidently, say so plainly. Likely candidates only — never claim 'the original'.
```

---

## 3. What "it worked" looks like

- **Message A →** report with **🥇 `meduzalive_143127`**, **Visual 1.000**, overall
  0.75, label *"likely candidate"*, caption about a Dzerzhinsky statue near Nizhny
  Tagil. (Runtime ~2 min.)
- **Message B →** **"No confident match"**, both candidates **rejected**,
  `ranked_candidates: []`.

Both are **deterministic** — re-sending the same message gives the same result.

---

## 4. If something breaks

- **The find is deterministic** (cached corpus, regular-pool function). If the chat
  is slow or errors once, just **re-send Message A** — it will return `143127`.
- **Do NOT** ask it to run in `mode='live'` during the demo — that hits Telegram and
  can flood-wait. The cached/demo path is the safe one.
- **Last resort:** show the saved reports/screenshots from `demo/backup/`.

---

## 5. Notes (for your own awareness, not the pitch)

- The two confirmed 1.000 matches in the corpus are `dzerzhinsky.mp4 → 143127` and
  `clip_0602.mp4 → 143089` — either works as the "find" (use `dzerzhinsky`).
- The corpus fixture lives at `clip2trace/demo-fixtures/meduzalive_corpus.json`
  (5 real posts with phashes). `load_demo_corpus` reads it on the regular worker
  pool, which is healthy; the `sharedPool` workers are `/tmp`-exhausted and are
  deliberately avoided for the demo.
- Cautious-language guardrail is real and on by default: the report never says
  "the original," and on an empty result it reports "no confident source" instead
  of inventing one.
