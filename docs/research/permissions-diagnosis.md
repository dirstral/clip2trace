# Research log: permissions diagnosis (corrects PR #45)

_Date: 2026-06-02. Instance: via-10. Principal: `ark.deliev@student.uva.nl`
(role `Admins`). Reproducer: `scripts/diagnose_permissions.py`._

## TL;DR

The PR #45 diagnosis of #44 ("API tokens need namespaced permission keys like
`sinas.functions/<ns>/<name>.execute:own`") is **wrong about the key format**.
The authoritative permission key grammar is **`sinas.<resource>.<action>:<scope>`**
(`<resource>` snake_case plural, `<scope>` `:own` or `:all`); namespace is metadata
used to scope `:own` queries, **not a substring of the key**.

The actual root cause on via-10 is that the API token we were using has
**explicit permission overrides** that strip almost every write/admin capability.
The console works because it uses the user's JWT session (which inherits the
`Admins` role), not this restricted token. The fix is operator-side and trivial:
mint a new API key with `permissions: {}` (empty → inherit from user's groups) or
with explicit perms for the resources we need.

## What we measured (via-10, 2026-06-02)

All commands are runnable via `scripts/diagnose_permissions.py`.

### 1. The token, the user, the role

```bash
curl -s -H "Authorization: Bearer $TOK" "$URL/auth/me"
# → {"id":"149a05fb-…","email":"ark.deliev@student.uva.nl",
#    "roles":["Admins"], "last_login_at":"2026-06-02T20:02:50Z",…}
```

User is in `Admins`. But the **token** is restricted.

### 2. `/auth/check-permissions` returns `false` for everything tried

```bash
# Correct form per /api/v1/roles/permissions/reference:
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"permissions":["sinas.functions.execute:all"],"logic":"OR"}' \
  "$URL/auth/check-permissions"
# → {"result":false,"checks":[{"permission":"sinas.functions.execute:all","has_permission":false}]}

# The wildcard (PR #45 said this was the admin form):
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"permissions":["sinas.*:all"],"logic":"OR"}' \
  "$URL/auth/check-permissions"
# → {"result":false,"checks":[{"permission":"sinas.*:all","has_permission":false}]}

# The PR #45 form (does not exist as a key):
curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"permissions":["sinas.functions/clip2trace/diagnose_runtime.execute:own"],"logic":"OR"}' \
  "$URL/auth/check-permissions"
# → {"result":false,"checks":[{"permission":"sinas.functions/clip2trace/diagnose_runtime.execute:own","has_permission":false}]}
```

The token is denied `sinas.functions.execute:all` even though the user is in
`Admins`. The only way the platform would deny that to an admin is if the
**token's per-key overrides** outrank the role.

### 3. The actual function execute

```bash
curl -sS -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"input":{}}' "$URL/functions/clip2trace/diagnose_runtime/execute"
# → {"detail":"Not authorized to execute this function"}   HTTP 403
```

Note the **descriptive 403** — it's "Not authorized to execute **this function**",
not a generic "Not authorized to read". The runtime knows the function exists
and is owned by the install; it just doesn't trust this token to run it.

### 4. The permission reference (authoritative)

```bash
curl -s -H "Authorization: Bearer $TOK" "$URL/api/v1/roles/permissions/reference"
```

Returns the **complete grammar** — every resource, its actions, and whether
it's `namespaced`. Excerpted:

```json
[
  {"resource":"agents",      "actions":["create","read","update","delete","chat"], "namespaced":true},
  {"resource":"functions",   "actions":["create","read","update","delete","execute","shared_pool"], "namespaced":true},
  {"resource":"collections", "actions":["create","read","update","delete","upload","download","list","delete_files"], "namespaced":true},
  {"resource":"stores",      "actions":["create","read","update","delete","write_state","read_state"], "namespaced":true},
  {"resource":"components",  "actions":["create","read","update","delete"], "namespaced":true},
  {"resource":"llm_providers","actions":["create","read","update","delete"], "adminOnly":true},
  {"resource":"api_keys",    "actions":["create","read","delete"]},
  {"resource":"packages",    "actions":["create","install","read","delete"], "adminOnly":true},
  {"resource":"executions",  "actions":["read","update"]},
  …]
```

So the **right key** to execute a function in any namespace is
`sinas.functions.execute:own` (or `:all`). Namespace is a property of the
**resource instance** (used to scope `:own`), not part of the key string.
The `sinas.functions/<ns>/<name>.execute:own` form in PR #45 does not exist.

### 5. What the existing token can and cannot do

| Endpoint | Result | Implied permission |
|---|---|---|
| `GET  /auth/me` | 200 | (none — open to any authenticated principal) |
| `GET  /api/v1/roles` | 200 `[Admins]` | has `sinas.roles.read:all` or `:own` |
| `GET  /api/v1/functions` | 200 `[]` | has `sinas.functions.read:own` but **sees zero functions** (should be 11) |
| `GET  /api/v1/api-keys` | 200 `[]` | has `sinas.api_keys.read:own` but **sees zero keys** |
| `GET  /api/v1/llm-providers` | 403 `sinas.llm_providers.read:all` | **lacks** that perm |
| `GET  /api/v1/packages` | 403 | **lacks** `sinas.packages.read:all` |
| `GET  /api/v1/roles/Admins/permissions` | 403 | **lacks** `sinas.roles.read:all` |
| `POST /api/v1/api-keys` (mint) | 403 | **lacks** `sinas.api_keys.create` |
| `POST /functions/clip2trace/.../execute` | 403 | **lacks** `sinas.functions.execute:all` / `:own` |
| `GET  /api/v1/users/{me}` | 403 | **lacks** `sinas.users.read:all` / `:own` |

The token has been given a handful of `:own` reads and nothing else. The
**Admin** role on the user is therefore not what's being checked — the **token's
per-key permission overrides** are. (Schema confirms: `APIKeyCreate.permissions`
is a `dict[str, bool]` described as **"Permission overrides (empty = inherit
from user's groups)"** — when non-empty, those win over the role.)

## What this means for #44

1. **The platform is fine.** The package installed cleanly, the function exists,
   the runtime knows the installer's `owner_user_id`, and the 403 is
   *descriptive* (it names the function). Nothing is broken in the package or
   the install.
2. **The token is the problem.** It was created with explicit overrides that
   don't include function-execute (or api-key-create, or roles/llm/packages
   read). The user is admin; the token is not.
3. **The fix is one console action.** An admin mints a new API key with
   `permissions: {}` (inherit) — or, for least-privilege, with explicit perms
   matching the dashboard/SDK's needs. That new key will execute package
   functions because it inherits `sinas.functions.execute:own` (the `Admins`
   role grants it; install sets the user as owner).
4. **PR #45's source-level claim** about `core/permissions.matches_permission_pattern`
   was correct in spirit (the runtime does pattern-match) but **wrong in the
   specific format** it claimed. The pattern language is `<resource>.<action>:<scope>`,
   not `<resource>/<ns>/<name>.<action>:<scope>`. The author was probably
   looking at a log line that contained the resource id and misread the format.

## Operator-side remediation (the actual fix)

From the Sinas management console as an admin user:

1. **Settings → API keys → Create API key** (or `POST /api/v1/api-keys`).
2. Name: e.g. `clip2trace-dashboard`.
3. **Permissions: leave empty** (inherits from the user's `Admins` role) —
   this is the simplest correct option.
4. Expiry: pick a date.
5. Save the returned key **once** (the platform shows it only at creation).

Then in the dashboard's env (or `.env`), set:
```bash
SINAS_BASE_URL=https://via-10.sinas.wearebrain.com
SINAS_ADMIN_TOKEN=<the new key>
```

Re-run the pipeline. The 403 is gone.

**Least-privilege alternative** (if you want the dashboard token to NOT
inherit Admin): pass explicit `permissions`:

```json
{
  "name": "clip2trace-dashboard",
  "permissions": {
    "sinas.functions.execute:own":         true,
    "sinas.functions.read:own":            true,
    "sinas.agents.chat:own":               true,
    "sinas.agents.read:own":               true,
    "sinas.collections.upload:own":        true,
    "sinas.collections.read:own":          true,
    "sinas.collections.download:own":      true,
    "sinas.collections.list:own":          true,
    "sinas.collections.delete_files:own":  true,
    "sinas.stores.write_state:own":        true,
    "sinas.stores.read_state:own":         true,
    "sinas.executions.read:own":           true,
    "sinas.query_templates.render:own":    true
  }
}
```

(Mint it from a token that *does* have `sinas.api_keys.create` — an admin
JWT, the console, or a broader "service" token kept in a secret store.)

## Bonus finding: 307 HTTPS→HTTP downgrade on the Management API

`GET /api/v1/<anything>/` (with trailing slash) returns:

```
HTTP/2 307
location: http://via-10.sinas.wearebrain.com/api/v1/<anything>
```

i.e. Caddy/uvicorn is downgrading the management API from HTTPS to HTTP on the
trailing-slash redirect. Two consequences:

- `curl -L` follows it and the bearer token is sent over **HTTP** (and
  re-serialized by curl in cleartext to the new host). Even with `-L`, the
  Authorization header should be re-stripped on cross-host redirects (RFC 7236
  / curl default) — but this is a downgrade on the **same host**, so curl
  keeps the header. That's a real, low-severity credential-exposure path on a
  hostile network.
- The same `GET` without the trailing slash returns the proper JSON 403/200
  (because the no-slash path is handled in FastAPI's router without the
  redirect). All the entries in the table above use the no-slash form.

**Workaround in `scripts/diagnose_permissions.py`:** strip the trailing slash
on the management API base, OR pass `--insecure-http-downgrade` and use a
freshly-minted, scoped token. Recommended: strip the slash until the Caddy
config is fixed.

The Caddy fix is operator-side (`via-10` console → reverse-proxy config; the
runtime and console run on different services, so the fix is one line in the
Caddyfile for the management vhost). Tracked separately — see the follow-up
issue.

## Reproducer

```bash
# Default: reads ~/.sinas/config.json (instance_url + admin_token).
python3 scripts/diagnose_permissions.py

# Or explicit:
python3 scripts/diagnose_permissions.py \
  --url https://via-10.sinas.wearebrain.com \
  --token "$SINAS_ADMIN_TOKEN"

# And try an actual function execute end-to-end (catches more than check-permissions):
python3 scripts/diagnose_permissions.py \
  --url https://via-10.sinas.wearebrain.com \
  --token "$SINAS_ADMIN_TOKEN" \
  --execute clip2trace/diagnose_runtime

# Exit codes:
#   0 = all checks pass (the token is healthy)
#   1 = at least one check failed (the token is restricted or instance is unreachable)
#   2 = usage / config error
```

## What we could **not** verify from this dev box

- Whether the new (inheriting) API key actually returns 200 on
  `/functions/clip2trace/diagnose_runtime/execute`. The path is:
  token has `sinas.functions.execute:own` + function is owned by the install
  user → should work. We can't mint that key because the **existing** token
  also lacks `sinas.api_keys.create`. **The remaining verification is one
  console click away** for whoever has admin console access.
