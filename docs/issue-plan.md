# Issue plan

All issues are created by `scripts/create_issues.sh` (canonical source of titles,
bodies, labels, milestones). Re-runnable; uses `gh`. A `scripts/create_issues.py`
wrapper is provided too.

## Labels
`area:sinas, area:telegram, area:video, area:matching, area:agents, area:ui,
area:docs, area:demo, risk, stretch, mvp, blocked, good-first-task`

## Milestones & issues

### Milestone 0 — Investigation & setup
1. Configure Sinas access and verify Claude provider/model — `area:sinas, mvp`
2. Install and validate Sinas CLI workflow — `area:sinas, mvp`
3. Investigate Sinas function runtime capabilities — `area:sinas, area:video, risk, mvp`
4. Research Telegram global search feasibility with Telethon — `area:telegram, risk, mvp`

### Milestone 1 — Sinas package base
5. Create clip2trace Sinas package skeleton — `area:sinas, mvp`
6. Add clip2trace Sinas collections and state stores — `area:sinas, mvp`
7. Add base function schemas and stubs — `area:sinas, mvp`

### Milestone 2 — Core video pipeline
8. Implement input video job creation and state tracking — `area:sinas, area:video, mvp`
9. Implement candidate reused-footage segment detection — `area:video, mvp`
10. Extract keyframes and visual fingerprints from segments — `area:video, area:matching, mvp`
11. Extract text clues and visible handles from segments — `area:video, area:telegram, mvp`

### Milestone 3 — Telegram retrieval
12. Implement secure Telegram session bootstrap workflow — `area:telegram, risk, mvp`
13. Implement global Telegram post search function — `area:telegram, mvp`
14. Implement Telegram candidate media fetcher — `area:telegram, area:matching, mvp`

### Milestone 4 — Matching & ranking
15. Implement visual similarity verification — `area:matching, mvp`
16. Implement evidence scoring and candidate ranking — `area:matching, area:agents, mvp`
17. Implement provenance report renderer — `area:docs, area:sinas, mvp`

### Milestone 5 — Agents & UI
18. Add coordinator and specialist agents — `area:agents, mvp`
19. Add clip2trace dashboard skeleton — `area:ui, mvp`
20. Wire async execution and progress polling — `area:sinas, area:ui, mvp`

### Milestone 6 — Demo & polish
21. Build controlled demo fixture — `area:demo, mvp`
22. Write final hackathon demo script — `area:demo, area:docs, mvp`
23. Add README with setup and first-run instructions — `area:docs, mvp`
24. Add safety, privacy, and compliance notes — `area:docs, risk`

### Stretch
25. Add repeated segment clustering across an input video — `area:matching, stretch`
26. Add ASR/transcript context extraction — `area:video, stretch`
27. Add OCR upgrade path — `area:video, stretch`
28. Add third-party Telegram search fallback adapter — `area:telegram, stretch`
29. Add HTML report export — `area:ui, area:docs, stretch`
30. Add visual embedding similarity — `area:matching, stretch`

## Ownership division (labels `owner:ark` / `owner:ali` / `owner:both`)

Ali does **not** take the Telegram side, so all `area:telegram` work is Ark's.
Ark also owns the Sinas platform, agents, and coordination/docs; Ali owns the
video pipeline, matching/scoring, report renderer, and UI. Split 14 / 14 / 2.

### Ark (Telegram + Sinas platform + agents + coordination)
- M0: #1 Sinas access, #2 CLI, #3 runtime capabilities (incl. Telethon probe), #4 Telegram feasibility
- M1: #5 package skeleton, #6 collections/stores
- M2: #11 text clues + visible handles (feeds Telegram queries)
- M3: #12 session bootstrap, #13 global search, #14 candidate media fetcher
- M5: #18 agents
- M6: #23 README, #24 safety/privacy
- Stretch: #28 third-party Telegram search adapter

### Ali (video pipeline + matching/scoring + report + UI — no Telegram)
- M1: #7 base function schemas/stubs
- M2: #8 job creation/state, #9 segment detection, #10 keyframes/fingerprints
- M4: #15 visual similarity, #16 scoring/ranking, #17 report renderer
- M5: #19 dashboard skeleton, #20 async wiring/polling
- Stretch: #25 segment clustering, #26 ASR/transcript, #27 OCR upgrade, #29 HTML report, #30 visual embeddings

### Both
- #21 demo fixture, #22 final pitch

## Suggested first issues
- **Ark**: #1 Sinas access → #5 package skeleton → #4/#13 Telegram retrieval.
- **Ali**: #7 function stubs → #9 segment detection → #15 visual similarity.
- **Both**: #21 demo fixture, #22 pitch (after the pipelines meet).
