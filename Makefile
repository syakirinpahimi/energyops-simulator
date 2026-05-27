# EnergyOps - convenience wrappers around docker compose.
# All real work lives in docker-compose.yml and the per-service code.
# Run `make help` for the list (default target).

COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help demo up down nuke build logs ps seed reset-db backend-test frontend-test sim-smoke typecheck config check

help:
	@echo "EnergyOps Makefile targets:"
	@echo ""
	@echo "  Quick demo:"
	@echo "    make demo            one-shot: build, start, wait, seed (best for recruiters)"
	@echo ""
	@echo "  Stack lifecycle:"
	@echo "    make up              build images and start the stack (-d)"
	@echo "    make down            stop containers, keep volumes"
	@echo "    make nuke            stop containers and drop volumes"
	@echo "    make build           rebuild images without starting"
	@echo "    make logs            tail logs for all services"
	@echo "    make ps              docker compose ps"
	@echo ""
	@echo "  Database:"
	@echo "    make seed            run app.seed inside the backend container"
	@echo "    make reset-db        wipe + re-seed the database"
	@echo ""
	@echo "  Tests / typecheck:"
	@echo "    make backend-test    run pytest inside the backend container"
	@echo "    make frontend-test   run vitest inside the frontend container"
	@echo "    make sim-smoke       run the simulator --smoke burst"
	@echo "    make typecheck       run tsc --noEmit inside the frontend container"
	@echo "    make check           typecheck + backend-test + frontend-test"
	@echo ""
	@echo "  Diagnostics:"
	@echo "    make config          docker compose config (validate)"

demo:
	@if [ ! -f .env ]; then echo "[demo] copying .env.example -> .env"; cp .env.example .env; fi
	$(COMPOSE) up --build -d
	@echo "[demo] waiting for backend /health (up to ~120s)"
	@for i in $$(seq 1 60); do \
		if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then echo "[demo] backend up"; break; fi; \
		sleep 2; \
	done
	$(COMPOSE) exec -T backend python -m app.seed || true
	@echo
	@echo "[demo] ready"
	@echo "  frontend:  http://localhost:3000"
	@echo "  api docs:  http://localhost:8000/docs"
	@echo "  health:    http://localhost:8000/health"

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

nuke:
	$(COMPOSE) down -v

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

seed:
	$(COMPOSE) exec -T backend python -m app.seed

reset-db:
	$(COMPOSE) exec -T backend python -m scripts.reset_db --seed

backend-test:
	$(COMPOSE) exec -T backend pytest

frontend-test:
	$(COMPOSE) exec -T frontend npm test

sim-smoke:
	$(COMPOSE) run --rm simulator python -m simulator.main --smoke --ticks 20 --seed 42

typecheck:
	$(COMPOSE) exec -T frontend npm run typecheck

check: typecheck backend-test frontend-test

config:
	$(COMPOSE) config --quiet
