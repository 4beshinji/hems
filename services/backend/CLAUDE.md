# services/backend/

Backend は FastAPI + SQLAlchemy async で構成される永続化・REST API 層です。task/voice/stats の persistence に加え、Device Registry / Shopping List / Chat といった横断サブシステムと、各ブリッジ向けの REST/MQTT 連携エンドポイントを提供します。

Extends the parent `hems/CLAUDE.md` (entry, build/run, MQTT topics, ports). Read that first if you haven't. Brain-side device tools and the brain chat server are documented in `services/brain/CLAUDE.md` — this file is the backend (persistence + HTTP) side.

## Schema migrations / startup

- Backend schemaはAlembic revision (`migrations/versions/`)が唯一のDDL SoT。`main.py` lifespanはDDLを実行しない。
- Containerは`entrypoint.py`、ローカルは`make backend-run`を使用し、`python -m migrations.bootstrap`成功後だけUvicornを起動する。
- 手動適用は`cd services/backend && python -m migrations.bootstrap`。`DATABASE_URL`は環境変数から読み、URL自体をlogしない。
- 現在のheadは`0002_legacy_additive_columns`。unversioned legacy DBもblind stampせずrevisionで検証/reconcileする。
- migration前にbackupを取得する。SQLiteはhead不一致時にrevision別`*.pre-<head>.bak`を自動作成し、PostgreSQLは運用backupを取得する。rollbackはDBをheadのままforward-fixする。
- Backend Alembicの所有範囲はPostgreSQL `public`のみ。Brain event storeの`events` schemaを変更してはならない。

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
  - テーブル所在: Backend DB が `approvals` / `action_snapshots` / `rollback_log` を保持

- **Feedback / Learning (Phase 1)**
  - Models: `AgentFeedback`, `AgentTrajectory` (`models.py`)
  - Router: `routers/feedback.py`
  - REST API:
    - `POST /feedback/` — ユーザーからの明示/暗黙フィードバックを `AgentFeedback` へ記録
    - `GET /feedback/` — フィードバック一覧・フィルタ
    - `GET /feedback/stats` — 集計（up/down/cancel/rerun 等）
    - `POST /feedback/trajectory` — Brain から decision-to-outcome 軌道を `AgentTrajectory` へ記録
    - `GET /feedback/trajectory` — 軌道一覧
  - 責務: Backend DB がフィードバックと軌道を永続化し、必要に応じて MQTT (`hems/feedback/{target_type}/{target_id}`) で Brain へ通知

- **Adaptive Thresholds (Phase 2)**
  - Models: `ThresholdDriftLog`, `ThresholdAdjustment` (`models.py`)
  - Router: `routers/adaptive_thresholds.py`
  - 責務: Brain からのドリフト検知提案を受け取り、人間承認/棄却/auto_apply を記録。承認時に `threshold_adjustments` へオフセットを永続化し、Brain 起動時に読み戻される
  - API:
    - `POST /thresholds/proposals` — 提案作成 (Brain から)
    - `GET /thresholds/proposals` / `GET /thresholds/proposals/{id}` — 一覧・詳細
    - `POST /thresholds/proposals/{id}/decide` — approve / reject / auto_apply
    - `GET /thresholds/adjustments` — 適用済みオフセット一覧
    - `POST /thresholds/adjustments` — Brain からの auto_applied 登録

- **Users & Places**
  - Models: `User`, `FrequentPlace` (`models.py`)
  - Routers: `routers/users.py`, `routers/frequent_places.py`
  - 責務: ユーザー情報、頻出場所管理

- **Zones (sensor snapshot)**
  - Router: `routers/zones.py`
  - 責務: Brain からの `POST /zones/snapshot` を受けて in-memory `_zone_store` を更新し、`GET /zones/` で最新ゾーンセンサーデータを返す。`Zone` DB モデルは存在しない

- **Mobile companion**
  - Model: `MobileDevice` (`models.py`)
  - Router: `routers/mobile.py`
  - 認証:
    - `admin_router` (`/mobile/register`, `/mobile/devices`, `/mobile/voice-capsule/*`): `Authorization: Bearer <BACKEND_API_KEY>` (`verify_api_key`)。`BACKEND_API_KEY` 未設定時はゼロコンフィグ LAN 信頼モードで開放
    - `device_router` (`/mobile/state/webhook`, `/mobile/voice-capsule/*`): 登録時に発行された per-device Bearer token (`verify_mobile_device`)。`/mobile/state/webhook` はさらに raw body の HMAC-SHA256 署名を `X-HEMS-Signature: sha256=<hex>` で検証する
  - 責務: モバイル端末登録、状態 webhook（位置/アクティビティ/生体/電池）、voice capsule 配信/ack
  - P1.3 durable path: `MobileObservationInbox` / `MobileDeliveryOutbox`、schema-v2 batch、`mobile_observations.py` adapter/transaction helperを使用。webhookはcommit後のみ2xxで、`mobile_delivery.py` single workerがMQTT QoS1/non-retainedまたはbiometric bridgeへretry配送する

- **Chat & Voice**
  - Models: `Conversation`, `Message`, `VoiceEvent`, `VoiceCapsule`, `VoiceCapsulePlayLog` (`models.py`)
  - Routers: `routers/chat.py`, `routers/voice_events.py`, `routers/character.py`
  - 責務: 会話/メッセージ永続化、Brain チャットサーバー `/chat` へのプロキシ、音声イベント・ボイスカプセル管理
  - 注記: `chat.py` は Brain HTTP エンドポイントへリクエストをプロキシする。詳細は「認証」節の internal-token 解説を参照

- **Biometrics**
  - Models: `BiometricLatest` (Brain cycle latest projection), `BiometricObservation` (immutable canonical history), `BiometricReading` (legacy history) (`models.py`)
  - Dashboard router: `routers/biometric.py` — `POST /biometric/snapshot` / `GET /biometric/` は`biometric_latest`をupsert/readし、`GET /biometric/history`は互換期間中`biometric_readings`を読む
  - Internal router: `routers/biometric_internal.py` — `POST /internal/biometric/observations`は`HEMS_INTERNAL_TOKEN`で保護し、stable observation IDとcanonical payload hashで同一payloadを冪等化、異なるpayloadを409にする
  - Canonical request schema/hashの正本は`services/_common/hems_common/biometric.py`。Backend `schemas.py`は互換import/re-exportのみ行う
  - 責務: latest projectionとcanonical observation historyの分離。bridge/mobile producerのこのinternal endpointへの配線は未実装

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

- **Brain control / batch**
  - Router: `routers/brain.py`
  - 責務:
    - `GET /brain/power-mode`, `POST /brain/power-mode` — Brain パワーモード取得/設定（MQTT `hems/brain/set-power-mode` 発行）
    - `POST /brain/snapshot` — Brain からの power-mode スナップショット受信
    - `GET /brain/ollama/models` — 利用可能な Ollama モデル一覧
    - `POST /brain/batch` — `hems/brain/batch-run` 経由でバッチタスク実行を要求
  - 注記: ダッシュボード → Brain HTTP 内部エンドポイントのプロキシは `chat.py`（`/chat`）と `devices.py`（`/devices/control` 等）が担当する

## Authentication / Internal proxy tokens

Backend-to-Brain、Backend-to-voice-service、Backend-to-ha-bridge 間のプロキシ呼び出しには、共有の内部トークン認証ヘルパー `hems_common.auth.internal_auth_headers()` を使用する。

- `HEMS_INTERNAL_TOKEN` が設定されている場合、`Authorization: Bearer <HEMS_INTERNAL_TOKEN>` を付加
- 未設定・空文字の場合は空の dict を返し、dev/ゼロコンフィグ環境では認証をスキップ
- 使用箇所:
  - `routers/chat.py` — Brain `/chat` へのプロキシ、voice-service `/api/voice/synthesize` への TTS 呼び出し
  - `routers/devices.py` — Brain `/devices/control`、Brain `/devices/zigbee/permit_join` へのプロキシ
  - `routers/home.py` — ha-bridge へのスマートホーム制御プロキシ

ダッシュボード向け API (`BACKEND_API_KEY`) と内部サービス間トークン (`HEMS_INTERNAL_TOKEN`) は独立しており、同じ値でも異なる値でもよい。

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
  - Backend は device lookup + enabled check 後、`body.params` をそのまま Brain の `/devices/control` REST に proxy するのみ
  - Brain 側 DeviceDispatcher が action dispatch（ha-bridge / switchbot-bridge / tapo-bridge / zigbee2mqtt ...）
  - Backend はこのエンドポイントで `DeviceActionLog` を書き込まない。アクション履歴は Brain が `POST /device-actions/` (`routers/device_actions.py`) へ書き込む

- **Safety**:
  - Backend は action params を検証しない。params の内容は Brain 側 `sanitizer.py` / `device_control_validator.py` で安全検証される
  - 例: pulse `duration_s` ≤ 600s、brightness 0-255、`color_temp` 153-500 等

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
