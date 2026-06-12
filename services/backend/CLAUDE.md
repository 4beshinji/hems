# services/backend/

Backend REST API (FastAPI + SQLAlchemy async) — task/voice/stats persistence plus three cross-cutting subsystems that span brain + frontend: the unified Device Registry, the Shopping List, and the Chat REST router.

Extends the parent `hems/CLAUDE.md` (entry, build/run, MQTT topics, ports). Read that first if you haven't. Brain-side device tools and the brain chat server are documented in `services/brain/CLAUDE.md` — this file is the backend (persistence + HTTP) side.

## Device Registry (Unified sensor + actuator 管理)

すべてのセンサー/アクチュエータを単一 `Device` テーブルで管理。**二階層アーキテクチャ**: Backend = 永続 source-of-truth (SoT)、Brain = TTL 付き in-memory runtime cache。統合はしない(各層の責務は明確に分離)。

### Backend Device Registry (Persistent SoT)

**責務**: 登録・メタデータ保存・状態更新・REST CRUD / control proxy

- **テーブル**: `Device` (`models.py`) — `device_id` unique key
- **フィールド**:
  - 固定(ユーザー編集):  `display_name`, `zone`, `location`, `purpose`(LLM context), `description`, `is_enabled`
  - 揮発性(自動更新): `last_state`, `last_value`, `last_seen`, `battery_pct`, `link_quality`, `last_seen_reported`
  - メタ(初回登録): `vendor`, `vendor_ref`, `kind`, `device_class`, `capabilities`, `channels`, `units`, `model_id`, `manufacturer`, `icon`, `metadata_json`
  
- **REST API** (`routers/devices.py`):
  - `GET /devices/` → list (kind/vendor/zone/device_class/capability でフィルタ)
  - `GET /devices/{device_id}` → fetch
  - `POST /devices/` → create (manual)
  - `PUT /devices/{device_id}` → update (metadata edit)
  - `DELETE /devices/{device_id}` → delete
  - `POST /devices/heartbeat` ← Brain heartbeat push、auto-register on unknown

- **Heartbeat インテーク** (`POST /devices/heartbeat`):
  - Brain の DeviceDispatcher が MQTT を解析後、DeviceObservation を REST push
  - 未知 device_id なら auto-create; 既知なら last_state / last_value / battery_pct / link_quality を refresh
  - ユーザー編集フィールド(display_name / purpose / zone)は保持 (overwrite しない)
  - vendor_ref / device_class を generic fallback (`"zigbee"`, `"tapo"`) から refine 可(LLM の observation なら)
  - vendor 側 capability merge: `existing |= new_capabilities`

- **Control Proxy** (`POST /devices/{device_id}/control`):
  - Frontend / REST クライアント向け manual control endpoint
  - Backend は device lookup + enabled check 後、Brain の `/devices/control` REST に proxy
  - Brain 側 DeviceDispatcher が action dispatch (ha-bridge / switchbot-bridge / tapo-bridge / zigbee2mqtt ...)
  - 成功ログを `DeviceActionLog` へ記録 (timeline view + analytics)

- **Safety**:
  - `device_id` 文字種検証: `^[\w.\-]+$` (alphanumeric + dot/dash)
  - action params validation via shared validator (sanitizer の規則と統一)
  - pulse duration_s ≤ 600s, brightness 0-255, color_temp 153-500 等

### Brain Device Registry (Runtime TTL Cache)

**責務**: in-memory device metadata refresh、state transition tracking、network topology、utility scoring

- **クラス**: `DeviceRegistry` (`services/brain/src/device_registry.py`)
- **データ構造**: `dict[device_id: str] → DeviceInfo` (memory-only)
- **DeviceInfo フィールド**:
  - `device_id`, `device_type`, `power_mode`, `state` (online/sleeping/stale/offline)
  - `last_seen` (wall-clock), `last_seen_reported` (device-reported timestamp)
  - `battery_pct`, `link_quality`, `hops_to_mqtt`, `children` (tree topology)
  - `next_wake_epoch` (sleep devices), `queue_status`, `utility_score` (decay via usage)

- **同期メカニズム**: MQTT heartbeat → Backend push
  1. Brain の MQTT subscriber が `*/heartbeat` トピックを observe
  2. `update_from_heartbeat(device_id, payload)` で in-memory state update (TTL refresh)
  3. dashboard_client → `/devices/heartbeat` REST で Backend へ push (永続化)
  4. Backend は auto-register or volatile fields refresh
  5. Frontend は `/devices/` fetch で Backend state 읆む (UI source-of-truth = Backend)

- **State Automation**:
  - `_update_device_states()`: last_seen elapsed time based on state transition
    - elapsed < 120s → online
    - 120s ≤ elapsed < 900s → stale
    - elapsed ≥ 900s → offline
    - Sleeping device (power_mode=DEEP_SLEEP/ULTRA_LOW + next_wake_epoch 存在) → sleeping
  - `get_timeout_for_device()`: state 別の adaptive timeout (online 10s, sleeping 30s, offline 5s)

- **Tools** (Brain のみ):
  - `control_actuator(device_id, action, params)` → dispatcher → bridge
  - `list_devices(kind, zone, vendor, capability, purpose_contains)` → Backend DB query
  - `describe_device(device_id)` → Backend から fetch + Brain in-memory state の merge
  - `zigbee_permit_join(enable, duration_s)` → dispatcher publish

- **Utility Scoring** (ambient intelligence):
  - `record_zone_action(zone_id, action_type)`: LLM decision/task creation で zone device の utility_score += 0.3/0.5
  - `decay_utility_scores()`: 30日未使用 → score ceiling 2.0 → 0.5 (grace 7d)
  - 用途: VRM motion selection / sensor weighting に活用

- **重要性**:
  - Backend DB 無くても LLM tool loop は ~10min 継続可(キャッシュ consistency を気にしない)
  - ただし UI state 取得は Backend DB 経由が必須(persistent view)
  - 新 vendor 追加時は dispatcher parser + Backend heartbeat intake の両方が要る

### 責務境界のまとめ

| 側 | role | 格納先 | 寿命 | 粒度 |
|---|---|---|---|---|
| **Backend** | source-of-truth、CRUD、UI view | DB | permanent | Device テーブル 1 row |
| **Brain** | runtime state refresh、state machine、LLM context | memory | TTL (120-900s) | DeviceInfo hash |

**結論**: 統合は避ける。Backend が persistent SoT、Brain が ephemeral LLM context cache というシンプルな契約のまま、dispatcher が仲介。

## Shopping List

Built-in shopping list with brain integration.

- **Backend**: CRUD API for shopping items with purchase history
- **Database**: `ShoppingItem`, `PurchaseHistory` models
- **MQTT**: `hems/shopping/{added,updated,purchased,deleted}` (per-event) + `hems/shopping/list` (full pending snapshot, published on every mutation)
- **World model**: `ShoppingState` is rebuilt from the `hems/shopping/list` snapshot by `digital_updates._update_shopping_state`, so the recurring-due / departure reminder rules read live data. Per-event topics still feed brain_mqtt → ShoppingClassifier + event_store; backend DB remains the source of truth (see IMPLEMENTATION_MAP §5)
- **Brain tools/rules**: `add_shopping_item`, `get_shopping_list` (always-on) + recurring-due / departure reminders — see `services/brain/CLAUDE.md`

## Chat (backend side)

Interactive chat with the AI character via the dashboard. The backend persists and proxies; the brain runs the actual chat ReAct loop.

- **Backend chat router**: `/chat/` REST API — message persistence (Conversation/Message tables), Brain proxy, optional TTS
  - Sliding window: last 20 messages sent to Brain as conversation context
  - Auto-TTS: responses under 100 chars are synthesized via voice-service
- **Brain chat server** (`services/brain/CLAUDE.md`): internal aiohttp server, separate read-only ReAct loop (max 3 iterations)
- **Frontend ChatPanel**: unified timeline (chat + voice events), text input + STT, optimistic UI, AudioQueue playback
