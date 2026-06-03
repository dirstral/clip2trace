# Research log: permissions diagnosis (corrects PR #45, then itself)

_Date: 2026-06-02, updated 2026-06-03. Instance: via-10. Principal: `<redacted>`
(role `Admins`). Reproducer: `scripts/diagnose_permissions.py`._

## TL;DR (FINAL — 2026-06-03)

**API keys cannot execute or read package resources on via-10, regardless of
their permissions. The blocker is a platform bug, not our configuration.** A
freshly minted API key for the *same* admin user, with explicit
`sinas.functions.execute:all` / `read:all` (the create response echoes them all
as `true`), still gets:

- `POST /functions/clip2trace/<name>/execute` → **403** "Not authorized to
  execute this function"
- `GET /api/v1/functions/clip2trace/<name>` → **403** "Not authorized to read
  this resource"; `GET /api/v1/functions` → **`[]`**
- `GET /api/v1/packages` → **403** "Not authorized to view packages"

…**while** `POST /auth/check-permissions` for the very same keys returns
`has_permission: true`. So the **permission-check layer honors the key's
`permissions`, but the resource-authorization middleware ignores them** — an
API-key principal never clears the per-resource gate. The console works only
because it uses the user's **JWT session**, which resolves authorization through
the `Admins` role.

**Workaround (until the platform is fixed): authenticate with a JWT, not an API
key.** `POST /auth/login` (email+password) → use the returned `access_token` as
the bearer; refresh via `POST /auth/refresh {refresh_token}` (~15-min TTL). The
console/dashboard already do this. **Real fix is operator/platform-side**: make
resource-auth honor API-key permissions (or bind the key to the user's
group/workspace).

> **Two earlier diagnoses were wrong and are kept below only as a trail.** PR #45
> blamed the *key format* (`sinas.functions/<ns>/<name>.execute:own`) — wrong; the
> grammar is `sinas.<resource>.<action>:<scope>`. The first correction (2026-06-02,
> below) blamed *empty/stripped key permission overrides* and prescribed "mint a
> key with explicit perms" — also wrong: a key with explicit `execute:all` still
> 403s (see "Definitive test" next). The permissions were never the gate.

## Definitive test (2026-06-03): explicit `execute:all` key still 403s

Minted a new key for the same admin user **with** explicit permissions
(`POST /api/v1/api-keys`, body `{"name":"clip2trace-exec","permissions":{...all
:all...}}`). The create response (`201`) echoed every permission as `true`:

```jsonc
"permissions": {
  "sinas.functions.execute:all": true, "sinas.functions.read:all": true,
  "sinas.agents.chat:all": true, "sinas.collections.upload:all": true,
  "sinas.stores.write_state:all": true, "sinas.executions.read:all": true, ...
}
```

Then, using that key as the bearer:

```bash
K=<new key>;  U=https://via-10.sinas.wearebrain.com

# 1. The permission CHECK says yes:
curl -s -X POST "$U/auth/check-permissions" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["sinas.functions.execute:all"],"logic":"OR"}'
# → {"result":true,"checks":[{"permission":"sinas.functions.execute:all","has_permission":true}]}
#   (read:all and execute:own also → true)

# 2. …but every actual resource access is denied:
curl -s "$U/api/v1/functions"               -H "Authorization: Bearer $K"   # → []
curl -s "$U/api/v1/functions/clip2trace/create_job" -H "Authorization: Bearer $K"
# → 403 {"detail":"Not authorized to read this resource"}
curl -s "$U/api/v1/packages"                -H "Authorization: Bearer $K"
# → 403 {"detail":"Not authorized to view packages"}
curl -s -X POST "$U/functions/clip2trace/create_job/execute" \
  -H "Authorization: Bearer $K" -H 'Content-Type: application/json' \
  -d '{"input":{"mode":"demo"}}'
# → 403 {"detail":"Not authorized to execute this function"}
```

`/auth/me` on the key confirms it is the **same** principal id `149a05fb-…` with
`roles:["Admins"]`. The component-proxy path
(`POST /components/clip2trace/dashboard/proxy/functions/.../execute`) is denied
the same way. So: **permission-check ✓, resource-auth ✗** — conclusive that the
resource-authorization middleware does not consult the API key's `permissions`.
A JWT for the same user (the console session) is *not* subject to this and works.

## What we measured (via-10, 2026-06-02) — superseded trail

All commands are runnable via `scripts/diagnose_permissions.py`.

### 1. The token, the user, the role

```bash
curl -s -H "Authorization: Bearer $TOK" "$URL/auth/me"
# → {"id":"149a05fb-…","email":"<redacted>",
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

## What this means for #44 (interim — superseded by the 2026-06-03 TL;DR)

> The 2026-06-02 reading below assumed the **old** key's empty/stripped
> permissions were the gate. The 2026-06-03 "Definitive test" disproves that: a
> key with explicit `execute:all` still 403s. Keep this only as context; the real
> cause is the resource-auth middleware ignoring key permissions entirely.

1. **The platform install is fine.** The package installed cleanly, the function
   exists, and the 403 is *descriptive* (it names the function). Nothing is
   broken in the package or the install.
2. ~~**The token is the problem** (empty/stripped overrides).~~ Disproven — see
   "Definitive test": explicit `execute:all` does not help.
3. ~~**The fix is to mint a key with `permissions: {}` or explicit perms.**~~
   Disproven — no key configuration clears the resource gate; use a JWT.
4. **PR #45's source-level claim** about `core/permissions.matches_permission_pattern`
   was correct in spirit (the runtime does pattern-match) but **wrong in the
   specific format** it claimed. The pattern language is `<resource>.<action>:<scope>`,
   not `<resource>/<ns>/<name>.<action>:<scope>`. The author was probably
   looking at a log line that contained the resource id and misread the format.

## Remediation (corrected 2026-06-03)

Minting a key with empty *or* explicit permissions does **not** work — the
resource-auth gate ignores key permissions either way (see "Definitive test").

**Workaround that works today — use a JWT, not an API key.** The console and
dashboard already do this; for scripts/back-ends:

```bash
U=https://via-10.sinas.wearebrain.com
# 1. login -> access_token (+ refresh_token)
curl -s -X POST "$U/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"<you>","password":"<pw>"}'      # -> {access_token, refresh_token, expires_in, ...}
# 2. use the access_token as the bearer for /functions/.../execute, /agents/.../chats, etc.
# 3. it expires in ~15 min — refresh:
curl -s -X POST "$U/auth/refresh" -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'      # -> {access_token, ...}
```

A JWT resolves authorization through the user's `Admins` role and clears the
resource gate that API keys cannot.

**The real fix is operator/platform-side** (Sinas backend), one of:

1. Make the resource-authorization middleware consult the API key's
   `permissions` (today only `/auth/check-permissions` does), **or**
2. Bind an API key to the creating user's group/workspace so resource
   visibility/ownership resolves the same way the JWT's does.

File this with the via-10 / Sinas operator with the "Definitive test" evidence
above. There is no client-side key configuration that unblocks it.

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

**Workaround in `scripts/diagnose_permissions.py`:** the script avoids the
downgrade entirely by stripping the trailing slash on every management-API path
(`base.rstrip("/") + path`, no `-L`-style redirect following), so the bearer
token is never re-sent over HTTP. No special flag is needed; this holds until
the Caddy config is fixed.

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
