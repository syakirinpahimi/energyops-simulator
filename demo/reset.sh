#!/usr/bin/env bash
# Wipe DB, re-seed, restart simulator. Use between demos.
# Usage:  ./demo/reset.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[demo/reset] resetting database"
docker compose exec -T backend python -m scripts.reset_db --seed

echo "[demo/reset] restarting simulator"
docker compose restart simulator

echo "[demo/reset] done"
