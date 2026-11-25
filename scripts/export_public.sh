#!/usr/bin/env bash
# Export a clean tree of BioStack for the public open-source repository.
# Excludes git history, private data, secrets, and internal agent/tooling directories.
# Usage: ./scripts/export_public.sh /path/to/biostack-public
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <destination-dir>" >&2
  exit 1
fi

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DST="$1"

if [ -e "$DST" ] && [ -n "$(ls -A "$DST" 2>/dev/null)" ]; then
  echo "Destination directory exists and is not empty: $DST" >&2
  exit 1
fi

mkdir -p "$DST"

tar -C "$SRC" \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='apps/web/.env*' \
  --exclude='*.db' \
  --exclude='data' \
  --exclude='state' \
  --exclude='demo-state' \
  --exclude='.repowise' \
  --exclude='graphify-out' \
  --exclude='.claude' \
  --exclude='docs/superpowers' \
  --exclude='AGENTS.md' \
  --exclude='GEMINI.md' \
  --exclude='int' \
  --exclude='./package.json' \
  --exclude='./package-lock.json' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.playwright-mcp' \
  --exclude='.superpowers' \
  --exclude='.remember' \
  -cf - . | tar -C "$DST" -xf -

cat <<EOF
Exported clean tree to: $DST

Next steps before pushing publicly:
  1. Scan for secrets:
     gitleaks detect --no-git --source "$DST"
  2. Review docs/ and scripts/ to confirm no personal details remain.
  3. Initialize a fresh git repository:
     cd "$DST" && git init && git add . && git commit -m "feat: initial public release"
EOF
