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

# Rebuild a single service
docker compose up -d --build <service-name>

# View logs
docker logs -f hems-brain
docker logs -f hems-voice
```

Service names: `mosquitto`, `brain`, `backend`, `frontend`, `voice-service`, `mock-llm`
Optional: `voicevox`, `ollama`, `postgres`, `perception`

### Frontend Development

```bash
cd services/frontend
npm install
npm run dev      # Vite dev server
npm run build    # tsc -b && vite build
```

## Architecture

### Service Ports

| Service | Port | Container |
|---------|------|-----------|
| Frontend (nginx) | 80 | hems-frontend |
| Backend API | 8000 | hems-backend |
| Mock LLM | 8001 | hems-mock-llm |
| Voice Service | 8002 | hems-voice |
| VOICEVOX | 50021 | hems-voicevox |
| Ollama | 11434 | hems-ollama |
| PostgreSQL | 5432 | hems-postgres |
| MQTT | 1883 | hems-mqtt |

### MQTT Topic Structure

```
# Sensor telemetry
office/{zone}/{device_type}/{device_id}/{channel}

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
- 4 tools: `create_task`, `send_device_command`, `get_zone_status`, `speak`

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

### Database

- Default: SQLite (`aiosqlite`) — zero config
- Optional: PostgreSQL 16 (`--profile postgres`)
- Backend: Task, User, PointLog, VoiceEvent, SystemStats
- Brain event_store: raw_events, llm_decisions, hourly_aggregates (SOMS-compatible)

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt, Pydantic 2.x
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, Framer Motion
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
