# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SOMS (Symbiotic Office Management System)** — an autonomous, event-driven office management system combining an LLM "brain" with IoT edge devices, computer vision, and a credit-based economy for human-AI collaboration. The LLM makes real-time decisions about the office environment (lighting, HVAC, task delegation) using sensor data and camera feeds.

## Build & Run Commands

All services run via Docker Compose from the `infra/` directory.

```bash
# Initial setup (create volumes, build containers)
cp env.example .env
./infra/scripts/setup_dev.sh

# Full simulation (no GPU/hardware required) — uses mock LLM + virtual edge devices
./infra/scripts/start_virtual_edge.sh

# Production (requires AMD ROCm GPU + real hardware)
docker compose -f infra/docker-compose.yml up -d --build

# Rebuild a single service
docker compose -f infra/docker-compose.yml up -d --build <service-name>

# View logs
docker logs -f soms-brain
docker logs -f soms-perception
```

Service names in docker-compose: `mosquitto`, `brain`, `postgres`, `backend`, `frontend`, `voicevox`, `voice-service`, `wallet`, `wallet-app`, `ollama`, `mock-llm`, `perception`

### Frontend Development

```bash
cd services/dashboard/frontend
npm install
npm run dev      # Vite dev server
npm run build    # tsc -b && vite build
npm run lint     # ESLint
```

### Testing

Tests are standalone Python scripts (no pytest framework):

```bash
# Integration test (end-to-end with mock LLM)
python3 infra/scripts/integration_test_mock.py

# Individual test scripts
python3 infra/scripts/test_task_scheduling.py
python3 infra/scripts/test_world_model.py
python3 infra/scripts/test_human_task.py
```

Perception service tests in `services/perception/`:
```bash
python3 services/perception/test_activity.py
python3 services/perception/test_discovery.py
python3 services/perception/test_yolo_detect.py
```

## Architecture

### 4-Layer Design

1. **Central Intelligence** (`services/brain/`) — LLM-driven decision engine using a ReAct (Think→Act→Observe) cognitive loop. Cycles every 30s or on new MQTT events, max 5 iterations per cycle, 3s event batch delay.
2. **Perception** (`services/perception/`) — YOLOv11 vision system with pluggable monitors (occupancy, whiteboard, activity) defined in `config/monitors.yaml`. Uses host networking for camera access.
3. **Communication** — MQTT broker (Mosquitto) as central message bus. Uses MCP (Model Context Protocol) over MQTT with JSON-RPC 2.0 payloads.
4. **Edge** (`edge/`) — ESP32 devices for sensors and relays. Two firmware variants: MicroPython (`edge/office/`) for production, PlatformIO C++ (`edge/test-edge/`) for development. Shared MicroPython library in `edge/lib/soms_mcp.py`. Diagnostic scripts in `edge/tools/`. All devices use MCP (JSON-RPC 2.0) and publish per-channel telemetry (`{"value": X}`) for WorldModel compatibility.
5. **SensorSwarm** (`edge/swarm/`, `edge/lib/swarm/`) — Hub+Leaf 2-tier sensor network. Hub (ESP32 with WiFi+MQTT) aggregates Leaf nodes via ESP-NOW, UART, I2C, or BLE. Binary protocol (5-245 bytes, MAGIC 0x53, XOR checksum). Device IDs use dot notation: `swarm_hub_01.leaf_env_01`. See `edge/swarm/README.md`.
6. **Wallet** (`services/wallet/`) — Double-entry credit ledger. System wallet (user_id=0) issues credits. Task bounty (500-5000), device XP with dynamic multiplier (1.0x-3.0x).

### Service Ports

| Service | Port | Container Name |
|---------|------|----------------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 8003 | soms-wallet |
| Wallet App (PWA) | 8004 | soms-wallet-app |
| PostgreSQL | 5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT | 1883 | soms-mqtt |

### MQTT Topic Structure

```
# Sensor telemetry (per-channel, payload: {"value": X})
office/{zone}/{device_type}/{device_id}/{channel}
  e.g. office/main/sensor/env_01/temperature

# SensorSwarm (Hub-forwarded, dot-separated device_id)
office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}
  e.g. office/main/sensor/swarm_hub_01.leaf_env_01/temperature

# Camera status
office/{zone}/camera/{camera_id}/status

# Activity detection
office/{zone}/activity/{monitor_id}

# MCP device control (JSON-RPC 2.0)
mcp/{agent_id}/request/{method}
mcp/{agent_id}/response/{request_id}

# Heartbeat (60s interval)
{topic_prefix}/heartbeat
```

Brain subscribes to `office/#`, `hydro/#`, `aqua/#` and `mcp/+/response/#`.

### Inter-Service Communication

- **Brain ↔ Edge Devices**: MCP over MQTT (JSON-RPC 2.0)
- **Brain → Dashboard**: REST API (`POST/GET/PUT /tasks`)
- **Brain → Voice**: REST API (`POST /api/voice/announce`, `POST /api/voice/synthesize`)
- **Perception → MQTT**: Publishes detection results to broker
- **Brain ← MQTT**: Subscribes to sensor telemetry and perception events, triggers cognitive cycles on state changes

### Brain Service Internals (`services/brain/src/`)

- `main.py` — `Brain` class: ReAct cognitive loop, MQTT event handler, component orchestration
- `llm_client.py` — Async OpenAI-compatible API wrapper (aiohttp, 120s timeout)
- `mcp_bridge.py` — MQTT ↔ JSON-RPC 2.0 translation layer (10s timeout per call)
- `world_model/` — `WorldModel` maintains unified zone state from MQTT; `SensorFusion` aggregates readings; `ZoneState`/`EnvironmentData`/`Event` dataclasses
- `task_scheduling/` — `TaskQueueManager` with priority scoring and decision logic
- `tool_registry.py` — OpenAI function-calling schema definitions (5 tools)
- `tool_executor.py` — Routes and executes tool calls with sanitizer validation
- `system_prompt.py` — Constitutional AI system prompt builder
- `sanitizer.py` — Input validation and security
- `dashboard_client.py` — REST client for dashboard backend
- `task_reminder.py` — Periodic reminder service (re-announces tasks after 1 hour)

### LLM Tools (defined in `tool_registry.py`)

| Tool | Purpose | Key Params |
|------|---------|------------|
| `create_task` | Create human task on dashboard with bounty | title, description, bounty (500-5000), urgency (0-4), zone |
| `send_device_command` | Control edge device via MCP | agent_id, tool_name, arguments (JSON) |
| `get_zone_status` | Query WorldModel for zone details | zone_id |
| `speak` | Voice-only announcement (ephemeral, no dashboard) | message (70 chars max), zone, tone |
| `get_active_tasks` | List current tasks (duplicate prevention) | — |

### Perception Service (`services/perception/src/`)

- Monitors are pluggable: `OccupancyMonitor`, `WhiteboardMonitor`, `ActivityMonitor` (all extend `MonitorBase`)
- Image sources abstracted: `RTSPSource`, `MQTTSource`, `HTTPStream` via `ImageSourceFactory`
- `activity_analyzer.py` — Tiered pose buffer (4 tiers, up to 4 hours) with posture normalization
- `camera_discovery.py` — ICMP ping sweep + YOLO verification for auto-discovery
- Monitor config in `config/monitors.yaml` includes YOLO model paths, camera-zone mappings, and discovery settings

### nginx Routing (`services/dashboard/frontend/nginx.conf`)

| Path | Upstream |
|------|----------|
| `/` | SPA (index.html) |
| `/api/wallet/` | wallet:8000 |
| `/api/voice/` | voice-service:8000 |
| `/api/` | backend:8000 |
| `/audio/` | voice-service:8000 |

### Dashboard Backend API (`services/dashboard/backend/`)

SQLAlchemy async ORM with PostgreSQL (asyncpg). Fallback to SQLite (aiosqlite) when `DATABASE_URL` is not set. Key models: `Task` (19 columns: bounty/urgency/voice/queue/assignment fields), `VoiceEvent` (tone: neutral/caring/humorous/alert), `User` (credits), `SystemStats` (total_xp, tasks_completed).

Task duplicate detection: Stage 1 (title + location exact match), Stage 2 (zone + task_type).

Routers: `routers/tasks.py` (CRUD + wallet integration), `routers/users.py` (stub), `routers/voice_events.py`. Swagger UI at `:8000/docs`.

### Voice Service API (`services/voice/src/`)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/voice/synthesize` | Direct text→speech (used by `speak` tool / accept) |
| `POST /api/voice/announce` | Task announcement with LLM text generation |
| `POST /api/voice/announce_with_completion` | Dual voice: announcement + completion |
| `POST /api/voice/feedback/{type}` | Acknowledgment messages |
| `GET /api/voice/rejection/random` | Random pre-generated rejection voice from stock |
| `GET /api/voice/rejection/status` | Rejection stock count / generation status |
| `POST /api/voice/rejection/clear` | Clear and regenerate rejection stock |
| `GET /audio/{filename}` | Serve generated MP3 files |
| `GET /audio/rejections/{filename}` | Serve rejection stock audio files |

VOICEVOX speaker ID 47 (ナースロボ_タイプT). `rejection_stock.py` pre-generates up to 100 rejection voices during idle time (LLM text gen + VOICEVOX synthesis).

### Wallet Service API (`services/wallet/src/`)

Double-entry credit ledger with PostgreSQL (asyncpg). Key models: `Wallet` (balance), `LedgerEntry` (debit/credit pairs), `Device` (XP tracking), `SupplyStats`.

Routers: `routers/wallets.py` (balance/create), `routers/transactions.py` (history/task reward), `routers/devices.py` (device registration), `routers/admin.py` (supply stats). `services/xp_scorer.py` handles dynamic reward multiplier (1.0x-3.0x based on device XP). Swagger UI at `:8003/docs`.

### Mock Infrastructure (`infra/`)

- `mock_llm/` — Keyword-based LLM simulator (FastAPI, OpenAI-compatible). Dual-mode: when `tools` present in request → generates tool calls (Brain mode); when absent → generates natural text (Voice text gen mode). Matches temperature/CO2/supply keywords → tool calls
- `virtual_edge/` — Virtual ESP32 device emulator for testing without hardware
- `virtual_camera/` — RTSP server (mediamtx + ffmpeg) for virtual camera feed
- `docker-compose.edge-mock.yml` — Lightweight compose for virtual-edge + mock-llm + virtual-camera

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt >=2.0, Pydantic 2.x, loguru
- **Frontend**: React 19, TypeScript, Vite 7, Tailwind CSS 4, Framer Motion, Lucide icons
- **ML/Vision**: Ultralytics YOLOv11 (yolo11s.pt + yolo11s-pose.pt), OpenCV, PyTorch (ROCm)
- **LLM**: Ollama with ROCm for AMD GPUs (Qwen2.5 target model)
- **TTS**: VOICEVOX (Japanese speech synthesis)
- **Edge**: MicroPython on ESP32 (BME680, MH-Z19 CO2, DHT22), PlatformIO C++ for camera nodes
- **Infra**: Docker Compose, Mosquitto MQTT, PostgreSQL 16 (asyncpg) / SQLite (aiosqlite fallback), nginx

## Code Conventions

- All Python I/O uses `async/await` (asyncio event loop)
- Configuration via environment variables (`.env` file, `python-dotenv`)
- LLM tools follow OpenAI function-calling schema with explicit `parameters.properties` and `required` fields
- Source code is bind-mounted into containers (`volumes: - ../services/X/src:/app`), so changes take effect on container restart without rebuild
- Documentation is bilingual (English code/comments, Japanese deployment docs and tool descriptions)
- Perception monitors are YAML-configured (`services/perception/config/monitors.yaml`), not hardcoded
- Logging uses `loguru` (brain, voice, perception) and standard `logging` (world_model)

## Parallel Development

When working as one of multiple concurrent Claude Code workers, read these documents BEFORE starting:

- `docs/parallel-dev/WORKER_GUIDE.md` — Lane definitions, file ownership, git workflow
- `docs/parallel-dev/API_CONTRACTS.md` — Inter-service API contracts and mocking guidance

### Worktree (必須)

並行開発では **git worktree** を使用する。メインディレクトリ (`Office_as_AI_ToyBox`) で `git checkout` を実行してはならない。

```
/home/sin/code/Office_as_AI_ToyBox     → main (監視・統合専用)
/home/sin/code/soms-worktrees/L{N}     → lane/L{N}-* (各ワーカーの作業用)
```

ワーカー起動時は自分のレーンの worktree パスを working directory に指定すること。

## Environment Configuration

Key variables in `.env` (see `env.example`):

- `LLM_API_URL` — `http://mock-llm:8000/v1` (dev) or `http://ollama:11434/v1` (Docker内部) or `http://host.docker.internal:11434/v1` (ホストOllama)
- `LLM_MODEL` — Model name for Ollama (e.g. `qwen2.5:14b`)
- `MQTT_BROKER` / `MQTT_PORT` — Broker address (default: `mosquitto:1883`)
- `DATABASE_URL` — `postgresql+asyncpg://user:pass@postgres:5432/soms` (Docker) or `sqlite+aiosqlite:///./soms.db` (fallback)
- `POSTGRES_USER` / `POSTGRES_PASSWORD` — PostgreSQL credentials (default: `soms` / `soms_dev_password`)
- `RTSP_URL` — Camera feed URL (dev: `rtsp://virtual-camera:8554/live`)
- `TZ` — Timezone (default: `Asia/Tokyo`)
- `HSA_OVERRIDE_GFX_VERSION` — AMD GPU compatibility override (e.g. `12.0.1` for RDNA4)
