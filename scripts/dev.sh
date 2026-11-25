#!/usr/bin/env bash
# Start BioStack locally: API on :8000, web on :${WEB_PORT:-3000}, both on 127.0.0.1. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd apps/api && uv run alembic upgrade head && uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
(cd apps/web && npm run dev -- -p "${WEB_PORT:-3000}")
