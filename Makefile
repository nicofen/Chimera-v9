# Makefile — Project Chimera developer shortcuts
# ─────────────────────────────────────────────────────────────────────────────
# Usage: make <target>
# Requires: docker, docker compose, python 3.12+

.PHONY: help build up down logs shell test lint backtest monitor health \
        breaker-status breaker-reset breaker-trip clean

COMPOSE = docker compose
SERVICE = chimera

help:   ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*##"}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Docker ────────────────────────────────────────────────────────────────────
build:  ## Build the Docker image
	$(COMPOSE) build

up:     ## Start all services in the background
	$(COMPOSE) up -d
	@echo "  Chimera starting... run 'make logs' to follow"

down:   ## Stop all services
	$(COMPOSE) down

restart: ## Restart the chimera service
	$(COMPOSE) restart $(SERVICE)

logs:   ## Follow chimera logs
	$(COMPOSE) logs -f $(SERVICE)

shell:  ## Open a shell inside the running container
	$(COMPOSE) exec $(SERVICE) /bin/bash

health: ## Check the /api/health endpoint
	@curl -s http://localhost:8765/api/health | python3 -m json.tool

# ── Development (no Docker) ───────────────────────────────────────────────────
dev-install: ## Install dependencies into local venv
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

dev-run: ## Run mainframe locally (reads from .env)
	.venv/bin/python -m chimera.mainframe

# ── Testing ───────────────────────────────────────────────────────────────────
test:   ## Run the full test suite
	.venv/bin/pytest tests/ -v --tb=short

test-fast: ## Run tests excluding slow integration tests
	.venv/bin/pytest tests/ -v --tb=short -m "not slow"

lint:   ## Run ruff linter
	.venv/bin/ruff check chimera/

typecheck: ## Run mypy type checker
	.venv/bin/mypy chimera/ --ignore-missing-imports

# ── Backtest ──────────────────────────────────────────────────────────────────
backtest: ## Run a demo backtest (GME, 2 years, daily bars)
	.venv/bin/python -m chimera.backtest.run_backtest \
	  --sector stocks \
	  --symbols GME AMC \
	  --start 2022-01-01 \
	  --end 2024-01-01 \
	  --equity 100000

# ── Social monitor ────────────────────────────────────────────────────────────
monitor: ## Watch Stocktwits Z-scores for default watchlist
	.venv/bin/python -m chimera.social.monitor \
	  --symbols GME AMC TSLA BBBY NVDA

# ── Circuit breaker ───────────────────────────────────────────────────────────
breaker-status: ## Check current circuit breaker status
	@curl -s http://localhost:8765/api/breaker | python3 -m json.tool

breaker-reset: ## Reset the circuit breaker (provide NOTE="reason")
	@curl -s -X POST "http://localhost:8765/api/breaker/reset?note=$(NOTE)" \
	  | python3 -m json.tool

breaker-trip: ## Manually trip the circuit breaker (emergency flatten)
	@curl -s -X POST "http://localhost:8765/api/breaker/trip?reason=operator" \
	  | python3 -m json.tool

# ── Maintenance ───────────────────────────────────────────────────────────────
db-trades: ## Show last 20 closed trades from SQLite
	sqlite3 data/chimera_trades.db \
	  "SELECT symbol,side,realised_pnl,r_multiple,status,closed_at \
	   FROM orders WHERE status='closed' ORDER BY closed_at DESC LIMIT 20;" \
	  -column -header

db-breaker: ## Show circuit breaker event history
	sqlite3 data/chimera_trades.db \
	  "SELECT ts,reason,detail,equity_at_trip,daily_loss_usd,drawdown_pct \
	   FROM breaker_events ORDER BY ts DESC LIMIT 10;" \
	  -column -header

clean:  ## Remove caches, pyc files, test artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
	@echo "Clean."
