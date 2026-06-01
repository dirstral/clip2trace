#!/usr/bin/env bash
# Install the official Sinas coding skills into .claude/skills/ so Claude Code
# auto-discovers them during this project's sessions.
#
# The skills (https://github.com/sinas-platform/skills) are AGPL-3.0; clip2trace
# is also AGPL-3.0-or-later, so this is license-compatible. We still keep
# .claude/skills/ gitignored so the skills stay fresh from upstream instead of
# vendoring stale copies. Each developer runs this once. Re-runnable.
#
#   bash scripts/setup_sinas_skills.sh

set -euo pipefail
REPO_URL="https://github.com/sinas-platform/skills"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.claude/skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Cloning $REPO_URL (shallow)..."
git clone --depth 1 "$REPO_URL" "$TMP/skills" >/dev/null 2>&1

mkdir -p "$DEST"
for s in sinas-package-author sinas-app; do
  if [ -d "$TMP/skills/skills/$s" ]; then
    rm -rf "$DEST/$s"
    cp -R "$TMP/skills/skills/$s" "$DEST/$s"
    echo "installed: .claude/skills/$s"
  else
    echo "WARN: skills/$s not found in upstream repo" >&2
  fi
done

echo
echo "Done. These AGPL-3.0 skills are local-only (gitignored) — never commit them."
echo "Use 'sinas-package-author' when editing sinas-package.yaml, and 'sinas-app'"
echo "when building the dashboard/React app. They are the source of truth for"
echo "Sinas YAML/SDK fields and override clip2trace's inferred field names."
