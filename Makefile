.PHONY: help dev up down build rebuild logs status test lint clean backup migrate release

# ─────────────────────────────────────────────
# Variables
# ─────────────────────────────────────────────
VERSION := $(shell cat VERSION)
COMPOSE := docker compose
SERVICES := ghostwire-proxy-api ghostwire-proxy-ui ghostwire-proxy-nginx

# ─────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ─────────────────────────────────────────────
# Development
# ─────────────────────────────────────────────
dev: ## Start all services (foreground logs)
	$(COMPOSE) up

up: ## Start all services (detached)
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

restart: ## Restart application containers (not databases)
	$(COMPOSE) restart $(SERVICES)

status: ## Show container status
	$(COMPOSE) ps

logs: ## Tail all logs
	$(COMPOSE) logs -f --tail=50

logs-api: ## Tail API logs
	$(COMPOSE) logs -f --tail=100 ghostwire-proxy-api

logs-ui: ## Tail UI logs
	$(COMPOSE) logs -f --tail=100 ghostwire-proxy-ui

logs-nginx: ## Tail Nginx logs
	$(COMPOSE) logs -f --tail=100 ghostwire-proxy-nginx

# ─────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────
build: ## Build all images
	$(COMPOSE) build

rebuild: ## Force rebuild all images (no cache)
	$(COMPOSE) build --no-cache

build-api: ## Build API image only
	$(COMPOSE) build ghostwire-proxy-api

build-ui: ## Build UI image only
	$(COMPOSE) build ghostwire-proxy-ui

build-nginx: ## Build Nginx image only
	$(COMPOSE) build ghostwire-proxy-nginx

deploy: ## Build and restart application containers
	$(COMPOSE) up -d --build $(SERVICES)

# ─────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────
test: ## Run backend tests
	docker exec ghostwire-proxy-api pytest tests/ -v --tb=short

test-local: ## Run backend tests locally (requires venv)
	cd backend && python -m pytest tests/ -v --tb=short

lint: ## Run frontend linting
	cd frontend && npm run lint

typecheck: ## Run TypeScript type checking
	cd frontend && npx tsc --noEmit

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────
migrate: ## Run database migrations
	docker exec ghostwire-proxy-api alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create MSG="add users table")
	docker exec ghostwire-proxy-api alembic revision --autogenerate -m "$(MSG)"

migrate-history: ## Show migration history
	docker exec ghostwire-proxy-api alembic history

# ─────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────
backup: ## Create a backup via API
	@echo "Creating backup..."
	@curl -s -X POST http://localhost:8089/api/backups/ \
		-H "Content-Type: application/json" \
		-H "X-Internal-Auth: $${INTERNAL_AUTH_TOKEN}" \
		-d '{"include_database":true,"include_certificates":true,"include_configs":true}' | \
		python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Backup created: {d.get(\"id\", \"unknown\")}')"

# ─────────────────────────────────────────────
# Release (run locally to cut a release)
# ─────────────────────────────────────────────
release: ## Create a new release tag (usage: make release V=1.2.0)
ifndef V
	$(error Usage: make release V=1.2.0)
endif
	@echo "Releasing v$(V)..."
	@echo "$(V)" > VERSION
	@cd frontend && npm version $(V) --no-git-tag-version --allow-same-version
	@git add VERSION frontend/package.json frontend/package-lock.json
	@git commit -m "release: v$(V)"
	@git tag -a "v$(V)" -m "Release v$(V)"
	@echo ""
	@echo "Release v$(V) created locally."
	@echo "Push with:  git push origin main --tags"

version: ## Show current version
	@echo "$(VERSION)"

# ─────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────
clean: ## Remove dangling Docker images
	docker image prune -f

clean-all: ## Remove all project images and volumes (DESTRUCTIVE)
	@echo "This will remove all project containers, images, and volumes!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && \
		$(COMPOSE) down -v --rmi local || echo "Cancelled."
