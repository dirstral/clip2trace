# Bug report (for the Sinas / via-10 operator): API-key permission matching is inconsistent

_Prepared 2026-06-03 from the clip2trace investigation. Full trail:
[`permissions-diagnosis.md`](permissions-diagnosis.md); reproducer:
[`scripts/diagnose_permissions.py`](../../scripts/diagnose_permissions.py)._

## Summary

On **via-10**, `/auth/check-permissions` and the **resource-authorization
middleware** disagree about API-key permissions:

- `/auth/check-permissions` matches **explicit action** keys (e.g.
  `sinas.functions.execute:all`) → returns `has_permission: true`.
- The actual resource endpoints (`/functions/.../execute`, `/api/v1/functions`,
  …) only honor **wildcard** keys (`sinas.<resource>.*:<scope>` or
  `sinas.*:<scope>`). An explicit-action key is **silently ineffective** there →
  `403`.

So a key minted with `sinas.functions.execute:all` *looks* authorized (the check
endpoint and the SDK both say yes) but **403s** on the real call. There is a
client-side workaround (use wildcard permissions), so this is a **correctness /
least-privilege** bug rather than a hard blocker.

- **Instance:** via-10 (`https://via-10.sinas.wearebrain.com`)
- **Severity:** Medium — keys *can* be made to work (wildcards), but explicit
  least-privilege permissions silently fail, and the check endpoint misreports
  them as granted.
- **Principal:** an `Admins`-role user (id `149a05fb-…`).

## Reproduction

Same admin user, several freshly minted keys (`POST /api/v1/api-keys`), each
tested with `POST /functions/clip2trace/create_job/execute`:

| Key `permissions` | `check-permissions` `functions.execute:all` | execute |
|---|---|---|
| `{ "sinas.*:all": true }` | true | **200** |
| `{ "sinas.functions.*:all": true, …resource wildcards… }` | true | **200** |
| `{ "sinas.*:own": true }` | (n/a) | **200** |
| `{ "sinas.functions.execute:all": true, "sinas.functions.read:all": true, … }` | **true** | **403** |

```bash
U=https://via-10.sinas.wearebrain.com

# A) explicit-action key — check says yes, execute says no:
K=<explicit-action key>
curl -s -X POST "$U/auth/check-permissions" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' \
  -d '{"permissions":["sinas.functions.execute:all"],"logic":"OR"}'
# -> {"result":true, ... has_permission:true ...}
curl -s -X POST "$U/functions/clip2trace/create_job/execute" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' -d '{"input":{"mode":"demo"}}'
# -> 403 {"detail":"Not authorized to execute this function"}
#    GET /api/v1/functions -> []   (also hidden)

# B) wildcard key — both agree, works:
K=<wildcard key, e.g. permissions {"sinas.functions.*:all":true,...}>
curl -s -X POST "$U/functions/clip2trace/create_job/execute" -H "Authorization: Bearer $K" \
  -H 'Content-Type: application/json' -d '{"input":{"mode":"demo"}}'
# -> 200 {"status":"success","result":{...}}
```

Both keys resolve to the same principal (`GET /auth/me` →
`{"id":"149a05fb-…","roles":["Admins"]}`); the only difference is wildcard vs
explicit-action permissions.

## Likely root cause

The resource-authorization path appears to do **wildcard pattern matching only**
(it matches `sinas.functions.*` / `sinas.*` against the required permission),
whereas `/auth/check-permissions` also accepts an **exact** action key. So
explicit `sinas.functions.execute:all` satisfies the check but not the resource
gate. (`GET /api/v1/functions` returning `[]` for the explicit-action key is the
same gate applied to listing.)

## Suggested fix

Make the two paths consistent — the resource-authorization middleware should
honor an **exact** action permission (`sinas.functions.execute:all`) the same way
`/auth/check-permissions` does, so least-privilege keys work and the check
endpoint doesn't misreport. (Equivalently: have `/auth/check-permissions` reflect
the stricter wildcard-only matching so it stops returning `true` for keys that
will 403 — but honoring exact actions is the more useful fix.)

## Workaround (clip2trace is using this)

Grant the key **wildcard-action** permissions. Least-privilege set that works:

```json
{
  "sinas.functions.*:all": true, "sinas.agents.*:all": true,
  "sinas.collections.*:all": true, "sinas.stores.*:all": true,
  "sinas.executions.*:all": true, "sinas.components.*:all": true
}
```

(`sinas.*:all` also works but is full admin — avoid for a service key.)
