#!/usr/bin/env bash
# From your laptop: push the current branch, then update BioStack on the server.
#   ./scripts/deploy.sh
# BIOSTACK_SERVER (required SSH host alias) and BIOSTACK_SERVER_DIR (default "biostack") target the server.
set -euo pipefail
cd "$(dirname "$0")/.."
host="${BIOSTACK_SERVER:?Set BIOSTACK_SERVER to your SSH host alias}"
dir="${BIOSTACK_SERVER_DIR:-biostack}"
branch="$(git rev-parse --abbrev-ref HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  echo "Uncommitted changes: commit or stash them first, so the server gets what you see." >&2
  exit 1
fi
git push origin "$branch"
ssh "$host" "cd '$dir' && bash scripts/server_deploy.sh '$branch'"
