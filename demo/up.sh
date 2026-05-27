#!/usr/bin/env bash
# Boot the full EnergyOps stack and seed demo data.
# Usage:  ./demo/up.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "[demo/up] copying .env.example -> .env"
  cp .env.example .env
fi

echo "[demo/up] building images and starting services"
docker compose up --build -d

echo "[demo/up] waiting for backend /health"
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "[demo/up] backend up"
    break
  fi
  sleep 2
done

echo "[demo/up] running seed (idempotent)"
docker compose exec -T backend python -m app.seed || true

echo
echo "[demo/up] ready"
echo "  frontend:  http://localhost:3000"
echo "  api docs:  http://localhost:8000/docs"
echo "  health:    http://localhost:8000/health"
