# SOMS — 都市をAI化するアーキテクチャの実証

**Symbiotic Office Management System**

分散型ローカルLLMによる自律的空間管理。1つのオフィスから都市全体へスケールする Core Hub アーキテクチャの Phase 0 実装。

センサーデータとカメラ映像をもとにローカルLLMがリアルタイムで自律判断し、APIで操作できない物理タスクは人間に経済的インセンティブで委託する。全処理がGPUサーバー1台で完結し、生データは一切クラウドに送信しない (50,000:1 のデータ圧縮)。

## Core Hub ビジョン

```
                      ┌──────────────────┐
                      │   City Data Hub  │ 集約統計のみ受信 (~1MB/Hub/日)
                      └────────┬─────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
        │  Office   │   │   Farm    │   │  Public   │
        │  Hub      │   │   Hub     │   │  Facility │
        │  (SOMS)◄──┤   │           │   │           │
        └───────────┘   └───────────┘   └───────────┘
         Phase 0 実装     同一アーキテクチャ、異なるプロンプトとセンサー
```

各 Core Hub は独立したローカルLLM+GPUを持ち、ネットワーク切断時も自律動作を継続する。システムプロンプト（行動原則）とセンサー構成の差し替えでオフィス・農場・店舗・公共施設に展開可能。

## Phase 0 アーキテクチャ (SOMS)

```
                ┌──────────────────┐
                │   Ollama / LLM   │
                │  (qwen2.5:14b)   │
                └────────┬─────────┘
                         │ OpenAI API
                ┌────────┴─────────┐
                │   Brain Service   │
                │  ReAct Loop (5x)  │
                │  WorldModel       │
                │  TaskScheduling   │
                └──┬───┬───┬───┬───┘
                   │   │   │   │
        ┌──────────┘   │   │   └──────────┐
        ▼              ▼   ▼              ▼
┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│ MQTT Broker  │ │  Dashboard  │ │Voice Service │
│ (Mosquitto)  │ │  Backend    │ │  + VOICEVOX  │
└──┬───┬───────┘ │  (FastAPI)  │ └──────────────┘
   │   │         └──────┬──────┘
   │   │                │
   │   │         ┌──────┴──────┐
   │   │         │  Dashboard  │
   │   │         │  Frontend   │◄── nginx ──► Wallet
   │   │         │  (React 19) │              Service
   │   │         └─────────────┘
   │   │
   │   └─────────────────┐
   ▼                     ▼
┌──────────────┐  ┌──────────────┐
│ Edge Devices │  │  Perception  │
│ SensorSwarm  │  │  YOLOv11     │
│ Hub + Leaf   │  │  Monitors    │
│ MCP/JSON-RPC │  │  (ROCm GPU)  │
└──────────────┘  └──────────────┘
```

### レイヤー構成

| Layer | Directory | Description |
|-------|-----------|-------------|
| Central Intelligence | `services/brain/` | LLM-driven ReAct 認知ループ (Think→Act→Observe, 5ツール, 3層安全機構) |
| Perception | `services/perception/` | YOLOv11 — 在室検知, ホワイトボード, 活動分析 (4層姿勢バッファ) |
| Communication | MQTT (Mosquitto) | MCP over MQTT — JSON-RPC 2.0 でエッジデバイスを直接制御 |
| Edge | `edge/` | SensorSwarm Hub-Leaf 2層ネットワーク (ESP-NOW/UART/I2C/BLE) |
| Human Interface | `services/dashboard/`, `services/voice/` | キオスクダッシュボード + VOICEVOX 音声合成 + モバイルウォレットPWA |
| Economy | `services/wallet/` | 複式簿記クレジット台帳 (デバイスXP, デマレッジ2%/日, 焼却5%) |

## Services

| Service | Port | Container |
|---------|------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 8003 | soms-wallet |
| PostgreSQL | 5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 | soms-mqtt |

## Quick Start

```bash
# 1. Clone and configure
git clone <repository_url>
cd Office_as_AI_ToyBox
cp env.example .env

# 2. Full simulation (no GPU/hardware required)
./infra/scripts/start_virtual_edge.sh

# 3. Production (AMD ROCm GPU + real hardware)
docker compose -f infra/docker-compose.yml up -d --build
```

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed setup. See [CITY_SCALE_VISION.md](docs/CITY_SCALE_VISION.md) for urban-scale architecture.

## Directory Structure

```
├── docs/
│   ├── CITY_SCALE_VISION.md   Urban AI architecture & roadmap
│   ├── SYSTEM_OVERVIEW.md     Technical specification
│   └── promo/                 Pitch decks, articles, design assets
├── infra/             Docker Compose, Mosquitto, mock LLM, virtual edge/camera
├── services/
│   ├── brain/         LLM decision engine (ReAct loop, WorldModel, task scheduling)
│   ├── dashboard/     Frontend (React 19 + Vite) + Backend (FastAPI + PostgreSQL)
│   ├── perception/    YOLOv11 vision system (pluggable monitors, camera discovery)
│   ├── voice/         VOICEVOX voice synthesis + LLM text generation
│   ├── wallet/        Double-entry credit ledger + device XP + demurrage
│   └── wallet-app/    Mobile PWA (balance, QR scan, P2P transfer, history)
├── edge/
│   ├── office/        Production MicroPython firmware (BME680, MH-Z19C)
│   ├── swarm/         SensorSwarm Hub + Leaf firmware (ESP-NOW, UART, I2C, BLE)
│   ├── lib/           Shared libraries (soms_mcp.py, swarm protocol)
│   ├── test-edge/     PlatformIO C++ firmware (camera/sensor nodes)
│   └── tools/         Diagnostic scripts
├── config/            Perception monitors YAML config
└── CLAUDE.md          Developer reference (architecture, APIs, conventions)
```

## Tech Stack

- **LLM**: Ollama + Qwen2.5:14b (ROCm, AMD GPU)
- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL 16 (asyncpg) / SQLite fallback
- **Frontend**: React 19, TypeScript, Vite 7, Tailwind CSS 4, Framer Motion
- **Vision**: YOLOv11 (yolo11s.pt + yolo11s-pose.pt), OpenCV, PyTorch (ROCm)
- **TTS**: VOICEVOX (Japanese, Speaker ID 47)
- **Edge**: ESP32 MicroPython + SensorSwarm (Hub-Leaf, binary protocol) + PlatformIO C++
- **Economy**: Double-entry ledger, demurrage 2%/day, 5% burn, device XP multiplier
- **Infra**: Docker Compose (11 services), Mosquitto MQTT, nginx

Python + MQTT による純粋なイベント駆動アーキテクチャ。重量級ミドルウェア不使用。

## Testing

```bash
# E2E integration test (7 scenarios)
python3 infra/scripts/e2e_full_test.py

# Individual tests
python3 infra/scripts/integration_test_mock.py
python3 infra/scripts/test_task_scheduling.py
python3 infra/scripts/test_world_model.py
python3 infra/scripts/test_wallet_integration.py
python3 infra/scripts/test_demurrage.py
```

## License

See LICENSE file.
