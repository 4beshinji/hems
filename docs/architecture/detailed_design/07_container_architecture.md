# 07. Containerization & Orchestration

## 1. Strategy
The system uses **Docker Compose** for container orchestration. All dependencies (ROCm drivers, Python libraries, system tools) are encapsulated into reproducible images. Source code is bind-mounted for development (changes take effect on container restart without rebuild).

## 2. Container Service Architecture

### 2.1 Main Compose (`infra/docker-compose.yml`)

| Service | Base Image | Container | Port | Role | Resources |
|---------|-----------|-----------|------|------|-----------|
| `mosquitto` | `eclipse-mosquitto:latest` | soms-mqtt | 1883, 9001 | MQTT Broker | Low |
| `brain` | Custom (Python 3.11) | soms-brain | — | LLM Cognitive Loop | CPU |
| `postgres` | `postgres:16-alpine` | soms-postgres | 5432 | Shared Database | Low |
| `backend` | Custom (Python 3.11) | soms-backend | 8000 | Dashboard API | CPU |
| `frontend` | Custom (nginx + Vite build) | soms-frontend | 80 | React SPA + Reverse Proxy | Low |
| `voicevox` | Custom (VOICEVOX CPU) | soms-voicevox | 50021 | Japanese TTS Engine | CPU |
| `voice-service` | Custom (Python 3.11) | soms-voice | 8002 | Voice API + LLM Text Gen | CPU |
| `wallet` | Custom (Python 3.11) | soms-wallet | 8003 | Credit Ledger | CPU |
| `ollama` | `ollama/ollama:rocm` | soms-ollama | 11434 | LLM Inference | **GPU** |
| `mock-llm` | Custom (Python 3.11) | soms-mock-llm | 8001 | Test LLM Simulator | CPU |
| `perception` | Custom (PyTorch ROCm) | soms-perception | host | YOLOv11 Vision | **GPU** |

### 2.2 Edge Mock Compose (`infra/docker-compose.edge-mock.yml`)

| Service | Role |
|---------|------|
| `virtual-edge` | SwarmHub + 3 Leaf emulator |
| `mock-llm` | Keyword-based LLM simulator |
| `virtual-camera` | mediamtx + ffmpeg RTSP server |

## 3. Service Dependencies

```
mosquitto ─────────────────────────────────────────────────────────
    ↑                    ↑           ↑              ↑
    │                    │           │              │
  brain ──→ backend ──→ postgres ←── wallet     perception
    │          ↑                                (host network)
    │          │
    ├──→ voice-service ──→ voicevox
    │
    └──→ ollama (or mock-llm)

  frontend (nginx) ──→ backend, voice-service, wallet
```

### Startup Order (`depends_on`)
1. `mosquitto` (no deps)
2. `postgres` (no deps)
3. `backend` (mosquitto, postgres)
4. `wallet` (postgres, mosquitto)
5. `voicevox` (no deps)
6. `voice-service` (voicevox)
7. `brain` (mosquitto)
8. `frontend` (backend)
9. `ollama`, `mock-llm`, `perception` (independent)

## 4. GPU Passthrough (AMD ROCm)

### Device Mapping
```yaml
ollama:
  devices:
    - /dev/kfd:/dev/kfd                     # AMD Kernel Fusion Driver
    - /dev/dri/card1:/dev/dri/card1         # dGPU render node
    - /dev/dri/renderD128:/dev/dri/renderD128
  environment:
    - HSA_OVERRIDE_GFX_VERSION=12.0.1       # RDNA4 compatibility
```

**Critical**: Do NOT pass `/dev/dri` (entire directory). This maps both dGPU and iGPU, causing the iGPU to reset and crashing the GNOME desktop. Always map specific device nodes.

### GPU Assignment
| Device | Path | Purpose |
|--------|------|---------|
| dGPU (RX 9700) | card1, renderD128 | ROCm compute (Ollama, Perception) |
| iGPU (Raphael) | card2, renderD129 | Display only — never pass to Docker |

### Perception Special Case
```yaml
perception:
  network_mode: host          # Direct camera RTSP access
  devices:
    - /dev/kfd:/dev/kfd
    - /dev/dri/card1:/dev/dri/card1
    - /dev/dri/renderD128:/dev/dri/renderD128
  group_add:
    - video
  security_opt:
    - seccomp:unconfined
```

`network_mode: host` is used for direct RTSP camera access. This means Perception cannot use the `soms-net` Docker network — it connects to MQTT via `localhost:1883`.

## 5. Volume Strategy

| Volume | Mounted By | Purpose |
|--------|-----------|---------|
| `soms_mqtt_data` | mosquitto | MQTT persistence |
| `soms_mqtt_log` | mosquitto | MQTT logs |
| `soms_pg_data` | postgres | PostgreSQL data |
| `soms_audio_data` | voice-service | Generated audio files |
| `ollama_models` | ollama | Model weights |
| `soms_db_data` | (legacy) | SQLite — no longer used, should be removed |

### Source Code Bind Mounts
All Python services bind-mount their source for development:
```yaml
volumes:
  - ../services/brain/src:/app
  - ../services/dashboard/backend:/app
  - ../services/voice/src:/app
  - ../services/wallet/src:/app
```

Changes take effect on container restart without rebuild.

## 6. Network Topology

### Internal Network (`soms-net`)
All services except Perception communicate on the `soms-net` bridge network.

### Host-Exposed Ports

| Service | Port | Binding | Purpose |
|---------|------|---------|---------|
| mosquitto | 1883 | `${MQTT_BIND_ADDR:-0.0.0.0}:1883` | Edge device MQTT access |
| mosquitto | 9001 | `${MQTT_BIND_ADDR:-0.0.0.0}:9001` | WebSocket |
| frontend | 80 | `0.0.0.0:80` | Dashboard + reverse proxy |
| backend | 8000 | `0.0.0.0:8000` | API direct access |
| mock-llm | 8001 | `0.0.0.0:8001` | Mock LLM direct access |
| voice-service | 8002 | `0.0.0.0:8002` | Voice API direct access |
| wallet | 8003 | `0.0.0.0:8003` | Wallet API direct access |
| postgres | 5432 | `0.0.0.0:5432` | DB direct access |
| voicevox | 50021 | `0.0.0.0:50021` | VOICEVOX direct access |
| ollama | 11434 | `0.0.0.0:11434` | LLM API direct access |

**Security note** (M-1): PostgreSQL and Wallet ports should be restricted to `127.0.0.1` in production.

### Host Docker Bridge
Brain and Voice Service use `extra_hosts: host.docker.internal:host-gateway` to reach host-running Ollama when `LLM_API_URL=http://host.docker.internal:11434/v1`.

## 7. Build & Deployment

### Development
```bash
# Full simulation
./infra/scripts/start_virtual_edge.sh

# Production
docker compose -f infra/docker-compose.yml up -d --build

# Rebuild single service
docker compose -f infra/docker-compose.yml up -d --build brain
```

### Migration
1. Copy `docker-compose.yml`, `.env`, and source directories.
2. Copy named volumes (PostgreSQL data, Ollama models, audio).
3. Run `docker compose up -d`.

## 8. Known Issues

| ID | Issue | Impact |
|----|-------|--------|
| M-1 | PostgreSQL port on all interfaces | Security risk |
| M-5 | Perception `network_mode: host` conflicts with custom network | Service discovery issue |
| M-8 | Unused `soms_db_data` volume (SQLite legacy) | Confusion |
| M-9 | Wallet port unnecessarily exposed | Security risk |
| M-10 | Frontend missing `.dockerignore` | Image bloat |
| M-11 | Edge mock compose missing network definition | Implicit default network |
| L-1 | Perception uses floating `rocm/pytorch:latest` tag | Build reproducibility |
| L-2 | Unnecessary `build-essential` in Python service Dockerfiles | +90MB image size |
| L-7 | No Docker healthchecks defined | Failure detection difficulty |

See `ISSUES.md` for complete issue tracking.
