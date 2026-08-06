# Invoice Automation prototype — developer task shortcuts.
# Run `make` or `make help` to list targets.
#
# Services run as native processes in separate terminals (backend, frontend),
# plus an optional Mailpit container for the email step.

.DEFAULT_GOAL := help
.PHONY: help setup backend frontend mailpit mailpit-down test test-all check build stop

MAILPIT_COMPOSE := docker-compose.mailpit.yml

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Bootstrap local dev (venv, deps, .env scaffolding)
	@./scripts/setup.sh

backend: ## Run the FastAPI backend on :8001 (terminal 1)
	@./backend/run.sh

frontend: ## Run the Vite dev server on :5173 (terminal 2)
	@cd frontend && npm run dev

mailpit: ## Start Mailpit (SMTP :1025, UI http://localhost:8025)
	@docker compose -f $(MAILPIT_COMPOSE) up -d

mailpit-down: ## Stop and remove Mailpit
	@docker compose -f $(MAILPIT_COMPOSE) down

test: ## Backend tests (synthetic only — what CI runs)
	@./backend/test.sh --no-real

test-all: ## Backend tests including realdata/integration (needs samples/ + Mailpit)
	@./backend/test.sh

check: ## Frontend typecheck (vue-tsc)
	@cd frontend && npm run check

build: ## Frontend production build
	@cd frontend && npm run build

stop: ## Stop backend + frontend dev processes (best-effort)
	@pkill -f vite || true
	@pkill -f uvicorn || true
	@echo "Stopped vite/uvicorn (Mailpit: make mailpit-down)"
