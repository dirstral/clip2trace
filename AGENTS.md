# CLAUDE.md

## Project

clip2trace is a [Sinas](https://docs.sinas.co) package for **Telegram source
tracing of reused footage in edited videos**. It scans an edited video, detects
likely reused footage segments, generates global Telegram search queries from
visual/contextual clues, retrieves public Telegram candidate posts, verifies
candidate media with visual/text/timing evidence, and produces a **provenance
report** with timestamps, Telegram links, confidence scores, and caveats.

Global search is _retrieval, not proof_; **visual verification is the
differentiator**. clip2trace finds **likely Telegram source candidates** — it
never claims to have found "the original". Start at [README.md](README.md) and
[docs/architecture.md](docs/architecture.md).

> **Scope guard.** Provenance and source tracing only. No tactical analysis,
> target identification, military advice, or conflict geolocation. Use "edited
> video", "reused footage segment", "candidate source segment", "Telegram source
> candidate", "provenance report" — never "broadcast"/"compilation" as the
> product category.

## Repository layout

- `sinas-package.yaml`: the Sinas package — 11 functions, 5 agents, 3 skills, 6 collections, 6 state stores, dashboard component, manifest. **Authoritative deployable function code is the inline `code:` blocks here.**
- `sinas-config.yaml`: custom roles/permissions (`kind: SinasConfig`, applied before the package).
- `src/clip2trace/`: reusable, **tested** core library (`scoring`, `matching`, `telegram_search`, `video`, `telegram_media`, `report`, `storage`, `schemas`).
- `functions/`: dev copies of the function handlers (`handler(input_data, context)`). They import `clip2trace.*` for readability — but the sandbox can't, so they carry self-contained fallbacks.
- `agents/`, `skills/`: agent prompts + skill content (cautious provenance language, scoring rubric, report style).
- `components/dashboard.jsx`: Sinas component skeleton.
- `scripts/`: `create_issues.{sh,py}`, `make_demo_fixture.py`, `bootstrap_telegram_session.py`.
- `tests/`: pytest suite + JSON fixtures.
- `docs/`: architecture, implementation-spec, data-model, api-contracts, sinas-setup, telegram-global-search, demo-plan, risks, issue-plan, dashboard-wireframe.
- `docs/research/`: investigation logs — Sinas, runtime diagnostics, Telegram global-search feasibility. **Read these before touching the package or Telegram code.**

## Build and test (uv)

This project uses **uv** for Python — do not use bare `pip`/`venv`.

```bash
uv venv
uv pip install -e ".[dev]"              # core + pytest
uv pip install -e ".[video,telegram]"   # optional: opencv/scenedetect/telethon
uv run --with pytest pytest -q          # run the suite (24 tests, must stay green)
uv run python scripts/make_demo_fixture.py --check   # validate demo fixtures
```

## Sinas commands

The CLI needs **Node/npm** (not installed in the current dev box — install Node
first, or run from a machine that has it). Never commit `./.sinas/config.json`.

```bash
npm i -g @sinas/cli
sinas login        # prompts instance_url + admin_token
sinas validate     # validates sinas-config.yaml + sinas-package.yaml
sinas preview
sinas install      # applies sinas-config.yaml (roles), then the package
sinas status
```

Fallback if the CLI is unavailable: validate/install via the Management API
(`POST /api/v1/packages/preview|install`). See [docs/sinas-setup.md](docs/sinas-setup.md).

## Official Sinas skills — use them, they're the source of truth

The Sinas team ships two coding-agent skills at
[github.com/sinas-platform/skills](https://github.com/sinas-platform/skills).
They are **more authoritative than anything in this repo** for Sinas mechanics —
the package YAML field names here were partly inferred, so when they disagree,
the skill wins.

| Skill                  | Authoritative for                                                                                                                                  | Consult it before…                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `sinas-package-author` | SinasPackage YAML schema, per-resource patterns, naming, manifests, variables/secrets, dependencies, the strict-schema "don't invent fields" rules | editing `sinas-package.yaml` / `sinas-config.yaml`, or debugging `sinas validate` |
| `sinas-app`            | building the React+Vite+TS app that talks to Sinas via `@sinas/sdk` (auth modes, calling queries/functions/chats, when to extend the package)      | building/wiring `components/dashboard.jsx` (#19, #20)                             |

**Install them locally (one time):**

```bash
bash scripts/setup_sinas_skills.sh   # copies both into .claude/skills/
```

This drops them into `.claude/skills/` so Claude Code auto-discovers them in this
project. They are **AGPL-3.0** and clip2trace is also **AGPL-3.0-or-later**, so
they're license-compatible; `.claude/skills/` is still **gitignored** so the
skills stay fresh from upstream (re-run the script to refresh) rather than
vendoring stale copies. Also available: `@sinas/cli`
(`npm i -g @sinas/cli`) and the scaffolder `npx @sinas/create-app` (we did not
scaffold with it; integrate by hand).

**How to get maximum value:**

- When a task touches Sinas resources, open/consult the matching skill **first**
  and follow its exact field names — then reconcile `sinas-package.yaml` and the
  "inferred-field caveats" in [docs/research/sinas-investigation.md](docs/research/sinas-investigation.md).
- Treat the skill as the resolver for every "is this the right YAML key?"
  question, especially for collections/stores/components (our least-certain
  fields).
- If a skill contradicts our docs, **fix our docs/YAML to match the skill** and
  note it in the investigation log.

## MCP tools — prefer them over guessing

Several MCP servers are connected. Reach for them by default for the work below
instead of working from memory or shelling out:

| Server | Use it for |
|---|---|
| `github` | Issues + PRs in `dirstral/clip2trace`: create branches, open/update PRs, request reviews, search code/issues. **Preferred over the `gh` CLI** for the issue/ownership workflow (below) and the branch→PR flow. |
| `context7` | Pull **current** library/SDK docs before writing code against them — Telethon, opencv, scenedetect, `@sinas/sdk`, React/Vite. Use it even for familiar libs; don't rely on stale recall. |
| `playwright` | Browser automation / visual checks for the dashboard component (`components/dashboard.jsx`, #19/#20). |
| `duckduckgo` | Web search backing the `docs/research/` investigation logs (Telegram global-search feasibility, Sinas mechanics). |
| `sequential-thinking` | Structured multi-step reasoning on hard pipeline / scoring / verification design problems. |

Other personal MCP servers (e.g. Gmail/Calendar/Drive) may also be connected but
are not part of the clip2trace workflow — ignore them unless explicitly asked.

## Working conventions

- **Never capitalise the name** — always `clip2trace`, in code, docs, and prose. Guard it: grep for any capitalised spelling of the name and expect zero matches.
- **Provenance language is non-negotiable.** Never emit "original" / "confirmed original" / "the original post" in automated output. Use "likely Telegram source candidate", "earlier known Telegram appearance", "best candidate found". `src/clip2trace/report.py` sanitises banned phrases and a test asserts no "original" leaks — keep both.
- **Do not invent Sinas YAML fields.** The strict schema rejects unknown keys. Consult the `sinas-package-author` skill (see above) for exact field names — it's the resolver. Field names for collections/stores/components are inferred camelCase (no verbatim example exists) — confirm with the skill + `sinas validate` and fix `sinas-package.yaml` if rejected. Don't create users, roles, or LLM providers in the package; reference the existing Claude provider via the `PRIMARY_LLM` variable.
- **Functions are sandboxed.** They can only use admin-approved deps (`spec.dependencies`) and **cannot import `src/clip2trace`** at runtime. Keep the YAML inline `code:` blocks self-contained and authoritative; the library is for tests + reference. Secrets (`context["secrets"]`) are only available in `sharedPool: true` functions.
- **Respect container limits**: 512 MB RAM, 1 CPU, 1 GB disk, 100 MB `/tmp`, 300 s timeout. Chunk/stream video; bound downloads; long steps run async (`/execute/async` → poll `/executions/{id}`).
- **Telegram is risky** — `channels.searchPosts` is user-account only, free-text is metered/paid, flood-waits happen. Always keep the demo/cached/manual fallback; the search function must surface `live_unavailable` explicitly and **never silently fake a live search**.
- **Never commit secrets or media**: `.env`, `.sinas/`, `*.session`, session strings, Telegram credentials, downloaded media, private datasets. All are gitignored — keep it that way.
- Prefer **small, testable functions** over one giant handler. If behaviour changes, update tests and docs in the same change.
- **Never commit or push directly to `main`.** Always work on a feature branch and open a **PR** against `main` (use the `github` MCP — `create_branch`, `create_pull_request`), then let it be reviewed/merged.
- **Commit messages follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):** `type: description` or `type(scope): description` (the scope is optional). Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build`, `ci`, `perf`, `style`; use `!` or a `BREAKING CHANGE:` footer for breaks. Lowercase the description, keep the subject ≤ ~72 chars, put detail in the body. **Do not add any AI / `Co-Authored-By` self-attribution trailer.**

## Issue & ownership workflow

Issues live in `dirstral/clip2trace` (GitHub). Canonical issue source is
`scripts/create_issues.sh`; the plan + division is in
[docs/issue-plan.md](docs/issue-plan.md).

- Labels: `area:*`, `mvp`/`stretch`/`risk`/`blocked`/`good-first-task`, and ownership `owner:ark` / `owner:ali` / `owner:both`.
- **`owner:either`** = floatable: whoever is ahead can pick it up; the `owner:*` assignment is the default plan, not a lock.
- **Ali (`Ali-Bilge`) does not do Telegram.** All `area:telegram` work plus #3 (runtime probe touches Telethon) is **Ark-only** and not floatable.
- Video/clue pipeline dependency chain (all Ali): **#9 → #10 → #11 → #13**; the only cross-person seam is **#11 → #13** (Ali → Ark) over the `SegmentClues` contract in [docs/data-model.md](docs/data-model.md).
- When you take a floatable issue assigned to the other person, reassign it: `gh issue edit <n> --add-assignee @me --remove-assignee <them>`.

## Pre-commit checklist

- [ ] `uv run --with pytest pytest -q` is green
- [ ] No capitalised spelling of the name anywhere
- [ ] No secrets/media staged (`git status` clean of `.env`, sessions, video)
- [ ] No invented Sinas YAML fields; `sinas validate` re-run if the package changed
- [ ] No "original"/overclaiming language in automated output
- [ ] Docs/tests updated alongside behaviour changes
- [ ] Changes are on a feature branch with an open PR (never pushed to `main`)

## Known gotchas / blockers

- **No Sinas instance number (X) or admin token** available to automation → `sinas validate/preview/status`, live API checks, and Claude provider/default-model verification cannot run. URLs stay as env vars (`SINAS_BASE_URL=https://via-X.sinas.wearebrain.com`, console `:51245`). See [docs/research/sinas-investigation.md](docs/research/sinas-investigation.md).
- **No Node/npm here** → `@sinas/cli` can't run locally; use the Management API fallback or a machine with Node.
- **Sinas package field caveats**: `MAX_VIDEO_MB` is a `text` variable (no numeric type); secret variables can't be conditionally required, so Telegram secrets are `required: false` and enforced at runtime instead.
- **Telegram session string = full account access.** Generate it once locally with `scripts/bootstrap_telegram_session.py`, store as a Sinas secret, rotate if leaked.
- clip2trace is **AGPL-3.0-or-later** (matches the Sinas platform/CLI/skills). The official skills are installed locally and gitignored to stay upstream-fresh, not for license reasons.
