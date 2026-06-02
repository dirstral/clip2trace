# clip2trace

**Telegram source tracing for reused footage in edited videos.**

clip2trace scans an edited video, detects likely reused footage segments,
generates global Telegram search queries from visual/contextual clues, retrieves
public Telegram candidate posts, verifies candidate media with
visual/text/timing evidence, and produces a **provenance report** with
timestamps, Telegram links, confidence scores, and caveats.

clip2trace finds **likely Telegram source candidates** — it never claims to have
found "the original" post. Global search is *retrieval*; visual verification is
the differentiator.

> Scope: provenance and source tracing only. No tactical analysis, target
> identification, military advice, or conflict geolocation.

## Architecture at a glance

A [Sinas](https://docs.sinas.co) package (`clip2trace`) with:

- **Functions** (`functions/`, declared in `sinas-package.yaml`) — the pipeline
  steps: `create_job → analyze_input_video → detect_source_segments →
  extract_segment_clues → generate_telegram_queries →
  search_global_telegram_posts → fetch_telegram_candidate_media →
  verify_media_similarity → rank_source_candidates → render_report`.
- **Agents** (`agents/`) — coordinator + 4 specialists.
- **Skills** (`skills/`) — methodology, scoring rubric, report style.
- **Collections / state stores** — media + job/segment/result state.
- **Core library** (`src/clip2trace/`) — reusable, tested scoring/matching/query
  logic.

See [docs/architecture.md](docs/architecture.md).

## Quick start (local dev with uv)

```bash
# 1. Python deps (uv)
uv venv
uv pip install -e ".[dev,video,telegram]"   # video/telegram extras are optional

# 2. Run the tests (no Sinas instance needed)
uv run --with pytest pytest -q

# 3. Validate the demo fixture
uv run python scripts/make_demo_fixture.py --check
```

## Sinas setup

See [docs/sinas-setup.md](docs/sinas-setup.md). In short:

```bash
cp .env.example .env          # fill SINAS_BASE_URL etc. (never commit .env)
npm i -g @sinas/cli           # needs Node
sinas login                   # prompts for instance_url + admin_token
sinas validate                # validate sinas-config.yaml + sinas-package.yaml
sinas preview
# `sinas install` cannot pass package variables (e.g. the required PRIMARY_LLM),
# so install via the Management API helper, which sends them:
python3 scripts/sinas_install.py        # installs the package with PRIMARY_LLM=Claude
sinas status
# After approving deps, click "Reload Workers" in the console so they load.
```

## Demo vs live mode

- **demo / hybrid (default)**: runs the full pipeline with cached/manual
  Telegram candidates — no live Telegram account needed. Use this for the demo.
- **live**: enables global Telegram search via Telethon. Requires a **user
  account** session and Telegram secrets stored in Sinas. See
  [docs/telegram-global-search.md](docs/telegram-global-search.md). Treat live
  search as flaky (flood-waits, metered free-text search) — keep the demo path.

## Running a job

A job traces one input video. Start it via the **coordinator** agent (it
orchestrates the whole pipeline) or by calling `create_job` directly:

```bash
# Direct function call (returns the job record; status starts at "created"):
curl -sX POST "$SINAS_BASE_URL/functions/clip2trace/create_job/execute" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"input": {"mode": "demo"}}'
```

The coordinator agent then runs `analyze_input_video → … → render_report` and
**persists job lifecycle state** (`created → analyzing → … → done`, or `failed` +
error) to the `clip2trace/jobs` state store, segments to `clip2trace/segments`,
and the final report to the `clip2trace/reports` collection. Functions on the
managed worker are pure transforms (they return data); the agents hold the store
/ collection access and do the persistence. Long analyses run via
`/execute/async` + polling (see [docs/architecture.md](docs/architecture.md)).

## Repo layout

```
sinas-package.yaml      Sinas package (functions/agents/skills/collections/stores/component/manifest)
sinas-config.yaml       Custom roles/permissions (kind: SinasConfig)
src/clip2trace/         Reusable, tested core library
functions/              Dev copies of Sinas function handlers
agents/  skills/        Agent prompts + skill content
components/dashboard.jsx Component skeleton
scripts/                Issue creation, demo fixture, Telegram session bootstrap
tests/                  pytest suite + fixtures
docs/                   Architecture, spec, data model, API contracts, setup, demo, risks, issues
docs/research/          Investigation logs (Sinas, runtime, Telegram)
```

## Safety & secrets

Never commit: `.env`, `.sinas/`, Telegram credentials, session strings, or
downloaded media. See `.gitignore` and [docs/risks.md](docs/risks.md).

License: **AGPL-3.0-or-later** (see `LICENSE`) — © 2026 dirstral. clip2trace is
a Sinas package, and the Sinas platform/CLI/skills are AGPL-3.0, so clip2trace
matches them. The official Sinas skills are installed locally via
`scripts/setup_sinas_skills.sh` (kept fresh from upstream, not vendored).
