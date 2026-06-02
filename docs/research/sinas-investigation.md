# Research log: Sinas investigation

_Date: 2026-06-01. Sources: https://docs.sinas.co, https://github.com/sinas-platform/sinas,
https://github.com/sinas-platform/skills (sinas-package-author / sinas-app SKILL.md, @sinas/cli README)._

## A. Sinas instance access — BLOCKED (documented)

- The assigned instance number **X is unknown** and **no admin API token was
  provided** to this run. Therefore live API validation could not run.
- URLs are kept as environment variables only (`.env.example`):
  - `SINAS_BASE_URL=https://via-X.sinas.wearebrain.com`
  - `SINAS_CONSOLE_URL=https://via-X.sinas.wearebrain.com:51245`
- Endpoints to check once access is available (from API research):
  - Runtime OpenAPI: `GET $SINAS_BASE_URL/openapi.json` (interactive `/docs`).
  - Management OpenAPI: `GET $SINAS_BASE_URL/api/v1/openapi.json` (`/api/v1/docs`).
  - Current user: `GET $SINAS_BASE_URL/auth/me` (returns email + roles).
  - LLM providers (management): `GET $SINAS_BASE_URL/api/v1/llm-providers/`.
  - **No dedicated `/info` endpoint was found** in docs; use `/openapi.json` /
    `/auth/me` for liveness instead.
- **Claude provider / default model**: cannot be confirmed without instance
  access. Action: after login, `GET /api/v1/llm-providers/` and confirm a Claude
  provider exists with default model `claude-sonnet-4-6`. If missing/mismatched,
  see issue "Configure Sinas access and verify Claude provider/model".

## B. Package model (confirmed from docs + skills repo)

Top-level package YAML:

```yaml
apiVersion: sinas.co/v1
kind: SinasPackage
package: { name, version, description, author, url }
spec:
  variables: []     manifests: []   collections: []  queries: []
  functions: []     agents: []      skills: []       stores: []
  components: []     connectors: []  templates: []    webhooks: []
  schedules: []      databaseTriggers: []  dependencies: []
```

- **Packages can create**: collections, queries, functions, agents, skills,
  stores, components, connectors, templates, webhooks, schedules,
  databaseTriggers, dependencies, manifests, variables.
- **Packages CANNOT create**: roles (→ `sinas-config.yaml`, `kind: SinasConfig`),
  users, llmProviders, databaseConnections (infra). We therefore **reference**
  the existing Claude provider via the `PRIMARY_LLM` resource_ref variable and
  never create one.
- **Variables**: `name` (UPPER_SNAKE_CASE), `type` ∈
  {text, boolean, enum, resource_ref, secret}, `description`, `required`,
  `default`, `resource` (for resource_ref, e.g. `llm_providers`), `choices`
  (enum), `pattern` (text). Referenced via `${{ vars.NAME }}` (plain string
  substitution, **not** Jinja2). `type: secret` upserts an encrypted Secret.
- **Naming**: namespace kebab-case; functions **snake_case**;
  agents/skills/connectors kebab-case; YAML keys **camelCase**; references are
  `namespace/name`. **Unknown YAML keys are rejected** (strict schema) — do not
  invent fields.
- **Manifest**: `requiredResources: [{type, namespace, name}]`,
  `requiredPermissions`, `optionalPermissions`, `exposedNamespaces`,
  `storeDependencies`. Permission key format `<ns>.<resource>.<action>:<scope>`
  (scope `:own`/`:all`). Readiness: `GET /api/runtime/manifests/{ns}/{name}/status`.

### Function execution model
- Handler: `def handler(input_data, context): -> dict`.
- `context`: `user_id`, `user_email`, `access_token` (JWT, TTL = timeout+5min,
  ≤24h), `execution_id`, `trigger_type`, `chat_id`, and **`secrets`** (decrypted)
  **only in shared-pool / trusted functions** (`sharedPool: true`).
- Schemas: `inputSchema` (pre) + `outputSchema` (post), JSON Schema.
- Sync: `POST /functions/{ns}/{name}/execute`. Async:
  `POST .../execute/async` → `202` + `execution_id`; poll
  `GET /executions/{execution_id}`. Batch: `.../execute/batch` + `GET /batches/{id}`.
- **Dependencies need admin approval** (`spec.dependencies: [{packageName, version?}]`;
  approve via dependency API + `POST /containers/reload`). SDK `sinas==0.1.7`
  preinstalled.
- **Container limits**: 512 MB RAM, 1.0 CPU, 1 GB disk, 300 s timeout,
  `/tmp` 100 MB tmpfs. → **video processing must be chunked / bounded.**

### CLI (@sinas/cli)
- `npm i -g @sinas/cli`; subcommands `login, init, validate, preview, install,
  status, add`. **No `deploy`** (use `install`). Config `./.sinas/config.json`
  (gitignored) → `~/.sinas/config.json`. `login` prompts instance_url +
  admin_token, verifies via `GET /auth/me`.

## C. CLI status in THIS environment — BLOCKED
- **Node/npm are not installed** here, so `@sinas/cli` could not be installed or
  run. `sinas validate / preview / status` were **not executed**. Fallback:
  validate via the Management API once a token is available, or run the CLI from
  a machine with Node. `@sinas/cli` is listed as a devDependency in
  `package.json` for when Node is present.

## D. Skills / license
- `sinas-platform/skills` is **AGPL-3.0**. clip2trace is licensed
  **AGPL-3.0-or-later** (switched from MIT) to be compatible with the Sinas
  ecosystem, so there is no license conflict. The skills are still installed
  locally via `scripts/setup_sinas_skills.sh` and gitignored to stay
  upstream-fresh rather than vendored. The package YAML was authored using the
  field names documented in those skills.

### SDK licenses (checked 2026-06-01) and why we are AGPL-3.0
| Component | Source | License | Bundled/distributed by clip2trace? |
|---|---|---|---|
| `@sinas/sdk` v0.7.0 (JS, used by the dashboard) | `sinas-platform/sinas-js` (npm registry `license` field) | **AGPL-3.0** | **Yes**, if the dashboard is shipped as a build that bundles the SDK |
| `@sinas/cli`, `@sinas/create-app` | `sinas-platform/skills` monorepo | AGPL-3.0 | No — dev tooling only |
| `sinas` (Python SDK, preinstalled in functions) | sinas-platform; runs server-side in the platform sandbox | Unconfirmed (likely AGPL) | No — not redistributed by us; the public PyPI `sinas` v0.2.0 (`github.com/sinas/sinas-sdk`, `docs.sinas.ai`, MIT) is a **namesake**, NOT this SDK — do not rely on it |

**Decision rationale.** The licence choice does not hinge on vendoring the skills
(we don't — they are dev tooling and staleness makes vendoring a net negative).
It hinges on whether clip2trace **distributes or network-serves AGPL code**. The
dashboard imports the **AGPL-3.0 `@sinas/sdk`**; a shipped/served frontend that
bundles it is a combined work, so AGPL attaches. Therefore **AGPL-3.0-or-later is
the correct, conflict-free licence** for clip2trace. A permissive licence
(MIT/Apache-2.0) would only be safe if we committed to never bundling
`@sinas/sdk` (REST-only UI, SDK excluded from the shipped bundle) — more
constraint than it is worth for a Sinas-native app. Calling the Sinas platform
over its API and using the skills as local tooling do **not**, by themselves,
force AGPL; the SDK dependency is the binding reason.

**Follow-up:** confirm the platform `sinas` Python SDK licence from sinas-platform
(not public PyPI) when instance access is available.

## Inferred-field caveats (must confirm with `sinas validate`)
The package-author skill ships verbatim YAML only for functions, agents,
queries, connectors, variables, manifests. For **collections, stores, components**
there is no verbatim package example; we used the camelCase form of the
documented snake_case API properties:
- collections: `metadataSchema` (← `metadata_schema`). Collections have **no
  documented `description` field** — omitted to avoid strict-schema rejection.
- stores: `description`, `visibility`, `encrypted` (per States docs).
- components: `title` (not `description`), `sourceCode` (← `source_code`),
  `visibility`, `enabledFunctions`, `enabledStores`.
If `sinas validate` rejects any of these, adjust in `sinas-package.yaml`.

## Validation results (instance via-10, 2026-06-01)
| Check | Result |
|---|---|
| `sinas validate` | **✓ Valid** — both `sinas-package.yaml` and `sinas-config.yaml`. One fix needed: manifest `requiredResources` only accepts `agent\|collection\|function\|skill` (not `store`/`component`) — those are declared in `spec` and created at install. All other inferred fields (collection `metadataSchema`, store `description`/`visibility`, component `title`/`sourceCode`/`enabledFunctions`/`enabledStores`, variables, dependencies) validated as-is. |
| `sinas preview` | **✓** `+42 created` (9 deps, 11 functions, 5 agents, 3 skills, 6 collections, 6 stores, 1 component, 1 manifest) + 2 roles from config |
| `sinas install` | **✓ Installed** `clip2trace@0.1.0` (pkg id `355d61da-272f-4ee8-891d-13c21e00f1a8`), `errors: []`. Roles applied first, then package. |
| LLM provider | **✓** Claude provider present (`anthropic`, default, active, id `8149b0ff-…`). `default_model` is `null` on the provider; agents pin `claude-sonnet-4-6` explicitly, so this is a minor console follow-up. |
| Management API liveness | **✓** reachable; `/auth/me`, `/packages`, `/dependencies` all 200 |
| Local pytest (core logic) | **62 passed** (`uv run --with pytest pytest`) |
| Package structure (offline) | `tests/test_package_structure.py` — manifest↔spec + agent/component refs resolve |
| Inline-block runnability (offline) | `tests/test_package_inline_sync.py` — every inline `code:` block execs + runs |

### Known live-instance gotchas found during deploy
- **`@sinas/cli` cannot pass install-time `variables`** (no flag; it always sends
  `null`), so `sinas install` 400s on the required `PRIMARY_LLM`. Workaround:
  `scripts/sinas_install.py` calls the same Management API (`POST
  /api/v1/packages/install`) with the `variables` object. Roles still go through
  `sinas install` / config-apply.
- **Scoped API keys hit resource-level 403** ("Not authorized to read/execute
  this resource") on package-installed functions even with `sinas.functions.*:all`
  — the function list returns `[]` and single read/execute are denied for the key
  principal. Execute functions/agents from the **console UI** (full user session)
  or investigate per-resource visibility. Deploy itself is unaffected.
- `sinas status` → 404 on `/api/v1/manifests/clip2trace/clip2trace/status` (the
  manifest exists; the status endpoint path/availability differs on this build).
