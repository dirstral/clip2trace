#!/usr/bin/env python3
"""Diagnose the #44 API-token permissions issue end-to-end.

Reproduces the investigation in `docs/research/permissions-diagnosis.md`.
Reports the principal, the token's effective permissions for the keys we care
about, and (optionally) whether the token can actually execute a package
function. Designed to be safe to share: no secret writes, no token mutation.

Reads `instance_url` + `admin_token` from `~/.sinas/config.json` (the file
written by `sinas login`), or from `--url` / `--token` flags, or from
`SINAS_BASE_URL` / `SINAS_ADMIN_TOKEN` env vars.

Usage:
    python3 scripts/diagnose_permissions.py
    python3 scripts/diagnose_permissions.py --url https://via-10.sinas.wearebrain.com \\
        --token "$SINAS_ADMIN_TOKEN"
    python3 scripts/diagnose_permissions.py --execute clip2trace/diagnose_runtime

Exit codes:
    0  all checks pass (token is healthy — can execute package functions)
    1  at least one check failed (token is restricted or instance unreachable)
    2  usage / config error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _load_config() -> tuple[str, str]:
    """Return (instance_url, token) from ~/.sinas/config.json (CLI's file)."""
    cfg_path = os.path.expanduser("~/.sinas/config.json")
    if not os.path.exists(cfg_path):
        raise SystemExit("no ~/.sinas/config.json — run `sinas login` first")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    base = (cfg.get("instance_url") or "").rstrip("/")
    tok = cfg.get("admin_token") or cfg.get("token") or ""
    if not base or not tok:
        raise SystemExit("missing instance_url/token in ~/.sinas/config.json")
    return base, tok


def _http(
    base: str,
    path: str,
    tok: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    """Issue a request. Returns (status, parsed_json_or_text).

    Strips the trailing slash on the management API to avoid the Caddy 307
    HTTPS→HTTP downgrade (see docs/research/permissions-diagnosis.md).
    """
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + tok,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _safe_json(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _safe_json(exc.read())
    except urllib.error.URLError as exc:
        # Connection/DNS/timeout failures: report as a non-200 so the check fails
        # gracefully (instance unreachable -> exit 1) instead of crashing.
        return 0, f"unreachable: {exc.reason}"


def _safe_json(raw: bytes) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", help="Sinas base URL (default: ~/.sinas/config.json)")
    ap.add_argument("--token", help="admin/API token (default: ~/.sinas/config.json)")
    ap.add_argument(
        "--execute",
        metavar="NS/NAME",
        help="also try POST /functions/<ns>/<name>/execute with {} and report the status",
    )
    args = ap.parse_args()

    base = args.url or os.environ.get("SINAS_BASE_URL", "")
    tok = args.token or os.environ.get("SINAS_ADMIN_TOKEN", "")
    # Fall back to the CLI's config only for whatever wasn't given explicitly, so
    # an explicit --url (or --token) always wins over ~/.sinas/config.json.
    if not base or not tok:
        try:
            cfg_base, cfg_tok = _load_config()
        except SystemExit as exc:
            print(str(exc), file=sys.stderr)
            return 2
        base = base or cfg_base
        tok = tok or cfg_tok
    if not base or not tok:
        print(
            "error: --url and --token required (or ~/.sinas/config.json)",
            file=sys.stderr,
        )
        return 2

    print(f"Sinas base: {base}")
    all_ok = True

    # 1. /auth/me — who is this token?
    code, me = _http(base, "/auth/me", tok)
    ok = code == 200 and isinstance(me, dict)
    detail = (
        f"id={me.get('id')} email={me.get('email')} roles={me.get('roles')}"
        if ok
        else f"http={code} body={me}"
    )
    all_ok &= _check("auth/me", ok, detail)

    # 2. /auth/check-permissions — the keys the runtime actually checks.
    # Per /api/v1/roles/permissions/reference the correct grammar is
    # sinas.<resource_snake>.<action>:<scope>. Namespace is metadata, not in key.
    # We test both :all and :own for each, and the wildcard.
    perms_to_check = [
        # Read paths
        ("sinas.functions.execute:all", "execute package functions (all)"),
        ("sinas.functions.execute:own", "execute package functions (own)"),
        ("sinas.functions.read:all", "list/read functions (all)"),
        ("sinas.functions.read:own", "list/read functions (own)"),
        ("sinas.agents.chat:own", "chat agents (own)"),
        ("sinas.collections.upload:own", "upload files to collections (own)"),
        ("sinas.stores.write_state:own", "write store state (own)"),
        # Admin-side
        ("sinas.api_keys.create", "create API keys"),
        ("sinas.llm_providers.read:all", "read LLM providers"),
        ("sinas.packages.read:all", "read packages"),
        # The "everything" wildcard (predicted to be false even for an admin
        # token if the token has explicit overrides)
        ("sinas.*:all", "wildcard (all)"),
    ]
    # Only the execute-related keys gate the overall result — #44 is about whether
    # the token can execute package functions. The other keys are printed for
    # context (e.g. an admin-only key like llm_providers.read may legitimately be
    # absent without meaning the token is "restricted" for our purposes).
    gating_perms = {"sinas.functions.execute:all", "sinas.functions.execute:own"}
    print("\nPermission checks (POST /auth/check-permissions):")
    perm_results: dict[str, bool] = {}
    for perm, label in perms_to_check:
        code, body = _http(
            base,
            "/auth/check-permissions",
            tok,
            method="POST",
            body={"permissions": [perm], "logic": "OR"},
        )
        if code != 200 or not isinstance(body, dict):
            ok = False
            detail = f"http={code} body={body}"
        else:
            checks = body.get("checks") or []
            granted = bool(checks[0].get("has_permission")) if checks else False
            ok = granted
            suffix = "" if perm in gating_perms else "  [informational]"
            detail = f"{perm}  ({label}){suffix}"
        perm_results[perm] = ok
        _check(perm, ok, detail)

    # The real gate: can this token execute functions at all (either scope)?
    can_execute = any(perm_results.get(p) for p in gating_perms)
    all_ok &= _check(
        "can execute package functions (execute:all OR execute:own)", can_execute
    )

    # 3. Optional: actual function execute (the real test).
    if args.execute:
        ns, _, name = args.execute.partition("/")
        if not (ns and name):
            print(
                f"\nerror: --execute expects NS/NAME, got {args.execute!r}",
                file=sys.stderr,
            )
            return 2
        path = f"/functions/{ns}/{name}/execute"
        print(f"\nLive execute: POST {path} {{}}")
        code, body = _http(
            base, path, tok, method="POST", body={"input": {}}, timeout=60.0
        )
        ok = code == 200
        detail = f"http={code}"
        if isinstance(body, dict) and "detail" in body:
            detail += f"  detail={body['detail']!r}"
        elif isinstance(body, dict):
            keys = sorted(body.keys())[:6]
            detail += f"  keys={keys}"
        all_ok &= _check("execute", ok, detail)

    print()
    if all_ok:
        print("RESULT: token looks healthy — package functions should execute.")
        return 0
    print(
        "RESULT: token is restricted (see FAILs above). "
        "Mint a new key with permissions: {} (inherit) or explicit perms "
        "per docs/research/permissions-diagnosis.md."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
