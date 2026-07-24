.PHONY: lint format test test-quick test-e2e test-lite-e2e build-frontend docker-build security ci clean help quickstart quickstart-sqlite backend-run

export PYTHONPATH := services/brain/src:services/backend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# -- Quick start -------------------------------------------------------------

quickstart: docker-base ## Generate .env (if missing) with random secrets and start the core stack
	@if [ ! -f .env ]; then \
		cp env.example .env; \
		python3 infra/scripts/init_env.py; \
	fi
	cd infra && docker compose --env-file ../.env up -d --build

quickstart-sqlite: docker-base ## Start the lightweight SQLite variant (no PostgreSQL required)
	@if [ ! -f .env ]; then \
		cp env.example .env; \
	fi
	cd infra && docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.sqlite-lite.yml up -d --build

backend-run: ## Run Backend locally after applying versioned migrations
	cd services/backend && ../../.venv/bin/python entrypoint.py

# -- Linting -----------------------------------------------------------------

lint: ## Run ruff check + format check
	ruff check .
	ruff format --check .

format: ## Auto-format with ruff
	ruff check --fix .
	ruff format .

# -- Testing ------------------------------------------------------------------

test: ## Run pytest with coverage
	pytest tests/ services/brain/tests/ \
		-v --tb=short \
		-m "not integration and not e2e and not benchmark" \
		--cov --cov-report=term-missing --cov-report=html

test-quick: ## Run pytest without coverage (faster)
	pytest tests/ services/brain/tests/ \
		-v --tb=short \
		-m "not integration and not e2e and not benchmark"

test-e2e: ## Test a running core stack end-to-end
	python3 infra/scripts/integration_test.py

test-lite-e2e: ## Test a running Lite stack end-to-end
	python3 infra/scripts/lite_integration_test.py

# -- Frontend -----------------------------------------------------------------

build-frontend: ## Build frontend (pnpm)
	cd services/frontend && pnpm install --frozen-lockfile && pnpm build

# -- Docker -------------------------------------------------------------------

# BuildKit is required for the Dockerfiles' cache mounts and `# syntax=` directives.
export DOCKER_BUILDKIT := 1

# Python services FROM hems-base:py3.11. Frontend is the only non-Python build.
PYTHON_SERVICES := brain backend voice \
	gas-bridge ha-bridge biometric-bridge obsidian-bridge knowledge-bridge \
	news-bridge weather-bridge switchbot-bridge tapo-bridge
HEAVY_SERVICES := perception stt
NON_PYTHON_SERVICES := frontend

docker-base: ## Build hems-base:py3.11 (shared Python runtime)
	@printf "\n\033[36m=== Building hems-base:py3.11 ===\033[0m\n"
	docker build -t hems-base:py3.11 -f infra/base/Dockerfile .

docker-build: docker-base ## Build all core Docker images (no push)
	@for svc in $(PYTHON_SERVICES) $(NON_PYTHON_SERVICES); do \
		printf "\n\033[36m=== Building %s ===\033[0m\n" "$$svc"; \
		docker build -t hems-$$svc:dev services/$$svc || exit 1; \
	done

docker-build-heavy: docker-base ## Build perception + stt (slow, GPU-aware via GPU_TYPE env)
	@for svc in $(HEAVY_SERVICES); do \
		printf "\n\033[36m=== Building %s (GPU_TYPE=$${GPU_TYPE:-none}) ===\033[0m\n" "$$svc"; \
		docker build --build-arg GPU_TYPE=$${GPU_TYPE:-none} \
			-t hems-$$svc:dev services/$$svc || exit 1; \
	done

docker-build-all: docker-build docker-build-heavy ## Build all images (base + core + heavy)

# -- Security -----------------------------------------------------------------

security: ## Run pip-audit + hadolint
	pip-audit -r services/brain/requirements.txt
	pip-audit -r services/backend/requirements.txt
	@printf "\n\033[36m=== Hadolint ===\033[0m\n"
	@find services -name "Dockerfile" -type f -exec sh -c 'echo "--- {}"; hadolint "{}" || true' \;

# -- Aggregate ----------------------------------------------------------------

ci: lint test build-frontend security ## Run all CI checks locally
	@echo "\n\033[32mAll CI checks passed\033[0m"

# -- Cleanup ------------------------------------------------------------------

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml
	rm -rf services/frontend/dist
