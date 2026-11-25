#!/usr/bin/env bash
# On the server, inside the repository: update the code, back up, rebuild, check health, roll back if it fails.
#   bash scripts/server_deploy.sh [branch]
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env is missing. Copy .env.example to .env and fill it in." >&2; exit 1; }
web_port="$(sed -n 's/^WEB_PORT=//p' .env | tail -1)"
export BIOSTACK_UID="$(id -u)" BIOSTACK_GID="$(id -g)"
mkdir -p state

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
previous="$(git rev-parse HEAD)"
retry() {  # a home connection drops now and then; try a few times before giving up
  for attempt in 1 2 3 4 5 6; do "$@" && return 0; echo "Attempt $attempt failed: $*" >&2; sleep 10; done
  return 1
}
retry git fetch --quiet origin
git checkout --quiet "$branch"
git merge --quiet --ff-only "origin/$branch"
current="$(git rev-parse HEAD)"
echo "Code: ${previous:0:7} -> ${current:0:7} on $branch"

if docker compose ps --status running --services 2>/dev/null | grep -qx api; then
  echo "Backing up before the update..."
  docker compose exec -T api python -m scripts.backup --keep 30
fi

healthy() {
  local api_id
  api_id="$(docker compose ps -q api)"
  [ -n "$api_id" ] && [ "$(docker inspect -f '{{.State.Health.Status}}' "$api_id" 2>/dev/null)" = healthy ] \
    && curl -fsS -o /dev/null "http://127.0.0.1:${web_port:-3410}/"
}

wait_until_healthy() {
  for _ in $(seq 1 40); do healthy && return 0; sleep 3; done
  return 1
}

docker compose up -d --build --remove-orphans
if wait_until_healthy; then
  echo "BioStack is up on ${current:0:7}."
  docker image prune -f >/dev/null
  exit 0
fi

echo "The new version did not become healthy. Logs:" >&2
docker compose logs --tail 40 api web >&2 || true
echo "Rolling back to ${previous:0:7}..." >&2
git reset --hard --quiet "$previous"
docker compose up -d --build --remove-orphans
if wait_until_healthy; then
  echo "Rolled back: the previous version is running. Newest backup: $(ls -1t state/backups/*.tar.gz | head -1)" >&2
else
  echo "The previous version is not healthy either. Check: docker compose logs. Restore with scripts/restore.sh." >&2
fi
exit 1
