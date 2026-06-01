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

## Suggested first issues
- **A (Sinas/agents/docs/coordination)**: #1, #5, #18 (and #23 done).
- **Partner (video/Telegram/matching)**: #3, #9, #13.
- **Both**: #21 demo fixture, #22 pitch.
