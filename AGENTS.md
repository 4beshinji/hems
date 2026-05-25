# Repository Guidelines

## Project Structure & Module Organization

HEMS is a multi-service home automation system. Core Python services live under `services/`, with the brain logic in `services/brain/src`, FastAPI backend routes in `services/backend`, and bridge services such as `services/ha-bridge`, `services/news-bridge`, and `services/weather-bridge`. Shared package/config assets are in `hems/` and `config/`. Repository-level tests are in `tests/`; brain-specific tests also live in `services/brain/tests/`. Docker and deployment assets are in `infra/`, edge-device code is in `edge/`, documentation is in `docs/`, and the Android companion app is in `apps/healthconnect-companion/`.

## Build, Test, and Development Commands

- `cp env.example .env`: create local configuration before running services.
- `cd infra && docker compose up -d --build`: start the local stack.
- `make lint`: run `ruff check .` and `ruff format --check .`.
- `make format`: auto-fix Ruff lint issues and format Python code.
- `make test-quick`: run non-integration pytest suites without coverage.
- `make test`: run non-integration pytest suites with coverage reports.
- `make docker-build`: build core Docker images after building `hems-base:py3.11`.
- `cd services/frontend && pnpm install --frozen-lockfile && pnpm build`: build the React frontend.
- `cd apps/healthconnect-companion && ./gradlew build`: build the Android companion app.

## Coding Style & Naming Conventions

Use Python 3.11. Ruff is the source of truth: 120-character lines, double quotes, space indentation, import sorting, and the lint rules configured in `pyproject.toml`. Keep Python module and test filenames `snake_case.py`; use descriptive test names like `test_backend_home_router.py`. Prefer existing service boundaries and helpers over new cross-service abstractions.

## Testing Guidelines

Pytest discovers `tests/` and `services/brain/tests/`. Mark slow or environment-dependent tests with existing markers: `integration`, `e2e`, or `benchmark`; default Make targets exclude them. Add focused tests near the affected behavior, especially for rule engines, routers, sanitizers, data classes, and event-store migrations. Run `make test-quick` before small changes and `make test` when behavior or shared contracts change.

## Commit & Pull Request Guidelines

Git history uses Conventional Commit style, often with scopes: `feat(brain): ...`, `fix(brain): ...`, `docs(infra): ...`, `refactor(brain): ...`. Keep commits focused and imperative. Pull requests should include a short problem/solution summary, linked issue or context, commands run, configuration or migration notes, and screenshots for frontend or dashboard changes.

## Security & Configuration Tips

Do not commit secrets or local `.env` files. Use `env.example` and `config/*.example` as templates. When changing Dockerfiles or dependencies, run `make security` where practical; it uses `pip-audit` and `hadolint`.
