# HEMS — Agent Onboarding Guide

> This file is written for AI coding agents. It assumes no prior knowledge of the project. All facts below are derived from the actual repository contents (`pyproject.toml`, `Makefile`, `infra/docker-compose.yml`, service code, tests, and documentation). Code comments are in English; user-facing docs are mostly Japanese.

## Project Overview

**HEMS (Home Environment Management System)** is a personal, single-occupant home automation platform. It combines an LLM "brain" with IoT sensors, plugin-based text-to-speech, a VRM 3D avatar, and a React dashboard. It was forked from SOMS (Symbiotic Office Management System) commit `1216952`.

Core design:

- **Brain** (`services/brain/src`): ReAct cognitive loop (30s cycle, max 5 iterations) with LLM + rule-based fallback. Maintains a tri-domain world model (Physical / Digital / User State), device registry, event store, and chat server.
- **Backend** (`services/backend`): FastAPI service that is the persistent source-of-truth for tasks, devices, shopping, chat, voice events, and user data.
- **Frontend** (`services/frontend`): React 19 + TypeScript dashboard with AI chat, device/scene/automation UI, and VRM avatar.
- **Voice** (`services/voice`): Plugin TTS service (espeak / VOICEVOX / Edge TTS / VoiSona Talk / Style-Bert-VITS2 / AIVoice).
- **Bridges** (`services/*-bridge`): Optional adapters for Home Assistant, SwitchBot, Tapo, biometric wearables, weather, news, knowledge ingestion, Google Apps Script, Obsidian, and PC/service monitoring.
- **Edge** (`edge/`): MicroPython/ESP32 firmware for sensor and camera nodes, plus a SensorSwarm hub/leaf network.
- **Android companions**: `services/mobile-android/` (HEMS mobile companion) and `apps/healthconnect-companion/` (Health Connect biometric sync). These are **not** Dockerized.

License: [PolyForm Noncommercial License 1.0.0](LICENSE). Non-commercial personal/hobbyist use on your own hardware is permitted; commercial use requires a separate written agreement.

## Technology Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.11 |
| Web framework | FastAPI, Uvicorn, aiohttp |
| ORM / DB | SQLAlchemy 2.x (async), SQLite default, optional PostgreSQL 16 |
| Messaging | Mosquitto MQTT (paho-mqtt) |
| Validation / config | Pydantic 2.x, python-dotenv, YAML |
| LLM | OpenAI / Anthropic / Ollama (routed via `LLMRouter`) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion, pnpm |
| 3D Avatar | Three.js, React Three Fiber, @pixiv/three-vrm |
| TTS | espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk, Style-Bert-VITS2, AIVoice |
| Search | BM25 (rank_bm25) + vector (Ollama embeddings) + title boost, 3-way RRF |
| Perception | YOLOv11s-pose, moondream / minicpm-v VLM |
| STT | Whisper large-v3-turbo |
| Infra | Docker Compose, BuildKit, Mosquitto |
| Edge | MicroPython on ESP32, ESP-NOW/UART/I2C/BLE |

## Project Structure

```
hems/
├── AGENTS.md                 # this file
├── README.md                 # user-facing intro (mostly Japanese)
├── CLAUDE.md                 # high-level orientation hub + doc graph map
├── pyproject.toml            # Python project metadata + ruff + pytest + coverage
├── Makefile                  # common dev/test/build commands
├── env.example               # canonical environment variable template
├── requirements-dev.txt      # dev/test/lint/security dependencies
├── services/
│   ├── brain/src/            # cognitive engine, world model, tools, ReAct loop
│   ├── backend/              # FastAPI REST API + database models/routers
│   ├── frontend/             # React dashboard
│   ├── voice/                # TTS + STT service
│   ├── _common/              # shared `hems_common` bridge infrastructure
│   └── *-bridge/             # optional integration bridges
├── tests/                    # repository-level pytest suite
├── services/brain/tests/     # brain-specific pytest suite
├── infra/
│   ├── docker-compose.yml    # full compose stack with optional profiles
│   ├── base/Dockerfile       # hems-base:py3.11 shared Python runtime
│   ├── scripts/              # validation / setup helpers
│   └── ...                   # mosquitto, zigbee2mqtt, ha-config, mock_llm
├── config/
│   ├── characters/           # built-in character YAML templates
│   ├── character.yaml.example
│   └── motions.yaml          # VRM avatar motion definitions
├── edge/                     # ESP32/MicroPython edge code
├── docs/                     # extensive documentation graph (see docs/README.md)
├── scripts/                  # seed/extraction/reset utilities
└── apps/healthconnect-companion/   # Android Health Connect app
```

Root-level helpers:

- `validate_character.py` — validate character YAML templates
- `bridge_auth.py` — removed; internal bridge auth now lives in `services/_common/hems_common/auth.py`
- `env.example` — canonical environment variable template

### Key service boundaries

- **`services/brain/src`** — cognitive engine only. Never add REST routes here; expose internal APIs via `brain_chat_server.py` or MQTT.
- **`services/backend`** — persistence and HTTP. Routers live under `routers/`, SQLAlchemy models under `models.py`, Pydantic schemas under `schemas.py`.
- **`services/_common`** — shared bridge package (`hems_common`) installed into the base Docker image. Contains MQTT publisher, lifespan helpers, config, auth, and status reporting.
- **`services/frontend/src`** — dashboard. Pages under `app/`, shared components under `components/`, hooks under `hooks/`, lib/utilities under `lib/`.

### Device Registry architecture

The system uses a **two-layer** device registry:

1. **Backend (`services/backend/models.py`, `routers/devices.py`)** — persistent source-of-truth (SQLite/Postgres). Auto-registers unknown devices from brain heartbeats and serves the frontend UI.
2. **Brain (`services/brain/src/device_registry.py`)** — in-memory TTL cache for LLM context, state machine (online/stale/sleeping/offline), and timeout optimization.

Do **not** merge these layers. Brain parses MQTT → updates cache → pushes `POST /devices/heartbeat` to Backend → Frontend reads Backend.

## Build, Test, and Development Commands

All commands assume the repository root as working directory unless otherwise noted.

### Initial setup

```bash
cp env.example .env
# Edit .env (at minimum set MQTT_PASS, and LLM provider/API key if not using Ollama)
```

### Local stack (Docker Compose)

```bash
cd infra

# One-time build of the shared Python base image
docker compose --profile bootstrap build base

# Start the always-on core (mosquitto + brain + backend + frontend + voice-service)
docker compose up -d --build

# Optional profiles (can be combined)
docker compose --profile voicevox up -d --build
docker compose --profile ollama up -d --build
docker compose --profile postgres up -d --build
docker compose --profile openclaw up -d --build
docker compose --profile obsidian up -d --build
docker compose --profile gas up -d --build
docker compose --profile ha up -d --build
docker compose --profile biometric up -d --build
docker compose --profile perception up -d --build
docker compose --profile switchbot up -d --build
docker compose --profile tapo up -d --build
docker compose --profile zigbee up -d --build
docker compose --profile news --profile ollama up -d --build
docker compose --profile knowledge up -d --build
docker compose --profile stt up -d --build

# With mock LLM (dev, no Ollama)
LLM_API_URL=http://mock-llm:8000/v1 LLM_MODEL=mock docker compose --profile mock up -d --build
```

Entry points after startup:

- Dashboard: http://localhost:8080
- Backend API docs: http://localhost:8010/docs
- Voice API docs: http://localhost:8012/docs

### Makefile commands

```bash
make lint          # ruff check . && ruff format --check .
make format        # ruff check --fix . && ruff format .
make test          # pytest tests/ services/brain/tests/ with coverage
make test-quick    # same tests without coverage (faster)
make build-frontend
make docker-base   # build hems-base:py3.11
make docker-build  # build all core images (after docker-base)
make docker-build-heavy   # perception + stt (GPU_TYPE aware)
make docker-build-all     # base + core + heavy
make security      # pip-audit + hadolint
make ci            # lint + test + build-frontend + security
make clean         # remove caches, htmlcov, frontend/dist
make help          # show all targets
```

### Frontend development

```bash
cd services/frontend
pnpm install
pnpm dev      # Vite dev server
pnpm build    # tsc -b && vite build
pnpm test     # vitest run
pnpm lint     # eslint
```

### Android projects

These are **not** built or run by Docker Compose.

```bash
# HEMS mobile companion
cd services/mobile-android
./gradlew assembleDebug

# Health Connect biometric sync
cd apps/healthconnect-companion
./gradlew assembleDebug
```

### Character validation

```bash
python validate_character.py --all      # validate all built-in templates
python validate_character.py --list     # list templates
python validate_character.py config/character.yaml
```

## Runtime Architecture

### Core services (always-on)

| Service | Container | Default Port | Role |
|---------|-----------|--------------|------|
| Mosquitto | hems-mqtt | 1893 | MQTT broker |
| Brain | hems-brain | — | ReAct cognitive loop, chat server, world model |
| Backend | hems-backend | 8010 | FastAPI REST API + persistence |
| Frontend | hems-frontend | 8080 | React dashboard (nginx) |
| Voice service | hems-voice | 8012 | TTS + STT |

### Optional bridge / heavy services

| Service | Profile | Port | Container |
|---------|---------|------|-----------|
| Mock LLM | mock | 8011 | hems-mock-llm |
| OpenClaw bridge | openclaw | 8013 | hems-openclaw-bridge |
| Obsidian bridge | obsidian | 8014 | hems-obsidian-bridge |
| GAS bridge | gas | 8015 | hems-gas-bridge |
| HA bridge | ha | 8016 | hems-ha-bridge |
| Biometric bridge | biometric | 8017 | hems-biometric-bridge |
| Perception | perception | 8018 | hems-perception |
| SwitchBot bridge | switchbot | 8019 | hems-switchbot-bridge |
| Tapo bridge | tapo | 8020 | hems-tapo-bridge |
| News bridge | news | 8021 | hems-news-bridge |
| Knowledge bridge | knowledge | 8022 | hems-knowledge-bridge |
| STT service | stt | 8023 | hems-stt |
| VOICEVOX | voicevox | 50031 | hems-voicevox |
| Ollama | ollama | 11444 | hems-ollama |
| PostgreSQL | postgres | 5442 | hems-postgres |

Ports are configurable via `HEMS_PORT_*` environment variables.

### MQTT topic conventions

- `hems/sensors/{zone}/{device_type}/{device_id}/{channel}` — physical sensor telemetry + camera/activity
- `office/{zone}/{device_type}/{device_id}/{channel}` — legacy SOMS prefix (brain still accepts both)
- `hems/pc/*`, `hems/services/{name}/*` — PC metrics / service monitor
- `hems/home/{zone}/{domain}/{entity_id}/state` — Home Assistant
- `hems/personal/{notes,biometrics,knowledge}/*` — Obsidian / biometric / knowledge
- `hems/gas/{calendar,tasks,gmail,sheets,drive}/*` — Google integrations
- `hems/{weather,news,shopping}/*`, `hems/perception/vlm/*` — weather / news / shopping / VLM
- `hems/{tapo,switchbot}/*`, `zigbee2mqtt/*` — direct device bridges
- `hems/<service>/bridge/status` — bridge connection status
- `hems/brain/{reload-character,guest-mode}` — brain control

For the full topic tree and verification commands, see `docs/IMPLEMENTATION_MAP.md` §4.

### Docker image build order

All Python services `FROM hems-base:py3.11`. You must build the base image first:

```bash
make docker-base          # or: cd infra && docker compose --profile bootstrap build base
make docker-build         # core Python + frontend
make docker-build-heavy   # perception + stt
```

The base image preinstalls `paho-mqtt`, `fastapi`, `uvicorn`, `aiohttp`, `pydantic`, `loguru`, `python-dotenv`, and the `hems_common` package.

## Code Style and Conventions

### Python

- Target **Python 3.11**.
- **Ruff** is the source of truth for linting and formatting. Configuration is in `pyproject.toml`.
  - 120-character line length.
  - Double quotes.
  - Space indentation (4 spaces).
  - Import sorting with `known-first-party` packages declared in `pyproject.toml`.
- Module and test filenames use `snake_case.py`.
- Use descriptive test names like `test_backend_home_router.py`.
- All I/O must be `async/await`.
- Configuration is read from environment variables (`.env`). Do not hardcode secrets.
- Keep service boundaries clean. Prefer existing helpers over new cross-service abstractions.
- Bilingual convention: **English** code and comments; **Japanese** UI strings, voice prompts, and human docs.

### Frontend

- React 19 functional components, TypeScript strict mode.
- Tailwind CSS 4 utility classes.
- Path alias `@/` maps to `services/frontend/src/`.
- Vite dev server proxies `/api` to the backend.

### Git commits

Use **Conventional Commits** with scopes, e.g.:

```
feat(brain): add morning briefing retry
fix(backend): validate device_id on heartbeat
docs(infra): update compose port table
refactor(brain): split persona rewriter into module
```

## Testing Instructions

### Python tests

Pytest discovers two test trees:

- `tests/`
- `services/brain/tests/`

Run commands:

```bash
make test-quick   # no coverage, fastest feedback loop
make test         # with coverage report
```

Both exclude tests marked `integration`, `e2e`, or `benchmark`. To run those explicitly:

```bash
pytest tests/ services/brain/tests/ -m integration
```

The release gate is full non-integration pytest:

```bash
PYTHONPATH=services/brain/src:services/backend timeout 1800s \
  .venv/bin/python -m pytest tests/ services/brain/tests/ \
  -v --tb=short -m "not integration and not e2e and not benchmark"
```

Test markers (defined in `pyproject.toml`):

- `integration` — requires running services.
- `e2e` — end-to-end, full stack.
- `benchmark` — performance benchmarks.

### Frontend tests

```bash
cd services/frontend
pnpm test        # vitest run
pnpm test:watch  # vitest
```

### CI pipeline

`.github/workflows/ci.yml` runs:

1. Python lint (`ruff check`, `ruff format --check`).
2. Backend tests with coverage (`pytest`, excluding integration/e2e/benchmark).
3. Frontend lint, type check, and build (`pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm build`).
4. Docker build validation for core services.
5. Security scanning (`pip-audit`, `hadolint`).
6. Infra validation (`docker compose config`, `infra/scripts/check_env_compose.py`).

## Security Considerations

- **Never commit secrets or `.env`**. Use `env.example` and `config/*.example` as templates.
- Rotate default passwords before first deployment:
  - `MQTT_PASS`
  - `POSTGRES_PASSWORD`
  - `BACKEND_API_KEY` (gates dashboard routers; empty = LAN-trusted zero-config mode)
  - `HEMS_INTERNAL_TOKEN` (gates voice-service / stt inter-service calls)
- `BACKEND_API_KEY` and `HEMS_INTERNAL_TOKEN` are independent and may differ.
- Device identifiers are validated against `^[\w.\-]+$` with max length 128.
- The `ha` profile runs Home Assistant in `privileged` + `network_mode: host`. Review `docs/ha-isolation.md` before enabling on the same host.
- Run `make security` (or CI) to audit Python dependencies with `pip-audit` and Dockerfiles with `hadolint`.
- For external exposure, protect the dashboard behind a reverse proxy or nginx Basic auth in addition to `BACKEND_API_KEY`.

## Documentation Map

The repository uses a documentation graph. Canonical details live in specific files; this file only summarizes.

| Tier | File | Purpose |
|------|------|---------|
| 0 | `CLAUDE.md` | Project entry / orientation hub |
| 0 | `README.md` | User-facing intro |
| 1 | `services/brain/CLAUDE.md` | Brain canonical (ReAct, tools, chat, event automation) |
| 1 | `services/backend/CLAUDE.md` | Backend canonical (Device Registry, Shopping, Chat REST) |
| 1 | `services/voice/CLAUDE.md` | Voice / TTS / STT canonical |
| 1 | `services/perception/CLAUDE.md` | Perception canonical (YOLO, VLM) |
| 2 | `docs/IMPLEMENTATION_MAP.md` | **Source-of-truth** for code ↔ compose ↔ MQTT ↔ tools ↔ env mapping |
| 2 | `docs/CLAUDE-bridges.md` | 11 bridge integrations canonical |
| 3+ | `docs/README.md` | Human setup / operation guides index |

When adding a new service, tool, topic, or env variable, update in order:

1. `docs/IMPLEMENTATION_MAP.md`
2. The relevant canonical doc (`docs/CLAUDE-bridges.md` or `services/*/CLAUDE.md`)
3. `CLAUDE.md` tables
4. `docs/README.md`
5. `env.example`

## Quick Reference

```bash
# Setup
cp env.example .env

# Core stack
cd infra && docker compose --profile bootstrap build base && docker compose up -d --build

# Lint / format / test
make lint
make format
make test-quick
make test

# Frontend
cd services/frontend && pnpm install && pnpm dev && pnpm build

# Build all Docker images
make docker-base && make docker-build

# Security audit
make security

# Full CI locally
make ci
```
