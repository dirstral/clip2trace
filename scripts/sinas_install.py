#!/usr/bin/env python3
"""Preview / install the clip2trace Sinas package WITH install-time variables.

Why this exists: `@sinas/cli`'s `sinas install` has no flag to pass package
`variables`, so a required `resource_ref` like `PRIMARY_LLM` makes it fail with
`400: Required variable 'PRIMARY_LLM' not provided`. This script calls the same
Management API the CLI uses (`POST /api/v1/packages/{preview,install}`) but
includes the `variables` object. Roles in `sinas-config.yaml` are applied
separately by `sinas install` / `sinas` config apply (already done).

Reads `instance_url` + token from `~/.sinas/config.json` (written by `sinas login`).

Usage:
    python3 scripts/sinas_install.py --preview            # dry-run, no changes
    python3 scripts/sinas_install.py                      # INSTALL (modifies the instance)
    PRIMARY_LLM="Claude" python3 scripts/sinas_install.py # override the provider ref
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="dry-run via /packages/preview (no changes)")
    ap.add_argument("--primary-llm", default=os.environ.get("PRIMARY_LLM", "Claude"),
                    help="value for the PRIMARY_LLM resource_ref (LLM provider name)")
    ap.add_argument("--package", default=os.path.join(ROOT, "sinas-package.yaml"))
    args = ap.parse_args()

    cfg_path = os.path.expanduser("~/.sinas/config.json")
    if not os.path.exists(cfg_path):
        sys.exit("no ~/.sinas/config.json — run `sinas login` first")
    cfg = json.load(open(cfg_path))
    base = (cfg.get("instance_url") or "").rstrip("/")
    tok = cfg.get("admin_token") or cfg.get("token")
    if not base or not tok:
        sys.exit("missing instance_url/token in ~/.sinas/config.json")

    source = open(args.package, encoding="utf-8").read()
    variables = {
        "PRIMARY_LLM": args.primary_llm,
        "ENABLE_TELEGRAM_LIVE_SEARCH": False,
        "MAX_VIDEO_MB": "500",
    }
    endpoint = "/api/v1/packages/preview" if args.preview else "/api/v1/packages/install"
    payload = json.dumps({"source": source, "variables": variables}).encode()

    print(f"POST {base}{endpoint}")
    print(f"  PRIMARY_LLM={args.primary_llm!r}  mode={'PREVIEW' if args.preview else 'INSTALL'}")
    req = urllib.request.Request(
        base + endpoint, data=payload, method="POST",
        headers={"Authorization": "Bearer " + tok,
                 "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        print("HTTP", resp.status)
        print(json.dumps(json.loads(resp.read()), indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code)
        print(exc.read().decode())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
