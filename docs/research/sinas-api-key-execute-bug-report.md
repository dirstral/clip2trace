# Bug report (for the Sinas / via-10 operator): API keys cannot execute or read resources

_Prepared 2026-06-03 from the clip2trace investigation. Full trail:
[`permissions-diagnosis.md`](permissions-diagnosis.md); reproducer:
[`scripts/diagnose_permissions.py`](../../scripts/diagnose_permissions.py)._

## Summary

On **via-10**, an **API key cannot execute or read package resources, regardless
of its permissions**, while the **same user's JWT session can**. The
authorization **check** endpoint (`/auth/check-permissions`) honors a key's
permissions, but the **resource-authorization middleware** on the actual
endpoints ignores them — so an API-key principal never clears the per-resource
gate. This blocks all programmatic (non-console) use of installed functions and
agents.

- **Instance:** via-10 (`https://via-10.sinas.wearebrain.com`)
- **Severity:** High — no API-key-based automation can run installed functions
  or agents; only interactive console (JWT) sessions work.
- **Affected:** `POST /functions/{ns}/{name}/execute`, the component-proxy
  execute path, and `GET /api/v1/functions|packages|functions/{ns}/{name}`.
- **Principal:** an `Admins`-role user (id `149a05fb-…`).

## Expected vs actual

**Expected:** an API key whose `permissions` grant `sinas.functions.execute:all`
(and which `/auth/check-permissions` confirms) can call
`POST /functions/{ns}/{name}/execute`, the same as the user's JWT.

**Actual:** that call returns `403 "Not authorized to execute this function"`,
and the function list/read endpoints return `[]` / `403`, even though
`/auth/check-permissions` reports the permission as granted.

## Reproduction

Two API keys for the **same** `Admins` user, created two different ways. Both
fail; together they isolate the bug. (Key values redacted; mint your own.)

### Key A — minted via the API with explicit permissions

`POST /api/v1/api-keys` with
`{"name":"...","permissions":{"sinas.functions.execute:all":true,
"sinas.functions.read:all":true, ...}}` → `201`, response echoes every
permission as `true`.

```bash
K=<key A>;  U=https://via-10.sinas.wearebrain.com

# permission CHECK says YES:
curl -s -X POST "$U/auth/check-permissions" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["sinas.functions.execute:all"],"logic":"OR"}'
# -> {"result":true,"checks":[{"permission":"sinas.functions.execute:all","has_permission":true}]}

# but the resource endpoints say NO:
curl -s "$U/api/v1/functions"                       -H "Authorization: Bearer $K"   # -> []
curl -s "$U/api/v1/functions/clip2trace/create_job" -H "Authorization: Bearer $K"
# -> 403 {"detail":"Not authorized to read this resource"}
curl -s -X POST "$U/functions/clip2trace/create_job/execute" \
  -H "Authorization: Bearer $K" -H 'Content-Type: application/json' \
  -d '{"input":{"mode":"demo"}}'
# -> 403 {"detail":"Not authorized to execute this function"}
```

### Key B — created in the console "Create API key" form with "all" selected

```bash
K=<key B>
curl -s -X POST "$U/auth/check-permissions" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["sinas.functions.execute:all","sinas.functions.read:all"],"logic":"AND"}'
# -> {"result":false, ... has_permission:false ...}   <-- console UI did not grant these keys
curl -s -X POST "$U/functions/clip2trace/create_job/execute" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' -d '{"input":{"mode":"demo"}}'
# -> 403 {"detail":"Not authorized to execute this function"}
```

Both keys resolve to the same principal:
`GET /auth/me` → `{"id":"149a05fb-…","roles":["Admins"]}`.

## What this isolates

| | `check-permissions` `execute:all` | actual execute |
|---|---|---|
| Key A (API-minted, explicit perms) | **true** | **403** |
| Key B (console "select all") | **false** | **403** |
| Same user's **JWT** (console session) | n/a | **works** |

- Key A proves the **resource-authorization middleware ignores key permissions**:
  the key *has* `execute:all` (check ✓) and is still denied.
- Key B proves a **secondary console-UI issue**: selecting "all" in the Create
  API key form does **not** write the permission keys the runtime evaluates
  (`check-permissions` → false).

## Likely root cause

The resource-authorization path appears to resolve a principal's permissions
from **role/group membership**, not from an **API key's `permissions` overrides**.
API keys are not bound to the creating user's group/workspace, so resource
visibility/ownership resolves to nothing — hence `GET /functions` → `[]` and
execute → 403 — even though `/auth/check-permissions` (which *does* read the
key's overrides) returns true. The `APIKeyCreate.permissions` schema describes
empty as *"inherit from user's groups"*, but the admin capability here comes from
a **role**, and group inheritance yields nothing.

## Suggested fix (one of)

1. Make the resource-authorization middleware consult the API key's `permissions`
   (the same source `/auth/check-permissions` already uses), so an explicit
   `sinas.functions.execute:all` key can execute; **and/or**
2. Bind an API key to the creating user's role/group/workspace so resource
   visibility resolves the same way the JWT's does.
3. Separately, fix the console **Create API key** form so a "select all"
   selection actually persists `sinas.<resource>.<action>:all` permissions
   (today they don't register in `check-permissions`).

## Workaround (clip2trace is using this)

Authenticate with a **JWT**, not an API key: `POST /auth/login`
(email+password) → use the returned `access_token` as the bearer; refresh via
`POST /auth/refresh {refresh_token}` (~15-min access-token TTL). The console and
dashboard already do this, which is why they work.
