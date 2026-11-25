#!/usr/bin/env bash
# On the server: put a backup archive back. Stops the app, replaces the database and data directory, starts it again.
#   bash scripts/restore.sh state/backups/biostack-20261112-030005.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
archive="${1:?Usage: scripts/restore.sh <backup archive>}"
[ -f "$archive" ] || { echo "No such archive: $archive" >&2; exit 1; }
export BIOSTACK_UID="$(id -u)" BIOSTACK_GID="$(id -g)"
docker compose stop web bot api
stamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p "state/before-restore-$stamp"
mv state/biostack.db state/data "state/before-restore-$stamp/" 2>/dev/null || true
tar -xzf "$archive" -C state
docker compose up -d
echo "Restored from $archive. The replaced files are in state/before-restore-$stamp."
