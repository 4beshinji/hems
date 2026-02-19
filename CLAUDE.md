# CLAUDE.md

## Project Overview

**HEMS (Home Environment Management System)** — a personal life management system for a single occupant, forked from SOMS (Symbiotic Office Management System). Combines an LLM "brain" with IoT sensors, plugin-based voice synthesis, and an XP gamification system. The AI has a configurable character personality (YAML-based) and makes real-time decisions about the home environment using sensor data, biometrics, and schedule information.

Forked from SOMS commit `1216952` (2026-02-16).

## Build & Run Commands

All services run via Docker Compose from the `infra/` directory.

```bash
# Initial setup
cp env.example .env
cd infra && docker compose up -d --build

# With VOICEVOX TTS
docker compose --profile voicevox up -d --build

# With local LLM (AMD ROCm)
docker compose --profile ollama up -d --build

# With PostgreSQL (instead of SQLite)
docker compose --profile postgres up -d --build

# With OpenClaw desktop agent (PC metrics + service monitor)
docker compose --profile openclaw up -d --build

# With Obsidian knowledge store
docker compose --profile obsidian up -d --build

# Rebuild a single service
docker compose up -d --build <service-name>

# View logs
docker logs -f hems-brain
docker logs -f hems-voice
```

Service names (Docker Compose): `mosquitto`, `brain`, `backend`, `frontend`, `voice-service`, `mock-llm`
Optional profiles: `voicevox`, `ollama`, `postgres`, `openclaw`, `obsidian`

### Frontend Development

```bash
cd services/frontend
pnpm install
pnpm dev      # Vite dev server
pnpm build    # tsc -b && vite build
```

## Architecture

### Service Ports

Host ports are configurable via `HEMS_PORT_*` env vars. Defaults are offset from SOMS to allow coexistence.

| Service | Default Port | Env Var | Container |
|---------|-------------|---------|-----------|
| Frontend (nginx) | 8080 | `HEMS_PORT_FRONTEND` | hems-frontend |
| Backend API | 8010 | `HEMS_PORT_BACKEND` | hems-backend |
| Mock LLM | 8011 | `HEMS_PORT_MOCK_LLM` | hems-mock-llm |
| Voice Service | 8012 | `HEMS_PORT_VOICE` | hems-voice |
| OpenClaw Bridge | 8013 | `HEMS_PORT_OPENCLAW_BRIDGE` | hems-openclaw-bridge |
| Obsidian Bridge | 8014 | `HEMS_PORT_OBSIDIAN_BRIDGE` | hems-obsidian-bridge |
| VOICEVOX | 50031 | `HEMS_PORT_VOICEVOX` | hems-voicevox |
| Ollama | 11444 | `HEMS_PORT_OLLAMA` | hems-ollama |
| PostgreSQL | 5442 | `HEMS_PORT_POSTGRES` | hems-postgres |
| MQTT | 1893 | `HEMS_PORT_MQTT` | hems-mqtt |

### MQTT Topic Structure

```
# Sensor telemetry
office/{zone}/{device_type}/{device_id}/{channel}

# PC metrics (OpenClaw bridge)
hems/pc/metrics/{cpu|memory|gpu|disk}
hems/pc/processes/top
hems/pc/bridge/status

# Service monitor (OpenClaw bridge)
hems/services/{name}/status
hems/services/{name}/event

# Knowledge store (Obsidian bridge)
hems/personal/notes/changed
hems/personal/notes/stats

# Personal data (Phase 2: data-bridge)
hems/personal/calendar/{id}/events
hems/personal/biometrics/{provider}/heart_rate
hems/personal/training/fitness
hems/system/gpu/utilization

# Brain control
hems/brain/reload-character
```

### Brain Service

- ReAct cognitive loop (30s cycle, max 5 iterations)
- Dual mode: LLM + rule-based fallback (GPU load > threshold)
- Character personality injection into system prompt
- Event store data mart (SOMS-compatible schema)
- Alert suppression: prevents duplicate tasks while environment slowly responds
  (e.g., AC cooling after task created — 30min for temp, 10min for CO2)
- 4 core tools: `create_task`, `send_device_command`, `get_zone_status`, `speak`
- OpenClaw tools (profile `openclaw`): `get_pc_status`, `run_pc_command`, `control_browser`, `send_pc_notification`
- Service monitor tool (when data available): `get_service_status`
- Obsidian tools (profile `obsidian`): `search_notes`, `write_note`, `get_recent_notes`

### OpenClaw Bridge (profile: `openclaw`)

Desktop agent integration service. Monitors host PC and external services.

- PC metrics: CPU / memory / GPU / disk / top processes → `hems/pc/*`
- Service monitor: Gmail (IMAP), GitHub (REST API), browser-based checkers → `hems/services/*`
- Edge-triggered events: unread count increases fire MQTT events for immediate LLM response

Configure in `.env`:
```bash
OPENCLAW_GATEWAY_URL=ws://host.docker.internal:18789
HEMS_GMAIL_ENABLED=true
HEMS_GMAIL_EMAIL=user@gmail.com
HEMS_GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
HEMS_GITHUB_ENABLED=true
HEMS_GITHUB_TOKEN=ghp_xxxx
```

### Voice Service (Plugin-based TTS)

TTSProvider ABC with backends:
- `espeak` — espeak-ng (default fallback, no GPU)
- `voicevox` — VOICEVOX Docker (profile: voicevox)
- `edge-tts` — Microsoft Edge TTS (cloud, free)
- `voisona` — VoiSona Talk (host app, Phase 4)
- `style-bert-vits2` — Local API (Phase 4)

### AI Character System

YAML-based character configuration with template inheritance.

```bash
# Zero-config: default personality
docker compose up -d

# One-liner: built-in template
echo 'CHARACTER=tsundere' >> .env

# Full custom: edit config/character.yaml
cp config/character.yaml.example config/character.yaml
# Hot-reload: mosquitto_pub -t hems/brain/reload-character -m reload
```

Templates: `default`, `tsundere`, `gentle-senpai`, `butler`
Validator: `python validate_character.py config/character.yaml`
         `python validate_character.py --all`   # validate all templates
         `python validate_character.py --list`  # list available templates

### Database

- Default: SQLite (`aiosqlite`) — zero config
- Optional: PostgreSQL 16 (`--profile postgres`)
- Backend: Task, User, PointLog, VoiceEvent, SystemStats
- Brain event_store: raw_events, llm_decisions, hourly_aggregates (SOMS-compatible)
- Retention: 730 days (2 years) for raw_events and llm_decisions

### OpenClaw Integration (Desktop Agent)

Bridges physical environment management with PC/desktop control via [OpenClaw](https://github.com/openclaw/openclaw).

- **openclaw-bridge**: Docker service connecting to OpenClaw Gateway via WebSocket
  - Polls PC metrics (CPU, memory, GPU, disk, temperatures) every 10s
  - Publishes to `hems/pc/*` MQTT topics
  - REST API for brain tools to execute commands, send notifications, control browser
- **Deploy**: OpenClaw runs on host OS (needs desktop access), bridge connects via `host.docker.internal:18789`
- **Profile**: `docker compose --profile openclaw up -d --build`
- **Brain tools**: `get_pc_status`, `run_pc_command` (with dangerous command blocklist), `control_browser`, `send_pc_notification`
- **Safety**: Destructive commands (`rm -rf /`, `mkfs`, `shutdown`, etc.) are blocked by sanitizer

### Obsidian Integration (Knowledge Store)

Connects Obsidian vault to HEMS Brain for bidirectional knowledge access.

- **obsidian-bridge**: Docker service with watchdog file monitoring
  - Indexes vault `.md` files with TF-IDF keyword search
  - Watches for file changes, publishes to `hems/personal/notes/*` MQTT topics
  - REST API for search, read, write operations
- **Deploy**: Mount vault directory, bridge indexes on startup
- **Profile**: `docker compose --profile obsidian up -d --build`
- **Brain tools**: `search_notes` (vault search), `write_note` (HEMS/ directory only), `get_recent_notes`
- **Writeback**: Decision logs (`HEMS/decisions/`) and learning memos (`HEMS/learnings/`) auto-generated
- **Token budget**: Only metadata in LLM context (~30 tokens); full content via on-demand `search_notes`
- **Safety**: Write restricted to `HEMS/` subdirectory, path traversal blocked, 10000 char limit

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt, Pydantic 2.x
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion
- **LLM**: OpenAI / Anthropic / Ollama (multi-provider)
- **TTS**: Plugin-based (espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk, Style-Bert-VITS2)
- **Infra**: Docker Compose, Mosquitto MQTT, SQLite / PostgreSQL

## Code Conventions

- All Python I/O uses `async/await`
- Configuration via environment variables (`.env`)
- Source code bind-mounted into containers (changes take effect on restart)
- Bilingual: English code/comments, Japanese UI/voice/docs
- `xp_reward` (50-500) replaces SOMS `bounty` (500-5000)
- No wallet service — points integrated into backend

## Key Differences from SOMS

| SOMS | HEMS |
|------|------|
| PostgreSQL required | SQLite default |
| Wallet (double-entry ledger) | Points/XP (backend integrated) |
| VOICEVOX only | Plugin TTS (5 backends) |
| Hardcoded personality | YAML character system |
| Ollama only | OpenAI / Anthropic / Ollama |
| 11 services | 7 core + optional profiles |
| Office/multi-user | Home/single occupant |
| No alert suppression | Alert suppression (30min/10min) |
| npm | pnpm |
