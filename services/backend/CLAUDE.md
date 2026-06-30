# services/backend/

Backend は FastAPI + SQLAlchemy async で構成される永続化・REST API 層です。task/voice/stats の persistence に加え、Device Registry / Shopping List / Chat といった横断サブシステムと、各ブリッジ向けの REST/MQTT 連携エンドポイントを提供します。

Extends the parent `hems/CLAUDE.md` (entry, build/run, MQTT topics, ports). Read that first if you haven't. Brain-side device tools and the brain chat server are documented in `services/brain/CLAUDE.md` — this file is the backend (persistence + HTTP) side.

## Backend Models / Routers Overview

主要な SQLAlchemy モデルと FastAPI ルーターをカテゴリ別に示します。詳細な CRUD 仕様は各ルーター/モデルファイルを参照してください。ファイルパスは `services/backend/` からの相対パスです。

- **Tasks & Scheduling**
  - Models: `Task`, `ScheduledBlock`, `DismissLog`, `TaskPreference` (`models.py`)
  - Routers: `routers/tasks.py`, `routers/timeline.py`
  - 責務: タスク CRUD、提案/棄却、スケジュールブロック生成・取得

- **Devices, Scenes, Automations**
  - Models: `Device`, `DeviceActionLog`, `Scene`, `AutomationRule` (`models.py`)
  - Routers: `routers/devices.py`, `routers/scenes.py`, `routers/automations.py`, `routers/device_actions.py`
  - 責務: デバイス永続化/heartbeat/制御プロキシ、シーン・自動化ルール CRUD、アクション履歴

- **Approvals / HITL (Phase 0)**
  - Models: `Approval`, `ActionSnapshot`, `RollbackLog` (`models.py`)
  - Manager: `approval_queue.py`
  - Router: `routers/approvals.py`
  - 責務: 人間承認リクエスト作成・決定・タイムアウト、実行前後スナップショット、ロールバック記録
  - テーブル所在: Backend DB が `approvals` / `action_snapshots` / `rollback_log` を保持。学習用テーブル (`agent_feedback`, `agent_trajectories`, `intervention_efficacy`) は Brain `event_store` (events schema) にあり、Backend は `/feedback` および `/approvals` REST エンドポイントで受け取り・仲介する

- **Users, Zones, Mobile, Places**
  - Models: `User`, `MobileDevice`, `FrequentPlace` (`models.py`)
  - Routers: `routers/users.py`, `routers/zones.py`, `routers/mobile.py`, `routers/frequent_places.py`
  - 責務: ユーザー・ゾーン情報、モバイル端末登録・HMAC 認証、頻出場所管理

- **Chat & Voice**
  - Models: `Conversation`, `Message`, `VoiceEvent`, `VoiceCapsule`, `VoiceCapsulePlayLog` (`models.py`)
  - Routers: `routers/chat.py`, `routers/voice_events.py`, `routers/character.py`
  - 責務: 会話/メッセージ永続化と Brain プロキシ、音声イベント・ボイスカプセル管理

- **Biometrics**
  - Model: `BiometricReading` (`models.py`)
  - Router: `routers/biometric.py`
  - 責務: 生体センサーデータの受信・履歴・集計

- **Shopping & Intelligence**
  - Models: `ShoppingItem`, `PurchaseHistory`, `ClassifierCache`, `SystemStats` (`models.py`)
  - Routers: `routers/shopping.py`, `routers/classifier_cache.py`, `routers/home.py`, `routers/services.py`
  - 責務: 買い物リスト CRUD、購入履歴、分類器キャッシュ、ダッシュボード統計

- **Time-series & Timeline**
  - Model: `TimeSeriesPoint` (`models.py`)
  - Routers: `routers/timeseries.py`, `routers/timeline.py`
  - 責務: 任意メトリクスの時系列書き込み/取得、24h タイムラインビュー

- **Bridge adapters**
  - Routers: `routers/weather.py`, `routers/news.py`, `routers/knowledge.py`, `routers/gas.py`, `routers/pc.py`, `routers/perception.py`, `routers/bridge_status.py`
  - 責務: 各ブリッジからの MQTT データを受け取り、キャッシュ/クエリ/転送用 REST を提供
  - Model: `BridgeStatusLog` — ブリッジの接続状態遷移を記録

- **Brain proxy**
  - Router: `routers/brain.py`
  - 責務: ダッシュボードから Brain 内部エンドポイントへの中継

## Device Registry (Unified sensor + actuator 管理)

すべてのセンサー/アクチュエータを単一 `Device` テーブルで管理。**二階層アーキテクチャ**: Backend = 永続 source-of-truth (SoT)、Brain = TTL 付き in-memory runtime cache。統合はしない（各層の責務は明確に分離）。

### Backend Device Registry (Persistent SoT)

**責務**: 登録・メタデータ保存・状態更新・REST CRUD / control proxy

- **テーブル**: `Device` (`models.py`) — `device_id` unique key
- **フィールド**:
  - 固定（ユーザー編集可）: `display_name`, `zone`, `location`, `purpose`（LLM context）, `description`, `is_enabled`, `notes`, `metadata_json`
  - 揮発性（自動更新）: `last_state`, `last_value`, `last_seen`, `last_seen_reported`, `battery_pct`, `link_quality`
  - メタ（初回登録・heartbeat で refine）: `vendor`, `vendor_ref`, `kind`, `device_class`, `capabilities`, `channels`, `units`, `model_id`, `manufacturer`, `icon`, `created_at`, `updated_at`

- `notes` はユーザー用の自由記述メモ。
- `metadata_json` は **vendor 固有設定を JSON 文字列として保持するフィールド**（汎用メタデータではない）。例: Zigbee exposes 等、機器固有の追加設定を保存する。heartbeat では上書きせず、UI/API 経由で編集する。

- **REST API** (`routers/devices.py`):
  - `GET /devices/` → list (`kind`/`vendor`/`zone`/`device_class`/`capability`/`enabled_only` でフィルタ)
  - `GET /devices/{device_id}` → fetch
  - `POST /devices/` → create (manual)
  - `PUT /devices/{device_id}` → update (metadata edit)
  - `DELETE /devices/{device_id}` → delete
  - `DELETE /devices/all` → 全デバイス削除（test reset 用）
  - `POST /devices/heartbeat` ← Brain heartbeat push、auto-register on unknown
  - `POST /devices/{device_id}/control` → manual control proxy to Brain
  - `POST /devices/zigbee/permit_join` → Z2M ペアリング許可/停止

- **Heartbeat インテーク** (`POST /devices/heartbeat`):
  - Brain の DeviceDispatcher が MQTT を解析後、`DeviceObservation` を REST push
  - 未知 `device_id` なら auto-create; 既知なら `last_state` / `last_value` / `battery_pct` / `link_quality` / `last_seen` を refresh
  - ユーザー編集フィールド（`display_name` / `purpose` / `zone` / `location` / `notes` / `metadata_json`）は保持（overwrite しない）
  - `vendor_ref` / `device_class` を generic fallback（`"zigbee"`, `"tapo"` 等）から refine 可（LLM の observation なら）
  - vendor 側 capability merge: `existing |= new_capabilities`

- **識別子検証**:
  - `device_id` と `vendor_ref` は `hems_common.validation` で統一検証
  - 正規表現: `^[\w.\-]+$`（英数字 + アンダースコア + ドット + ハイフン）
  - 最大 **128 文字**
  - ドット区切りセグメントが空でない（先頭/末尾ドット、連続ドット `a..b` を禁止）
  - スペースなど特殊文字は不可
  - パスパラメータ不正時は `400 Bad Request`
  - 起動時 `_audit_existing_device_ids()` で既存行を読み取り専用監査。不整合行は削除せず警告ログを出力

- **Control Proxy** (`POST /devices/{device_id}/control`):
  - Frontend / REST クライアント向け manual control endpoint
  - Backend は device lookup + enabled check 後、Brain の `/devices/control` REST に proxy
  - Brain 側 DeviceDispatcher が action dispatch（ha-bridge / switchbot-bridge / tapo-bridge / zigbee2mqtt ...）
  - 成功ログを `DeviceActionLog` へ記録（timeline view + analytics）

- **Safety**:
  - action params validation via shared validator（sanitizer の規則と統一）
  - pulse `duration_s` ≤ 600s、brightness 0-255、`color_temp` 153-500 等

### Brain Device Registry (Runtime TTL Cache)

**責務**: in-memory device metadata refresh、state transition tracking、network topology、utility scoring

- **クラス**: `DeviceRegistry` (`services/brain/src/device_registry.py`)
- **データ構造**: `dict[device_id: str] → DeviceInfo` (memory-only)
- **DeviceInfo フィールド**:
  - `device_id`, `device_type`, `power_mode`, `state` (online/sleeping/stale/offline)
  - `last_seen` (wall-clock), `last_seen_reported` (device-reported timestamp)
  - `battery_pct`, `link_quality`, `hops_to_mqtt`, `parent_id`, `children` (tree topology)
  - `next_wake_epoch` (sleep devices), `queue_status`, `utility_score` (decay via usage)

- **同期メカニズム**: MQTT heartbeat → Backend push
  1. Brain の MQTT subscriber が `*/heartbeat` トピックを observe
  2. `update_from_heartbeat(device_id, payload)` で in-memory state update（TTL refresh）
  3. dashboard_client → `/devices/heartbeat` REST で Backend へ push（永続化）
  4. Backend は auto-register or volatile fields refresh
  5. Frontend は `/devices/` fetch で Backend state を読む（UI source-of-truth = Backend）

- **State Automation**:
  - `_update_device_states()`: `last_seen` elapsed time based on state transition
    - elapsed < 120s → online
    - 120s ≤ elapsed < 900s → stale
    - elapsed ≥ 900s → offline
    - Sleeping device (`power_mode=DEEP_SLEEP/ULTRA_LOW` + `next_wake_epoch` 存在) → sleeping
  - `get_timeout_for_device()`: state 別の adaptive timeout（online 10s, sleeping 30s, offline 5s）

- **Tools** (Brain のみ):
  - `control_actuator(device_id, action, params)` → dispatcher → bridge
  - `list_devices(kind, zone, vendor, capability, purpose_contains)` → Backend DB query
  - `describe_device(device_id)` → Backend から fetch + Brain in-memory state の merge
  - `zigbee_permit_join(enable, duration_s)` → dispatcher publish

- **Utility Scoring** (ambient intelligence):
  - `record_zone_action(zone_id, action_type)`: LLM decision/task creation で zone device の `utility_score` += 0.3/0.5
  - `decay_utility_scores()`: 30日未使用 → score ceiling 2.0 → 0.5（grace 7d）
  - 用途: VRM motion selection / sensor weighting に活用

- **重要性**:
  - Backend DB 無くても LLM tool loop は ~10min 継続可（キャッシュ consistency を気にしない）
  - ただし UI state 取得は Backend DB 経由が必須（persistent view）
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
- **World model**: `ShoppingState` is rebuilt from the `hems/shopping/list` snapshot by `digital_updates._update_shopping_state`, so the recurring-due / departure reminder rules read live data. Per-event topics still feed `brain_mqtt` → ShoppingClassifier + event_store; backend DB remains the source of truth (see IMPLEMENTATION_MAP §5)
- **Brain tools/rules**: `add_shopping_item`, `get_shopping_list` (always-on) + recurring-due / departure reminders — see `services/brain/CLAUDE.md`

- **REST API** (`routers/shopping.py`):
  - `GET /shopping/` → 一覧（カテゴリ/店舗フィルタ、未購入のみ可）
  - `POST /shopping/` → 追加（重複時は数量マージ）
  - `PUT /shopping/{id}` → 全フィールド更新
  - `PATCH /shopping/{id}` → 部分更新（Brain の ShoppingClassifier が `store_category` を書き戻す用途）
  - `PUT /shopping/{id}/purchase` → 購入済みにして履歴を記録、定期商品は次回エントリを生成
  - `DELETE /shopping/{id}`
  - `GET /shopping/stats`
  - `GET /shopping/categories`, `GET /shopping/stores`
  - `GET /shopping/history`, `GET /shopping/purchase-history`
  - `GET /shopping/recurring`, `GET /shopping/due`
  - `POST /shopping/{id}/share` → 共有リンク生成（`item_id=0` で未購入全件）
  - `GET /shopping/shared/{token}` → 共有リンク閲覧（`public_router`）

- **共有リンクについての注記**: `public_router` は `routers/shopping.py` 内で定義されていますが、現状 `services/backend/main.py` では `include_router` されていません。そのため `POST /shopping/{id}/share` はトークンを生成できますが、`GET /shopping/shared/{token}` への実際のアクセスは機能しません。これは既知の実装バグです。

## Chat (backend side)

Interactive chat with the AI character via the dashboard. The backend persists and proxies; the brain runs the actual chat ReAct loop.

- **Backend chat router**: `/chat/` REST API — message persistence (`Conversation`/`Message` tables), Brain proxy, optional TTS
  - Sliding window: last 20 messages sent to Brain as conversation context
  - Auto-TTS: responses under 100 chars are synthesized via voice-service
  - Rate limiting: in-memory token bucket (`CHAT_RATE_LIMIT_CAPACITY` default `10`, `CHAT_RATE_LIMIT_REFILL` default `0.5`/sec). 制限超過時は `429 Too Many Requests` + `Retry-After` ヘッダを返す。`capacity <= 0` で無効化可
- **Brain chat server** (`services/brain/CLAUDE.md`): internal aiohttp server, separate read-only ReAct loop (max 3 iterations)
- **Frontend ChatPanel**: unified timeline (chat + voice events), text input + STT, optimistic UI, AudioQueue playback
