.PHONY: lint format test test-quick build-frontend docker-build security ci clean help

export PYTHONPATH := services/brain/src:services/backend:services/openclaw-bridge/src

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

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

# -- Frontend -----------------------------------------------------------------

build-frontend: ## Build frontend (pnpm)
	cd services/frontend && pnpm install --frozen-lockfile && pnpm build

# -- Docker -------------------------------------------------------------------

CORE_SERVICES := brain backend frontend voice openclaw-bridge \
	gas-bridge ha-bridge biometric-bridge obsidian-bridge \
	news-bridge weather-bridge switchbot-bridge tapo-bridge

docker-build: ## Build all core Docker images (no push)
	@for svc in $(CORE_SERVICES); do \
		echo "\n\033[36m=== Building $$svc ===\033[0m"; \
		docker build -t hems-$$svc:dev services/$$svc || exit 1; \
	done

# -- Security -----------------------------------------------------------------

security: ## Run pip-audit + hadolint
	pip-audit -r services/brain/requirements.txt
	pip-audit -r services/backend/requirements.txt
	pip-audit -r services/openclaw-bridge/requirements.txt
	@echo "\n\033[36m=== Hadolint ===\033[0m"
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
