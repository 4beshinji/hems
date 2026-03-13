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

# With local LLM (GPU auto-detect → generates docker-compose.gpu.yml)
python infra/scripts/gpu_setup.py
cd infra && docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  --profile ollama up -d --build
# Pull default model (first time only)
docker exec hems-ollama ollama pull qwen3.5

# With local LLM (CPU-only, no GPU override needed)
docker compose --profile ollama up -d --build
# Pull default model (first time only)
docker exec hems-ollama ollama pull qwen3.5
# Lighter alternatives: qwen2.5:7b, llama3.2:3b

# With PostgreSQL (instead of SQLite)
docker compose --profile postgres up -d --build

# With localcraw (PC metrics + service monitor, no external gateway needed)
docker compose --profile localcraw up -d --build

# With Obsidian knowledge store
docker compose --profile obsidian up -d --build

# With GAS integration (Google Calendar/Tasks/Gmail)
docker compose --profile gas up -d --build

# With Home Assistant (smart home control)
docker compose --profile ha up -d --build

# With biometric tracking (smartband/smartwatch: Xiaomi Smart Band, CMF Watch Pro 2, etc.)
docker compose --profile biometric up -d --build

# With perception (camera-based person detection + activity tracking)
docker compose --profile perception up -d --build

# With SwitchBot (direct SwitchBot API, no HA required)
docker compose --profile switchbot up -d --build

# With mock LLM (development, no Ollama needed)
LLM_API_URL=http://mock-llm:8000/v1 LLM_MODEL=mock \
  docker compose --profile mock up -d --build

# Rebuild a single service
docker compose up -d --build <service-name>

# View logs
docker logs -f hems-brain
docker logs -f hems-voice
```

Service names (Docker Compose): `mosquitto`, `brain`, `backend`, `frontend`, `voice-service`, `mock-llm`
Optional profiles: `mock`, `voicevox`, `ollama`, `postgres`, `localcraw`, `obsidian`, `gas`, `ha`, `biometric`, `perception`, `switchbot`

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
| localcraw Bridge | 8013 | `HEMS_PORT_OPENCLAW_BRIDGE` | hems-localcraw-bridge |
| Obsidian Bridge | 8014 | `HEMS_PORT_OBSIDIAN_BRIDGE` | hems-obsidian-bridge |
| GAS Bridge | 8015 | `HEMS_PORT_GAS_BRIDGE` | hems-gas-bridge |
| HA Bridge | 8016 | `HEMS_PORT_HA_BRIDGE` | hems-ha-bridge |
| Biometric Bridge | 8017 | `HEMS_PORT_BIOMETRIC_BRIDGE` | hems-biometric-bridge |
| Perception | 8018 | `HEMS_PORT_PERCEPTION` | hems-perception |
| SwitchBot Bridge | 8019 | `HEMS_PORT_SWITCHBOT_BRIDGE` | hems-switchbot-bridge |
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

# GAS integration (Google Apps Script bridge)
hems/gas/calendar/upcoming
hems/gas/calendar/free_slots
hems/gas/tasks/all
hems/gas/tasks/due_today
hems/gas/gmail/summary
hems/gas/gmail/recent
hems/gas/sheets/{name}
hems/gas/drive/recent
hems/gas/bridge/status

# Smart home (HA bridge)
hems/home/{zone}/{domain}/{entity_id}/state
hems/home/bridge/status

# Biometric data (biometric-bridge)
hems/personal/biometrics/{provider}/heart_rate
hems/personal/biometrics/{provider}/spo2
hems/personal/biometrics/{provider}/sleep
hems/personal/biometrics/{provider}/activity
hems/personal/biometrics/{provider}/steps
hems/personal/biometrics/{provider}/stress
hems/personal/biometrics/{provider}/fatigue
hems/personal/biometrics/bridge/status

# Perception (camera detection + activity tracking + VLM)
office/{zone}/camera/{camera_id}/status
office/{zone}/activity/{monitor_id}
hems/perception/bridge/status
hems/perception/vlm/{zone}
hems/perception/vlm/status
hems/perception/vlm/model_swap
hems/perception/vlm/request

# Personal data (future: data-bridge)
hems/personal/calendar/{id}/events
hems/personal/training/fitness
hems/system/gpu/utilization

# Shopping list
hems/shopping/{added,updated,purchased}

# SwitchBot (direct API bridge)
hems/switchbot/{device_id}/state
hems/switchbot/bridge/status

# Weather (weather-bridge)
hems/weather/{current,forecast,alerts}
hems/weather/bridge/status

# Brain control
hems/brain/reload-character
hems/brain/guest-mode
```

### Brain Service

- ReAct cognitive loop (30s cycle, max 5 iterations)
- Dual mode: LLM + rule-based fallback (GPU load > threshold)
- Character personality injection into system prompt
- Event store data mart (SOMS-compatible schema)
- Alert suppression: prevents duplicate tasks while environment slowly responds
  (e.g., AC cooling after task created — 30min for temp, 10min for CO2)
- Tri-domain world model: Physical Space (zones, smart home, weather), Digital Space (PC, services, GAS, knowledge, shopping), User State (biometrics, screen time)
- 6 core tools: `create_task`, `send_device_command`, `get_zone_status`, `speak`, `get_active_tasks`, `get_device_status`
- localcraw tools (profile `localcraw`): `get_pc_status`, `run_pc_command`, `control_browser`, `send_pc_notification`
- Service monitor tool (when data available): `get_service_status`
- Obsidian tools (profile `obsidian`): `search_notes`, `write_note`, `get_recent_notes`
- HA tools (profile `ha`): `control_light`, `control_climate`, `control_cover`, `get_home_devices`, `control_switch`, `get_sensor_data`, `execute_scene`
- System tools (with `ha`): `set_guest_mode`, `get_weather`
- Biometric tools (profile `biometric`): `get_biometrics`, `get_sleep_summary`
- Perception tools (profile `perception`): `get_perception_status`, `describe_scene` (VLM on-demand scene analysis)
- Shopping tools (always enabled): `add_shopping_item`, `get_shopping_list`
- SwitchBot tools (profile `switchbot`): `get_switchbot_devices`, `control_switchbot`, `send_switchbot_ir`
- Schedule learner (with `ha` profile): arrival/departure/wake pattern learning and prediction (+ biometric sleep data)

### localcraw Bridge (profile: `localcraw`)

PC metrics + service monitor bridge. OpenClaw Gateway 不要 — Node.js + systeminformation で直接ホスト計測。

- PC metrics: CPU / memory / GPU / disk / top processes → `hems/pc/*`
- Service monitor: Gmail (IMAP), GitHub (REST API), browser-based checkers (Playwright内蔵) → `hems/services/*`
- Edge-triggered events: unread count increases fire MQTT events for immediate LLM response

Configure in `.env`:
```bash
LOCALCRAW_BRIDGE_URL=http://localcraw-bridge:8000
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
- `voisona` — VoiSona Talk (host app)

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

Templates: `ena` (default), `tsundere`, `gentle-senpai`, `butler`, `nurserobo-typet`, `default`
Validator: `python validate_character.py config/character.yaml`
         `python validate_character.py --all`   # validate all templates
         `python validate_character.py --list`  # list available templates

### Database

- Default: SQLite (`aiosqlite`) — zero config
- Optional: PostgreSQL 16 (`--profile postgres`)
- Backend: Task, User, VoiceEvent, SystemStats, ShoppingItem, PurchaseHistory
- Brain event_store: raw_events, llm_decisions, hourly_aggregates (SOMS-compatible)
- Retention: 730 days (2 years) for raw_events and llm_decisions

### localcraw Integration (PC Metrics + Desktop Control)

PC metrics collection and desktop control. OpenClaw Gateway 不要。Node.js + systeminformation で直接ホスト計測、Playwright 内蔵ブラウザ制御。

- **localcraw-bridge**: Docker service (Node.js) running on host PID namespace
  - Polls PC metrics (CPU, memory, GPU, disk, temperatures) every 10s via systeminformation
  - Publishes to `hems/pc/*` MQTT topics
  - REST API for brain tools to execute commands, send notifications, control browser
- **Deploy**: ホストプロセス不要 — `pid:host` + `/proc` `/sys` マウントで直接取得
- **Profile**: `docker compose --profile localcraw up -d --build`
- **Brain tools**: `get_pc_status`, `run_pc_command` (with dangerous command blocklist), `control_browser`, `send_pc_notification`
- **Safety**: Destructive commands (`rm -rf /`, `mkfs`, `shutdown`, etc.) are blocked by sanitizer

### GAS Integration (Google Apps Script)

Bridges Google services (Calendar, Tasks, Gmail, Sheets, Drive) to HEMS via GAS Web App proxy.

- **GAS Script**: `scripts/gas-bridge/Code.gs` — deploy as Web App, `doGet(e)` handler with action-based routing
- **gas-bridge**: Docker service polling GAS Web App and publishing to MQTT
  - Calendar: upcoming events + free slots every 120s
  - Tasks: all + due today every 300s
  - Gmail: summary + recent every 300s
  - Sheets: configured sheets every 600s
  - Drive: recent files every 600s
- **Deploy**: Deploy GAS as Web App, configure `GAS_WEBAPP_URL` + `GAS_API_KEY`
- **Profile**: `docker compose --profile gas up -d --build`
- **Brain rules**: meeting reminders, morning briefing, evening summary, overdue alerts, task sync, unread Gmail alerts, etc.
- **GAS Quota**: ~1,100 calls/day with defaults (quota limit: 20,000/day)

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

### Home Assistant Integration (Smart Home)

Connects Home Assistant to HEMS for smart home device control and life automation.

- **ha-bridge**: Docker service connecting to HA via REST/WebSocket API
  - WebSocket: real-time `state_changed` events → MQTT publish
  - REST API: Brain tool calls → HA service calls
  - Polling fallback: 30s interval when WebSocket disconnects
  - Publishes to `hems/home/*` MQTT topics
- **Deploy**: HA running on host or via Docker, configure `HA_URL` + `HA_TOKEN`
- **Profile**: `docker compose --profile ha up -d --build`
- **Brain tools**: `control_light`, `control_climate`, `control_cover`, `get_home_devices`, `control_switch`, `get_sensor_data`, `execute_scene`
- **System tools** (always with HA): `set_guest_mode`, `get_weather`
- **Schedule learner**: learns arrival/departure/wake patterns from occupancy data
- **Automation rules**: sleep detection → lights off, pre-arrival HVAC, wake-up curtains, circadian lighting, guest mode filtering
- **Supported devices**: SwitchBot (via HA), Nature Remo (via HA), any HA integration
- **Safety**: temperature 16-30, brightness 0-255, position 0-100 range validation

Configure in `.env`:
```bash
HA_URL=http://host.docker.internal:8123
HA_TOKEN=your-long-lived-access-token
HA_BRIDGE_URL=http://ha-bridge:8000
```

### Biometric Integration (Smartband)

Tracks heart rate, sleep, activity, stress, and fatigue via smartband/smartwatch (Xiaomi Smart Band, Amazfit, CMF Watch Pro 2) via Health Connect or Huami cloud API.

- **biometric-bridge**: Docker service receiving webhook data from Gadgetbridge app
  - POST webhook endpoint normalizes device data → MQTT publish
  - Fatigue score computation (weighted: HR 30%, sleep 40%, stress 30%)
  - Sleep session caching for daily summaries
  - Publishes to `hems/personal/biometrics/*` MQTT topics
- **Deploy**: Install Gadgetbridge on phone, configure webhook to `http://<host>:8017/api/biometric/webhook`
- **Profile**: `docker compose --profile biometric up -d --build`
- **Brain tools**: `get_biometrics` (current readings), `get_sleep_summary` (last night's sleep)
- **Brain rules**: 7 rules (high HR/stress/fatigue alerts, sleep quality notification, step goal, sleep detection lights off, fatigue-linked dimming)
- **Thresholds**: HR > 120, HR < 45, SpO2 < 92, Stress > 80 (configurable via env vars)
- **World model**: Tri-domain architecture — biometrics in User State domain, threshold crossing events

Configure in `.env`:
```bash
BIOMETRIC_BRIDGE_URL=http://biometric-bridge:8000
BIOMETRIC_PROVIDER=gadgetbridge
```

### Perception (Camera Detection + Activity Tracking + VLM Scene Analysis)

Camera-based person detection and posture/activity tracking using YOLOv11s-pose,
with optional VLM (Vision Language Model) integration via Ollama for scene understanding.

- **perception**: Docker service with YOLOv11s-pose inference pipeline
  - Captures frames from MCP (ESP32 MQTT) or stream (RTSP/HTTP) cameras
  - Single-pass person detection + skeleton keypoint extraction
  - Posture classification (standing/sitting/lying/walking) from COCO 17 keypoints
  - Activity level (0.0-1.0) with EMA smoothing + tiered pose buffer
  - Publishes to `office/{zone}/camera/{cam_id}/status` and `office/{zone}/activity/{cam_id}`
- **VLM integration** (optional, requires `--profile ollama` + `VLM_ENABLED=true`):
  - Dual-model strategy: light (moondream ~1.8B) for routine scans, heavy (minicpm-v ~3B) for events
  - Adaptive frequency: 30min routine → event-boosted (1-5min) → quiet decay (up to 2hr)
  - Event-triggered boost: YOLO detects person enter/leave → heavy VLM for detailed analysis
  - Model swap coordination: heavy VLM evicts brain LLM; brain falls back to rule-based mode during swap (~10-30s)
  - On-demand analysis via brain `describe_scene` tool
  - Publishes to `hems/perception/vlm/{zone}`, `hems/perception/vlm/status`, `hems/perception/vlm/model_swap`
- **Deploy**: Configure cameras in `HEMS_PERCEPTION_CAMERAS` env var (JSON array)
- **Profile**: `docker compose --profile perception up -d --build`
- **Brain integration**: WorldModel receives occupancy + activity + VLM scene data via MQTT, Rule Engine triggers sedentary alerts, sleep detection, and VLM anomaly alerts
- **Brain tools**: `get_perception_status`, `describe_scene` (VLM on-demand)
- **Privacy**: RAM-only processing, no image storage, person class only (no face recognition), all local
- **GPU**: Optional GPU acceleration (auto-detected by `gpu_setup.py`), CPU fallback

Configure in `.env`:
```bash
PERCEPTION_BRIDGE_URL=http://perception:8000
HEMS_PERCEPTION_CAMERAS=[{"device_id":"cam01","zone":"living_room","type":"mcp"}]
# VLM (requires --profile ollama)
VLM_ENABLED=true
VLM_LIGHT_MODEL=moondream
VLM_HEAVY_MODEL=minicpm-v
```

### SwitchBot Integration (Direct API)

Controls SwitchBot devices directly via SwitchBot API (HA不要).

- **switchbot-bridge**: Docker service polling SwitchBot Cloud API
  - Device state polling + MQTT publish
  - REST API for brain tool calls → SwitchBot API commands
  - IR remote support via Hub (AC, TV, etc.)
  - Publishes to `hems/switchbot/*` MQTT topics
- **Deploy**: Get token/secret from SwitchBot app, configure device map
- **Profile**: `docker compose --profile switchbot up -d --build`
- **Brain tools**: `get_switchbot_devices`, `control_switchbot` (turnOn/turnOff/toggle/setBrightness/setPosition/setColorTemperature/press), `send_switchbot_ir` (Hub IR commands)

Configure in `.env`:
```bash
SWITCHBOT_BRIDGE_URL=http://switchbot-bridge:8000
SWITCHBOT_TOKEN=your-switchbot-token
SWITCHBOT_SECRET=your-switchbot-secret
SWITCHBOT_DEVICE_MAP={}
```

### Shopping List

Built-in shopping list with brain integration.

- **Backend**: CRUD API for shopping items with purchase history
- **Database**: `ShoppingItem`, `PurchaseHistory` models
- **Brain tools**: `add_shopping_item`, `get_shopping_list` (always enabled)
- **Brain rules**: recurring items due reminder, departure notification with pending items
- **MQTT**: `hems/shopping/{added,updated,purchased}`
- **World model**: `ShoppingState` in Digital Space (due items, pending count)

### Weather Integration (weather-bridge)

Weather data from JMA (気象庁) or OpenWeatherMap.

- **weather-bridge**: Service polling weather APIs → MQTT publish
  - Providers: JMA (free, default), OpenWeatherMap
  - Publishes to `hems/weather/{current,forecast,alerts}` MQTT topics
- **Brain rules**: rain window detection, hot forecast notification
- **World model**: `WeatherState` in Physical Space

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt, Pydantic 2.x
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion
- **LLM**: OpenAI / Anthropic / Ollama (multi-provider)
- **TTS**: Plugin-based (espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk)
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
| VOICEVOX only | Plugin TTS (4 backends) |
| Hardcoded personality | YAML character system |
| Ollama only | OpenAI / Anthropic / Ollama |
| 11 services | 7 core + optional profiles |
| Office/multi-user | Home/single occupant |
| No alert suppression | Alert suppression (30min/10min) |
| npm | pnpm |
