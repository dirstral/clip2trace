# Dashboard wireframe

Component `clip2trace/dashboard` (skeleton in `components/dashboard.jsx`).

## States
1. **Configure** — instance status (GET /auth/me), mode select (demo/hybrid/live).
2. **Select video** — pick/upload to `clip2trace/input-videos`.
3. **Start** — call `create_job`.
4. **Progress** — show `execution_id`/`job_id`; poll `GET /executions/{id}` for
   async analyze/search/verify steps; show failures.
5. **Segments** — cards: timestamp range, source_likelihood, type, clues.
6. **Query plan** — ranked queries with type + reason.
7. **Candidates** — cards: channel, post time, link, caption, accessibility.
8. **Evidence** — per candidate: visual/text/temporal scores, matched frames.
9. **Report** — final provenance report: confidence + label + caveats; clear
   "likely candidate" framing; never "confirmed original".

```
+--------------------------------------------------------+
| clip2trace        [demo v]            instance: OK      |
+--------------------------------------------------------+
| [1 video] -> [2 start] -> [3 progress ===>  60%]        |
+--------------------------------------------------------+
| Segments            | Telegram candidates               |
| seg_001 12.0-24.5   | @demo_channel /4521  (strong 0.78) |
|  likelihood 0.81    |  visual 0.95 text 0.6 predates yes |
|  @demo_channel      |  [open in Telegram]                |
+--------------------------------------------------------+
| Report: 1 likely candidate. Caveats: retrieval != proof |
+--------------------------------------------------------+
```

## Wiring status
Skeleton renders state navigation + demo job. Full SDK wiring (function calls,
polling, evidence views) is tracked in issues "Add clip2trace dashboard
skeleton" and "Wire async execution and progress polling".
