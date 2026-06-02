#!/usr/bin/env python3
"""Thin wrapper around scripts/create_issues.sh (the canonical issue source).

Requires the GitHub CLI (`gh`) authenticated with `repo` scope. The bash script
holds all titles/bodies/labels/milestones so there is a single source of truth.

Usage:
    python scripts/create_issues.py            # auto-detect repo
    REPO=owner/name python scripts/create_issues.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SH = os.path.join(HERE, "create_issues.sh")


def main() -> int:
    if shutil.which("gh") is None:
        print(
            "ERROR: GitHub CLI 'gh' not found. Install it and run "
            "`gh auth login` (repo scope).",
            file=sys.stderr,
        )
        return 2
    if not os.path.exists(SH):
        print(f"ERROR: {SH} missing.", file=sys.stderr)
        return 3
    return subprocess.call(["bash", SH], env=os.environ.copy())


if __name__ == "__main__":
    raise SystemExit(main())
