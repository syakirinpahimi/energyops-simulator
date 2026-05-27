# EnergyOps - convenience wrappers around docker compose.
# All real work lives in docker-compose.yml and the per-service code.
# Run `make help` for the list.

COMPOSE ?= docker compose

.PHONY: help up down nuke build logs ps seed reset-db backend-test frontend-test sim-smoke typecheck config

help:
	@echo "EnergyOps Makefile targets:"
	@echo ""
	@echo "  make up              build images and start the stack (-d)"
	@echo "  make down            stop containers, keep volumes"
	@echo "  make nuke            stop containers and drop volumes"
	@echo "  make build           rebuild images without starting"
	@echo "  make logs            tail logs for all services"
	@echo "  make ps              docker compose ps"
	@echo ""
	@echo "  make seed            run app.seed inside the backend container"
	@echo "  make reset-db        wipe + re-seed the database"
	@echo ""
	@echo "  make backend-test    run pytest inside the backend container"
	@echo "  make frontend-test   run vitest inside the frontend container"
	@echo "  make sim-smoke       run the simulator --smoke burst"
	@echo "  make typecheck       run tsc --noEmit inside the frontend container"
	@echo ""
	@echo "  make config          docker compose config (validate)"

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

config:
	$(COMPOSE) config --quiet
