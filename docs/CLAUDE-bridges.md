# Bridge integrations (HEMS)

Detail reference for the 11 bridge integrations. Not auto-loaded — referenced from `hems/CLAUDE.md`. Read on demand when working on or adjacent to a specific bridge.

For service-specific Claude context that DOES auto-load when in the dir, see:
- `services/brain/CLAUDE.md`
- `services/voice/CLAUDE.md`
- `services/perception/CLAUDE.md`

The bridges below mostly live under `services/<name>-bridge/`. They lack per-service CLAUDE.md to avoid file sprawl — this single doc is the consolidated reference.

---

## OpenClaw Integration (PC Metrics + Desktop Control)

PC metrics collection and desktop control. Node.js + systeminformation で直接ホスト計測し、Playwright 内蔵ブラウザ制御を提供する。現在の compose service は互換のため `localcraw-bridge` のままだが、運用名は OpenClaw。

- **openclaw-bridge**: Docker DNS alias / container `hems-openclaw-bridge` (Node.js) running on host PID namespace
  - Compose service key is still `localcraw-bridge`, built from legacy external repo `../localcraw`
  - Polls PC metrics (CPU, memory, GPU, disk, temperatures) every 10s via systeminformation
  - Publishes to `hems/pc/*` MQTT topics
  - REST API for brain tools to execute commands, send notifications, control browser
- **Deploy**: ホストプロセス不要 — `pid:host` + `/proc` `/sys` マウントで直接取得
- **Profile**: `docker compose --profile openclaw up -d --build` (`localcraw` is a legacy alias)
- **Brain tools**: `get_pc_status`, `run_pc_command` (with dangerous command blocklist), `control_browser`, `send_pc_notification`, `get_service_status` (Gmail/GitHub/browser checker), `list_processes` (CPU/メモリでソート)
- **Safety**: Destructive commands (`rm -rf /`, `mkfs`, `shutdown`, etc.) are blocked by sanitizer

Bridge supplementary detail:

- PC metrics: CPU / memory / GPU / disk / top processes → `hems/pc/*`
- Service monitor: Gmail (IMAP), GitHub (REST API), browser-based checkers (Playwright内蔵) → `hems/services/*`
- Edge-triggered events: unread count increases fire MQTT events for immediate LLM response

Configure in `.env`:
```bash
OPENCLAW_BRIDGE_URL=http://openclaw-bridge:8000
# Legacy alias still accepted:
# LOCALCRAW_BRIDGE_URL=http://localcraw-bridge:8000
HEMS_GMAIL_ENABLED=true
HEMS_GMAIL_EMAIL=user@gmail.com
HEMS_GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
HEMS_GITHUB_ENABLED=true
HEMS_GITHUB_TOKEN=ghp_xxxx
```

---

## GAS Integration (Google Apps Script)

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
- **Brain tools**: `get_recent_emails` (Gmail スレッド一覧), `gas_query_free_slots` (空き時間), `gas_query_sheet` (Sheets 値クエリ)
- **Brain rules**: meeting reminders, morning briefing, evening summary, overdue alerts, task sync, unread Gmail alerts, etc.
- **GAS Quota**: ~1,100 calls/day with defaults (quota limit: 20,000/day)

---

## Obsidian Integration (Knowledge Store)

Connects Obsidian vault to HEMS Brain for bidirectional knowledge access.

- **obsidian-bridge**: Docker service with watchdog file monitoring
  - Indexes vault `.md` files with TF-IDF keyword search
  - Watches for file changes, publishes to `hems/personal/notes/*` MQTT topics
  - REST API for search, read, write operations
- **Deploy**: Mount vault directory, bridge indexes on startup
- **Profile**: `docker compose --profile obsidian up -d --build`
- **Brain tools**: `search_notes` (vault search), `write_note` (HEMS/ directory only), `get_recent_notes`, `list_note_tags` (タグ一覧)
- **Writeback**: Decision logs (`HEMS/decisions/`) and learning memos (`HEMS/learnings/`) auto-generated
- **Token budget**: Only metadata in LLM context (~30 tokens); full content via on-demand `search_notes`
- **Safety**: Write restricted to `HEMS/` subdirectory, path traversal blocked, 10000 char limit

---

## Home Assistant Integration (Smart Home)

Connects Home Assistant to HEMS for smart home device control and life automation.

- **ha-bridge**: Docker service connecting to HA via REST/WebSocket API
  - WebSocket: real-time `state_changed` events → MQTT publish
  - REST API: Brain tool calls → HA service calls
  - Polling fallback: 30s interval when WebSocket disconnects
  - Publishes to `hems/home/*` MQTT topics
- **Deploy**: HA running on host or via Docker, configure `HA_URL` + `HA_TOKEN`
- **Profile**: `docker compose --profile ha up -d --build`
- **Brain tools**: `control_light`, `control_climate`, `control_cover`, `get_home_devices`, `control_switch`, `get_sensor_data`, `execute_scene`, `get_entity_status` (単一エンティティ状態)
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

---

## Biometric Integration (Smartband)

Tracks heart rate, sleep, activity, stress, and fatigue via smartband/smartwatch (Xiaomi Smart Band, Amazfit, CMF Watch Pro 2) via Health Connect or Huami cloud API.

- **biometric-bridge**: Docker service receiving webhook data from Gadgetbridge app
  - POST webhook endpoint normalizes device data → MQTT publish
  - Fatigue score computation (weighted: HR 30%, sleep 40%, stress 30%)
  - Sleep session caching for daily summaries
  - Publishes to `hems/personal/biometrics/*` MQTT topics
- **Deploy**: Install Gadgetbridge on phone, configure webhook to `http://<host>:8017/api/biometric/webhook`
- **Profile**: `docker compose --profile biometric up -d --build`
- **Brain tools**: `get_biometrics` (current readings), `get_sleep_summary` (last night's sleep), `get_biometric_trend` (履歴トレンド), `get_sleep_history` (睡眠履歴)
- **Brain rules**: 7 rules (high HR/stress/fatigue alerts, sleep quality notification, step goal, sleep detection lights off, fatigue-linked dimming)
- **Thresholds**: HR > 120, HR < 45, SpO2 < 92, Stress > 80 (configurable via env vars)
- **World model**: Tri-domain architecture — biometrics in User State domain, threshold crossing events

Configure in `.env`:
```bash
BIOMETRIC_BRIDGE_URL=http://biometric-bridge:8000
BIOMETRIC_PROVIDER=gadgetbridge
```

---

## Tapo Integration (`--profile tapo`)

Tapo P110/P115 (電力計測対応スマートプラグ) を LAN 経由で直接制御 (HA不要)。

- **tapo-bridge**: Docker サービス (Python/FastAPI, python-kasa 使用)
  - 30秒間隔で全 Tapo デバイスを polling → 電力・電圧・電流・総消費電力を MQTT publish
  - REST API: `POST /api/devices/{ref}/command` (turnOn/turnOff/toggle)
  - Publishes to `hems/tapo/{vendor_ref}/state`
- **Profile**: `docker compose --profile tapo up -d --build`
- **Brain tools**: `control_actuator` 経由 (vendor="tapo") + `get_power_consumption` (瞬時電力 W、device_id 省略で全プラグ並列取得)
- **pulse対応**: ブレイン側で on → sleep → off (水ポンプ等の短時間通電に活用)
- **Device Registry**: `tapo.{vendor_ref}` として自動登録

Configure in `.env`:
```bash
TAPO_USERNAME=<tapo-cloud-email>
TAPO_PASSWORD=<tapo-cloud-password>
TAPO_DEVICES={"plug_desklight":"192.168.1.42","plug_pump":"192.168.1.43"}
TAPO_ZONES={"plug_desklight":"bedroom","plug_pump":"balcony"}
TAPO_NAMES={"plug_desklight":"寝室デスクライト"}
TAPO_BRIDGE_URL=http://tapo-bridge:8000
HEMS_PORT_TAPO_BRIDGE=8020
```

---

## Zigbee2MQTT Integration (`--profile zigbee`)

Zigbee デバイスを公式 Z2M daemon 経由で直接制御 (HA不要)。

- **zigbee2mqtt**: 公式 Docker image (`koenkk/zigbee2mqtt`) — Zigbee USB coordinator stick 必須
  - `zigbee2mqtt/{device}` にデバイス状態、`zigbee2mqtt/bridge/*` に管理情報を publish
  - Brain が `zigbee2mqtt/{device}/set` に publish すれば制御可能
- **Profile**: `docker compose --profile zigbee up -d --build`
- **Brain tools**: `control_actuator` 経由 (vendor="zigbee") — 直接 MQTT publish、`zigbee_permit_join` でペアリング制御
- **Device Registry**: `zigbee.{friendly_name}` として自動登録
- **Admin UI**: `http://localhost:${HEMS_PORT_FRONTEND:-8080}/z2m/` (nginx proxy 経由) または `http://localhost:${HEMS_PORT_Z2M_UI:-8090}/` (直接)
- **Remote permit_join**: `POST /devices/zigbee/permit_join` で Z2M に `zigbee2mqtt/bridge/request/permit_join` publish、`/devices` ページにボタンあり

**Deploy 手順**:
1. (推奨) USB stick を固定名化: `sudo cp infra/udev/99-zigbee.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger` → `.env` に `HEMS_Z2M_USB_DEVICE=/dev/zigbee-coordinator`
2. `docker compose --profile zigbee up -d --build`

**IKEA GRILLPLATS ペアリング** (secret Zigbeeモード):
1. On/Offボタン長押し (10秒) → 工場リセット
2. On/Offを**素早く8回**タップ → Zigbeeモード有効化 (Matter ではなく)
3. `/devices` ページで「Zigbee ペアリング開始」ボタン押下 (または `zigbee_permit_join` LLM tool)
4. ペアリング成功後は On/Off と Power-on behavior のみ (電力計測は非対応 → Matter モード必要)

Configure in `.env`:
```bash
HEMS_Z2M_USB_DEVICE=/dev/ttyUSB0   # or /dev/zigbee-coordinator with udev rule
# HEMS_PORT_Z2M_UI=8090
```

---

## SwitchBot Integration (Direct API)

Controls SwitchBot devices directly via SwitchBot API (HA不要).

- **switchbot-bridge**: Docker service polling SwitchBot Cloud API
  - Device state polling + MQTT publish
  - REST API for brain tool calls → SwitchBot API commands
  - IR remote support via Hub (AC, TV, etc.)
  - Publishes **device/sensor state to `hems/home/{zone}/{domain}/{entity_id}/state`** (HA 互換 — world_model の `_update_home_device` で HA デバイスと統合)。`hems/switchbot/*` は `bridge/status` のみ
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

---

## Weather Integration (weather-bridge)

Weather data from JMA (気象庁, default, no API key) or OpenWeatherMap. Always-on (no profile).

- **weather-bridge**: Service polling weather APIs → MQTT publish
  - Providers: JMA (free, default), OpenWeatherMap
  - Publishes to `hems/weather/{current,forecast,alerts}` MQTT topics
- **Brain consumer**: `_update_weather_state` in world_model + `get_weather` tool
- **Configure**: `WEATHER_PROVIDER=jma`, `JMA_AREA_CODE=130000`, `JMA_DETAIL_CODE=130010` (defaults: 東京都/東京地方). For OpenWeatherMap set `WEATHER_PROVIDER=openweathermap` + `OWM_API_KEY` + `OWM_LAT`/`OWM_LON`.

---

## News Integration (news-bridge)

RSS news fetcher + Ollama summarizer + urgency detection with event-driven voice briefings.

- **news-bridge**: Docker service (Python/FastAPI) polling RSS feeds and generating Ollama-powered summaries
  - Sources: NHK (国内+国際) + BBC World + Guardian World (configurable)
  - Daily summary: generated at configurable time (default 07:30) + on startup
  - Urgent news: 5-minute polling, urgency score 0.8+ triggers MQTT alert
  - Overseas articles translated to Japanese via Ollama
  - Publishes to `hems/news/{daily,urgent}` MQTT topics
- **Deploy**: Requires `--profile ollama` for summarization
- **Profile**: `docker compose --profile news --profile ollama up -d --build`
- **Brain tools**: `get_news_summary`
- **Brain rules**: urgent news speak notification
- **World model**: `NewsState` in Digital Space

---

## Knowledge Bridge (Multi-format document ingestion)

Read-only multi-format document ingestion from external directories with hybrid search.

- **knowledge-bridge**: Docker service with watchdog file monitoring
  - Plugin-based loaders: Markdown (.md), Python (.py), JSON (.json), Text (.txt/.yaml/.toml/.rst), PDF (.pdf), DOCX (.docx), CSV (.csv), HTML (.html)
  - **Hybrid search**: 3-way Reciprocal Rank Fusion (RRF)
    - BM25 (keyword): body text scoring via rank_bm25
    - Vector (semantic): Ollama embedding cosine similarity (optional, requires `--profile ollama`)
    - Title boost: separate BM25 on titles for precise name matching
  - Graceful degradation: BM25 + Title when Ollama unavailable
  - Embedding cache: disk-persisted, only re-embeds changed documents
  - Watches for file changes, publishes to `hems/personal/knowledge/*` MQTT topics
  - REST API for search, read, list sources, reindex
- **Deploy**: Mount source directories read-only, configure sources via JSON env var
- **Profile**: `docker compose --profile knowledge up -d --build`
- **Brain tools**: `search_knowledge` (cross-source search), `get_knowledge_sources`, `read_knowledge_document`, `get_recent_knowledge_changes` (最近変更ドキュメント)
- **Read-only**: No write-back to source directories (enforced at Docker mount level)
- **World model**: `KnowledgeState.external_sources` in Digital Space

Configure in `.env`:
```bash
KNOWLEDGE_BRIDGE_URL=http://knowledge-bridge:8000
KNOWLEDGE_SOURCE_PWS=/path/to/pws
KNOWLEDGE_SOURCES=[{"name":"pws","path":"/sources/pws","extensions":[".md",".py",".json",".pdf"]}]
# Vector search (optional, requires --profile ollama)
EMBEDDING_URL=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text
```
