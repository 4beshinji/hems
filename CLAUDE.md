# CLAUDE.md

## Project Overview

**HEMS (Home Environment Management System)** — a personal life management system for a single occupant, forked from SOMS (Symbiotic Office Management System). Combines an LLM "brain" with IoT sensors, plugin-based voice synthesis, and a VRM 3D avatar system. The AI has a configurable character personality (YAML-based) and makes real-time decisions about the home environment using sensor data, biometrics, and schedule information.

Forked from SOMS commit `1216952` (2026-02-16).

## Documentation Map

このリポジトリのドキュメントは**グラフ構造**を取る。本ファイルはオリエンテーション・ハブで、概要 + ポインタのみを持つ。各事実の詳細(canonical home)は下表を参照。全 doc の詳細インデックスは [`docs/README.md`](docs/README.md)。

| Tier | 読み込み | ノード | 役割 |
|---|---|---|---|
| 0 | 常時 | `CLAUDE.md`(本ファイル) / [`README.md`](README.md) | オリエンテーション / ユーザー向け紹介 |
| 1 | service dir で auto-load | [`services/brain/CLAUDE.md`](services/brain/CLAUDE.md) / [`services/voice/CLAUDE.md`](services/voice/CLAUDE.md) / [`services/perception/CLAUDE.md`](services/perception/CLAUDE.md) / [`services/backend/CLAUDE.md`](services/backend/CLAUDE.md) | サービス固有 canonical |
| 2 | on-demand | [`docs/IMPLEMENTATION_MAP.md`](docs/IMPLEMENTATION_MAP.md)(SoT)/ [`docs/CLAUDE-bridges.md`](docs/CLAUDE-bridges.md)(11 ブリッジ)/ [`docs/wiring-gap-06-data-flow-consolidation.md`](docs/wiring-gap-06-data-flow-consolidation.md)(ロードマップ) | 横断リファレンス |
| 3-4 | 人間向け | setup/運用・計画・監査ガイド群 | [`docs/README.md`](docs/README.md) に一覧 |

どこを見るか:

- **Brain の内部構造・subsystem・tool 一覧** → `services/brain/CLAUDE.md`
- **ブリッジ統合**(OpenClaw / GAS / Obsidian / HA / biometric / Tapo / Zigbee / SwitchBot / weather / news / knowledge) → `docs/CLAUDE-bridges.md`
- **Device Registry / Shopping / Chat バックエンド** → `services/backend/CLAUDE.md`
- **正確な code↔compose↔MQTT↔tools↔env マッピング** → `docs/IMPLEMENTATION_MAP.md`

## Build & Run Commands

All services run via Docker Compose from the `infra/` directory.

```bash
# Initial setup
cp env.example .env
cd infra
docker compose --profile bootstrap build base   # build hems-base:py3.11 (one time, all Python services FROM it)
docker compose up -d --build

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

# With OpenClaw (PC metrics + service monitor; legacy localcraw build context)
docker compose --profile openclaw up -d --build

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

# With Tapo P110/P115 (direct LAN, python-kasa, no HA required)
docker compose --profile tapo up -d --build

# With Zigbee2MQTT (requires Zigbee USB coordinator stick)
docker compose --profile zigbee up -d --build

# With news briefing (RSS + Ollama summarizer, requires --profile ollama)
docker compose --profile news --profile ollama up -d --build

# With knowledge ingestion (multi-format document loader)
docker compose --profile knowledge up -d --build

# With STT (Speech-to-Text, push-to-talk + VAD auto mode)
docker compose --profile stt up -d --build

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
Optional profiles: `mock`, `voicevox`, `ollama`, `postgres`, `openclaw`, `localcraw` (legacy alias), `obsidian`, `gas`, `ha`, `biometric`, `perception`, `switchbot`, `tapo`, `zigbee`, `news`, `knowledge`, `stt`

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
| GAS Bridge | 8015 | `HEMS_PORT_GAS_BRIDGE` | hems-gas-bridge |
| HA Bridge | 8016 | `HEMS_PORT_HA_BRIDGE` | hems-ha-bridge |
| Biometric Bridge | 8017 | `HEMS_PORT_BIOMETRIC_BRIDGE` | hems-biometric-bridge |
| Perception | 8018 | `HEMS_PORT_PERCEPTION` | hems-perception |
| SwitchBot Bridge | 8019 | `HEMS_PORT_SWITCHBOT_BRIDGE` | hems-switchbot-bridge |
| Tapo Bridge | 8020 | `HEMS_PORT_TAPO_BRIDGE` | hems-tapo-bridge |
| News Bridge | 8021 | `HEMS_PORT_NEWS_BRIDGE` | hems-news-bridge |
| Knowledge Bridge | 8022 | `HEMS_PORT_KNOWLEDGE_BRIDGE` | hems-knowledge-bridge |
| STT Service | 8023 | `HEMS_PORT_STT` | hems-stt |
| VOICEVOX | 50031 | `HEMS_PORT_VOICEVOX` | hems-voicevox |
| Ollama | 11444 | `HEMS_PORT_OLLAMA` | hems-ollama |
| PostgreSQL | 5442 | `HEMS_PORT_POSTGRES` | hems-postgres |
| MQTT | 1893 | `HEMS_PORT_MQTT` | hems-mqtt |

### MQTT Topics

プレフィックス規約のみ(全トピックツリーは [`docs/IMPLEMENTATION_MAP.md`](docs/IMPLEMENTATION_MAP.md) §4.0、ブリッジ別の詳細は [`docs/CLAUDE-bridges.md`](docs/CLAUDE-bridges.md)):

- `office/{zone}/{device_type}/{device_id}/{channel}` — 物理センサ telemetry + camera/activity(perception)
- `hems/pc/*` ・ `hems/services/{name}/*` — PC メトリクス / サービスモニタ(OpenClaw)
- `hems/home/{zone}/{domain}/{entity_id}/state` — smart home(HA)
- `hems/personal/{notes,biometrics,knowledge}/*` — Obsidian / biometric / knowledge
- `hems/gas/{calendar,tasks,gmail,sheets,drive}/*` — Google(GAS)
- `hems/{weather,news,shopping}/*` ・ `hems/perception/vlm/*` — weather / news / shopping / VLM
- `hems/{tapo,switchbot}/*` ・ `zigbee2mqtt/*` — direct device bridges
- `hems/<service>/bridge/status` — 各ブリッジ接続状態
- `hems/brain/{reload-character,guest-mode}` — Brain 制御

### Brain Service

ReAct 認知ループ(30s サイクル, 最大 5 iteration)。LLM + rule-based の dual mode(GPU 高負荷 / low-power / VLM heavy-swap 時に rule-based へ fallback)。Character は 2 段分離(Stage 1 raw 思考 → Stage 2 PersonaRewriter 出力)。Tri-domain world model(Physical / Digital / User State)+ event store data mart(SOMS 互換, 730d retention)。Alert suppression / Ambient Speaker あり。

subsystem 一覧(PowerModeManager / LLMRouter / BootLoadManager / SunriseAlarm / ScheduleLearner / TimelineGenerator / EventAutomation / AutomationEngine / SceneExecutor / DeviceDispatcher / TaskQueueManager / PersonaRewriter / Annotators / MotionRetriever 等)、always-on / profile-gated tool の全一覧、Chat brain server、Event Automation は **canonical: [`services/brain/CLAUDE.md`](services/brain/CLAUDE.md)**(該当 dir で auto-load)。tool 定義 ↔ dispatch の整合は `docs/IMPLEMENTATION_MAP.md` §3。

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

Templates: `default` (default), `ena`, `tsundere`, `gentle-senpai`, `butler`, `nurserobo-typet`
Validator: `python validate_character.py config/character.yaml`
         `python validate_character.py --all`   # validate all templates
         `python validate_character.py --list`  # list available templates

VRM avatar / animation の詳細は [`docs/avatar-setup.md`](docs/avatar-setup.md)、TTS backend(VoiSona 等)は [`docs/voisona-talk-setup.md`](docs/voisona-talk-setup.md) と `services/voice/CLAUDE.md`。

### Database

- Default: SQLite (`aiosqlite`) — zero config
- Optional: PostgreSQL 16 (`--profile postgres`)
- Backend: Task, User, VoiceEvent, SystemStats, ShoppingItem, PurchaseHistory
- Brain event_store: raw_events, llm_decisions, hourly_aggregates (SOMS-compatible)
- Retention: 730 days (2 years) for raw_events and llm_decisions

### Integrations

各統合の deep-dive は canonical doc に集約。ブリッジ群は [`docs/CLAUDE-bridges.md`](docs/CLAUDE-bridges.md)、heavy service は per-service CLAUDE.md(該当 dir で auto-load)。各 profile の起動コマンドは Build & Run、port は Service Ports 表を参照。

| 統合 | profile | port | canonical doc |
|---|---|---|---|
| OpenClaw(PC metrics + desktop) | `openclaw` (`localcraw` legacy alias) | 8013 | `docs/CLAUDE-bridges.md` |
| GAS(Calendar/Tasks/Gmail/Sheets/Drive) | `gas` | 8015 | `docs/CLAUDE-bridges.md` |
| Obsidian(knowledge store) | `obsidian` | 8014 | `docs/CLAUDE-bridges.md` |
| Home Assistant(smart home) | `ha` | 8016 | `docs/CLAUDE-bridges.md` |
| Biometric(smartband) | `biometric` | 8017 | `docs/CLAUDE-bridges.md` |
| Tapo(P110/P115 直 LAN) | `tapo` | 8020 | `docs/CLAUDE-bridges.md` |
| Zigbee2MQTT | `zigbee` | — | `docs/CLAUDE-bridges.md` |
| SwitchBot(直 API) | `switchbot` | 8019 | `docs/CLAUDE-bridges.md` |
| Weather(JMA/OWM) | always-on | — | `docs/CLAUDE-bridges.md` |
| News(RSS + Ollama) | `news` | 8021 | `docs/CLAUDE-bridges.md` |
| Knowledge(multi-format ingest) | `knowledge` | 8022 | `docs/CLAUDE-bridges.md` |
| Perception(YOLOv11s-pose + VLM) | `perception` | 8018 | `services/perception/CLAUDE.md` |
| Voice TTS / STT | `voicevox` / `stt` | 8012 / 8023 | `services/voice/CLAUDE.md` |
| Event Automation | (news/gas) | — | `services/brain/CLAUDE.md` + [`docs/event-automation.md`](docs/event-automation.md) |

setup 手順(HA/SwitchBot 配線・smartband ペアリング・avatar・VoiSona 等)は [`docs/README.md`](docs/README.md) Tier 3 を参照。

### Device Registry / Shopping / Chat

全センサー/アクチュエータを単一 `Device` テーブルで管理(vendor は属性: zigbee/switchbot/tapo/ha/mcp)。Brain が MQTT を監視し未知 device を `/devices/heartbeat` で自動登録、`purpose` フィールドを LLM のツール選択に活用。Shopping List と Chat REST router も backend 側にある。

詳細(Device Registry CRUD・Safety・Shopping models・Chat router)→ **[`services/backend/CLAUDE.md`](services/backend/CLAUDE.md)**。ベンダー非依存の device tool(`control_actuator` / `list_devices` / `describe_device`)と dispatcher は `services/brain/CLAUDE.md`。

## Implementation Status & Source-of-Truth Map

For exact mapping between code, docker-compose, MQTT topics, world model fields, brain tools, and env vars, see **[`docs/IMPLEMENTATION_MAP.md`](docs/IMPLEMENTATION_MAP.md)**. That doc is the authoritative cross-reference and includes verification commands. When adding a new service / tool / topic, update in order: **IMPLEMENTATION_MAP → the canonical doc (`docs/CLAUDE-bridges.md` or `services/*/CLAUDE.md`) → the Integrations table above → [`docs/README.md`](docs/README.md)**, then `env.example`.

詳細な配線ギャップ分析と Wave 計画は [`docs/wiring-gap-06-data-flow-consolidation.md`](docs/wiring-gap-06-data-flow-consolidation.md) を参照(gap-01..05 は統合・supersede 済)。技術的負債の最新監査と実行計画は [`docs/audit/2026-06-11/SUMMARY.md`](docs/audit/2026-06-11/SUMMARY.md) → [`docs/refactor/2026-06-11/PLAN.md`](docs/refactor/2026-06-11/PLAN.md)(2026-05-25 の deferred 9 行を継承)。

### Known orphans / wiring gaps (2026-06-11)

- **`services/data-bridge/`** — Phase-2 scaffold (placeholder for future Strava/Fitbit/Garmin/Intervals.icu intake). `src/bridges/` empty, no compose entry. Topics under `hems/personal/calendar`, `hems/personal/training/fitness`, `hems/system/gpu/utilization` are documented but never published. Currently substituted by biometric-bridge + gas-bridge. **存続・実装決定(2026-06-11)** — Strava/Fitbit 連携として共通ブリッジ基盤(refactor/2026-06-11 PLAN W3.1)完了後に着手。
- **`services/mobile-android/` / `apps/healthconnect-companion/`** — compose 非参照の Android プロジェクト。リポジトリ内での位置づけ未文書化。
- **`hems/services/{name}/event`** — edge events arrive but only the next 30s cycle picks them up; no immediate-trigger path.
- **`hems/gas/sheets/{name}` / `hems/gas/drive/recent`** — flow into world_model but no rules / event-automation actions consume them yet.
- **`*/bridge/status`** — only `bridge_connected` flag is updated; outage history is not retained. また status topic は規約 `hems/<service>/bridge/status` に対し実装がばらつき、gas/weather/news/knowledge は未発行。
- 解消済: ~~`services/weather-bridge/`~~(always-on 配線済)。

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy (async), paho-mqtt, Pydantic 2.x
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Framer Motion
- **3D Avatar**: Three.js, React Three Fiber, @pixiv/three-vrm
- **LLM**: OpenAI / Anthropic / Ollama (multi-provider)
- **TTS**: Plugin-based (espeak-ng, VOICEVOX, Edge TTS, VoiSona Talk)
- **Infra**: Docker Compose, Mosquitto MQTT, SQLite / PostgreSQL

## Code Conventions

- All Python I/O uses `async/await`
- Configuration via environment variables (`.env`)
- Source code bind-mounted into containers (changes take effect on restart)
- Bilingual: English code/comments, Japanese UI/voice/docs

## Key Differences from SOMS

| SOMS | HEMS |
|------|------|
| PostgreSQL required | SQLite default |
| Wallet (double-entry ledger) | No points system |
| VOICEVOX only | Plugin TTS (5 backends: voisona / voicevox / espeak / edge-tts / aivoice) |
| Hardcoded personality | YAML character system (2-stage thinking/output separation) |
| Ollama only | OpenAI / Anthropic / Ollama (multi-provider via LLMRouter) |
| 11 services | 5 core (mosquitto/brain/backend/frontend/voice-service) + 16 optional profiles |
| Office/multi-user | Home/single occupant |
| No alert suppression | Alert suppression (30min/10min) |
| npm | pnpm |
