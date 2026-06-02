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
- **Demo mode (#19):** runs fully offline against a bundled fixture — `create_job`
  → simulated progression → segment cards + candidate cards + cautious report.
  No live instance needed, so the component always renders end-to-end.
- **Live/hybrid (#19/#20):** calls the package functions through the injected
  `sinas` client (`create_job` → `render_report`); the long analysis step is
  enqueued async and the execution is polled for visible progress, with failures
  surfaced in the UI. `job_id` and `execution_id` are shown on the progress view.
- The authoritative deployable source is the component `sourceCode` block in
  `sinas-package.yaml`; `components/dashboard.jsx` is the readable dev copy. A
  test (`tests/test_component_sync.py`) keeps the two in sync.

### Known limitations (full wiring blocked without a live instance)
- The exact `sinas` client method surface for an embedded component is not
  verified here (no Node / `sinas validate` in this box). Calls go through small
  feature-detecting adapters (`callFunction` / `enqueueFunction` / `getExecution`)
  that try the common method names and otherwise surface a clear error — adjust
  the adapters once the live SDK shape is confirmed.
- Live orchestration of the full pipeline (analyze → search → verify → rank) runs
  through the **coordinator agent**, not direct component calls; the component
  currently drives `create_job`/`render_report` and the async-progress UX. Richer
  evidence views (query plan, matched frames) remain follow-ups.
