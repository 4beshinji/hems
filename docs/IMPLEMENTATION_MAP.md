# HEMS Implementation Map

**目的**: 実装と設計ドキュメント (CLAUDE.md / README.md / env.example) を突合するための単一の真実源。
将来 "ドキュメントが実装に追従しているか" を高速にチェックできるよう、コード上のシグネチャや MQTT トピックを直接列挙する。

**更新方針**:
- 新サービス・新ツール・新 MQTT トピックを追加したら、まずこのドキュメントを更新する。
- CLAUDE.md / README.md / env.example の差分修正は、このドキュメントを diff 元として行う。
- 検証コマンド (Verification) を各セクションに記載しているので、定期的にそれらを実行して乖離を検出する。

---

## 1. サービス棚卸し

### 1.1 Docker サービス (infra/docker-compose.yml に存在するもの)

| Service | Container | Profile | Source | Status |
|---------|-----------|---------|--------|--------|
| mosquitto | hems-mqtt | (always) | external image | ✓ |
| brain | hems-brain | (always) | services/brain | ✓ |
| backend | hems-backend | (always) | services/backend | ✓ |
| frontend | hems-frontend | (always) | services/frontend | ✓ |
| voice-service | hems-voice | (always) | services/voice | ✓ |
| weather-bridge | hems-weather-bridge | (always) | services/weather-bridge | ✓ |
| mock-llm | hems-mock-llm | mock | infra/mock_llm | ✓ |
| localcraw-bridge | hems-openclaw-bridge | openclaw / localcraw | external repo (`../localcraw`) | ✓ ※注 |
| obsidian-bridge | hems-obsidian-bridge | obsidian | services/obsidian-bridge | ✓ |
| gas-bridge | hems-gas-bridge | gas | services/gas-bridge | ✓ |
| homeassistant | hems-homeassistant | ha | external image | ✓ |
| matter-server | hems-matter-server | ha | external image | ✓ |
| ha-bridge | hems-ha-bridge | ha | services/ha-bridge | ✓ |
| biometric-bridge | hems-biometric-bridge | biometric | services/biometric-bridge | ✓ |
| voicevox | hems-voicevox | voicevox | external image | ✓ |
| ollama | hems-ollama | ollama | external image | ✓ |
| ollama-pull | hems-ollama-pull | ollama | external image | ✓ |
| postgres | hems-postgres | — (core) | external image | ✓ |
| perception | hems-perception | perception | services/perception | ✓ |
| switchbot-bridge | hems-switchbot-bridge | switchbot | services/switchbot-bridge | ✓ |
| tapo-bridge | hems-tapo-bridge | tapo | services/tapo-bridge | ✓ |
| zigbee2mqtt | hems-zigbee2mqtt | zigbee | external image | ✓ |
| news-bridge | hems-news-bridge | news | services/news-bridge | ✓ |
| knowledge-bridge | hems-knowledge-bridge | knowledge | services/knowledge-bridge | ✓ |
| stt-service | hems-stt | stt | services/stt | ✓ |

注: OpenClaw Bridge は互換のため compose service key `localcraw-bridge` を維持し、別リポジトリ
`../localcraw/` (Node.js + systeminformation) からビルドする。コンテナ名と DNS alias は
`hems-openclaw-bridge` / `openclaw-bridge`。`OPENCLAW_BRIDGE_URL` が正、`LOCALCRAW_BRIDGE_URL` は旧 alias。

### 1.2 services/ 配下、および apps/ に存在するが docker-compose に無い (Orphans / 非 Docker)

| Directory | 概要 | 状態 |
|-----------|------|------|
| services/data-bridge | Phase 2 scaffold (Strava/Fitbit/Garmin 用)、実装予定 W3.1 後 | **実装予定** — 共有ライブラリ W3.1/W3.2 完了後に `_common` ベース新規ブリッジとして実装(2026-08 月以降) |
| services/mobile-android | Android コンパニオンアプリ (Gradle プロジェクト) | **ALIVE** — Docker 化対象外。apk ビルド、実デバイス配布。詳細: [`services/mobile-android/README.md`](../services/mobile-android/README.md) |
| apps/healthconnect-companion | Android Health Connect reader (Gradle プロジェクト) | **ALIVE** — Docker 化対象外。apk ビルド、実デバイス配布。biometric-bridge webhook データソース。詳細: [`apps/healthconnect-companion/README.md`](../apps/healthconnect-companion/README.md) |

### 1.3 Verification

```bash
# compose に登録されたサービス一覧
grep -E '^\s+(container_name:|profiles:)' infra/docker-compose.yml

# services/ に存在するディレクトリ
ls services/

# 差分: services/ にあって compose に build パスが無いものが orphan 候補
diff <(ls services/) <(grep -E "build: \.\./services/" infra/docker-compose.yml | awk -F'/' '{print $NF}' | sort -u)
```

---

## 2. Brain 内部モジュール一覧

初期化は 2 段に分かれる: **always-on コア**は `services/brain/src/main.py` の `Brain.__init__`、
**async startup 配線**は `brain_startup.py` の `_wire_runtime_components()`(`Brain.run()` から呼ばれる)。
「起動条件」列の `startup` は後者を指す。

| Module | File | 起動条件 | 役割 |
|--------|------|----------|------|
| MCPBridge | mcp_bridge.py | always | レガシー MCP 経由のエージェントブリッジ |
| Sanitizer | sanitizer.py | always | ツール呼び出し / コマンドのバリデーション |
| WorldModel | world_model/world_model.py | always | 三領域 (Physical/Digital/User) の世界モデル |
| DeviceRegistry | device_registry.py | always | センサー/アクチュエータの統一メタデータ |
| EventWriter / HourlyAggregator | event_store/ | always | event_store DB へのイベント書込 |
| RuleEngine | rule_engine.py | always | 閾値ベースのフォールバック・回路 |
| PowerModeManager | low_power_mode.py | always | normal/sleep/away モード管理 + LLM レート制限 |
| LLMClient | llm_client.py | startup | プロバイダ抽象 (OpenAI/Anthropic/Ollama) |
| LLMRouter | llm_router.py | startup | 軽量/重量モデルの振り分け |
| BootLoadManager | boot_load_manager.py | `BOOT_LOAD_ENABLED=true` (default true) | 起床前の重量モデル briefing 事前生成 |
| SunriseAlarm | sunrise_alarm.py | `SUNRISE_ALARM_DEVICE` 設定時 | Zigbee ライトの段階的明度ランプアップ |
| ScheduleLearner | schedule_learner.py | HA / biometric / switchbot 有効時 | 帰宅・出発・起床パターン学習 |
| TimelineGenerator | timeline/ | startup (常時 instantiate) | 1日のタイムライン生成 (EDF + free window)。calendar 無時は内部 degrade |
| EventAutomation | event_automation.py | startup (常時 instantiate) | wake_up / arrival / departure / scheduled 連動。action は news/gas 無時 degrade |
| AmbientSpeaker | ambient_speaker.py | startup | 5分間隔の自然な独り言生成 |
| AutomationEngine | automation_engine.py | always | sensor_threshold / schedule / device_state / event ルール。`event` は完全一致 + glob ワイルドカード（例: `motion:*`）。`require_confirm=true` / `approval_required=true` 時は ApprovalGate 経由 |
| ApprovalGate | approval/gate.py | always (backend 接続時) | HITL 承認ゲート: 高リスク/不可逆アクション実行前に人間承認を取得 |
| ApprovalClient | approval/client.py | ApprovalGate から利用 | backend `/approvals` API 非同期クライアント |
| ActionRiskClassifier | approval/action_risk_classifier.py | ApprovalGate から利用 | ルール/アクションの risk_tier / reversibility / approval_required 判定 |
| RollbackPlanner | approval/rollback_planner.py | ApprovalGate から利用 | 実行済みアクションの補償アクション計画 |
| RollbackExecutor | approval/rollback_executor.py | ApprovalGate から利用 | 補償アクション実行 + backend ロールバックログ記録 |
| VerificationWatcher | approval/verification_watcher.py | 任意 | ロールバック後のデバイス状態検証 |
| ApprovalAuditLogger | approval/audit_logger.py | ApprovalGate から利用 | event_store への承認ライフサイクルイベント記録 |
| SceneExecutor | scene_executor.py | always | 複数デバイスを束ねた named scene 実行 |
| DeviceDispatcher | device_dispatcher.py | always | vendor (ha/switchbot/tapo/zigbee/mcp) 振り分け |
| TaskQueueManager | task_scheduling/ | startup | LLM 出力タスクのバッチ化 |
| TaskReminder | task_reminder.py | startup | 期日付きタスクの再通知 |
| ToolExecutor | tool_executor.py | startup | LLM tool calls のディスパッチ |
| PersonaRewriter | persona_rewriter.py | startup (常時 instantiate) | rule-engine speak をキャラ口調に書換。`PERSONA_REWRITE_ENABLED=false` で書換動作のみ無効化(instantiate はされる) |
| Annotators | annotator/ | startup | EventClassifier / RulePromoter / ShoppingClassifier / ClassifierCache |
| AckLearner | voice_capsule/ack_learner.py | mobile companion 経由 | ユーザー認識パターン学習 |
| MotionRetriever | motion_retriever.py | startup | VRM モーション選定 (BM25 + 親和度 + 新規性) |
| DashboardClient | dashboard_client.py | startup | backend API 経由のフロント連携 |

### 2.1 Verification

```bash
# always-on コア (__init__)
grep -nE "self\.\w+ = " services/brain/src/main.py | head -50
# async startup 配線 (_wire_runtime_components / _start_event_store)
grep -nE "self\.\w+ = " services/brain/src/brain_startup.py | head -50
```

### 2.2 Device Registry 双層アーキテクチャ

Brain DeviceRegistry は Backend Device Registry と対を成す **分離設計**(統合しない)。

| 側 | 役割 | 実装 | 寿命 | 同期 |
|---|---|---|---|---|
| **Backend** | persistent SoT、CRUD、UI view | `models.Device` DB table、`routers/devices.py` REST API | 永続 | heartbeat intake (auto-register / volatile refresh) |
| **Brain** | in-memory LLM context cache、state automation、timeout optimization | `DeviceRegistry` class (`device_registry.py`)、`dict[device_id → DeviceInfo]` | TTL 120-900s | MQTT heartbeat → `update_from_heartbeat()` + async `dashboard_client.push_device_heartbeat()` |

**Heartbeat Flow**:
1. MQTT sensor / bridge publish → Brain subscriber
2. dispatcher.parse_mqtt() → DeviceObservation
3. brain_mqtt._update_device_registry() → device_registry.update_from_heartbeat()
4. dashboard_client.push_device_heartbeat() → Backend POST /devices/heartbeat
5. Backend: unknown device_id なら auto-create、already known なら volatile fields (last_state/last_value/battery_pct/link_quality) のみ refresh

**Tool層の分担**:
- `control_actuator(device_id, action, params)`: Brain dispatcher → bridge (vendor-specific)
- `list_devices(...)`: Backend DB query (SoT)
- `describe_device(device_id)`: Backend fetch + Brain cache state merge
- LLM は always Backend SoT 結果を見る(refresh guarantees)

### 2.3 Backend Models と Persistence

Device Registry persistent 層。以下を参照: `services/backend/models.py` 内の `Device` class。

| Field | Type | Role | 更新ソース | 注記 |
|-------|------|------|-----------|------|
| `device_id` | str (unique) | Primary key | heartbeat (Brain dispatcher) | 形式: vendor.詳細 (e.g. `zigbee.0x781c...`) |
| `vendor` | str | 分類(zigbee/tapo/switchbot/ha/mcp) | heartbeat (初回のみ) | autoregister 時に auto-populate |
| `vendor_ref` | str | ベンダー側ID (IEEE addr / IP / entity_id) | heartbeat (既知なら refine のみ) | Zigbee IEEE addr or HA entity_id |
| `kind` | str | 分類(sensor/actuator/both) | heartbeat (upgrade: sensor→actuator/both) | can only upgrade, not downgrade |
| `device_class` | str | device_class(plug/light/bulb/pump/temp_humidity/co2/pir/hub_ir等) | heartbeat (generic fallback から refine) | Z2M definition.description から推定 |
| `capabilities` | JSON list | 操作可能アクション(on_off/brightness/color_temp/pulse/ir_send等) | heartbeat (merge: existing ∪ new) | set union、重複排除 |
| `channels` | JSON list | センサー出力チャネル(temperature/humidity/soil_moisture) | heartbeat (初回のみ) | sensor only |
| `units` | JSON dict | チャネル単位({temperature: °C}) | heartbeat (初回のみ) | LLM context |
| `display_name` | str | ユーザー表示名 (e.g. "デスク照明") | Frontend `/devices/{id}` PUT (ユーザー編集) | **重要: heartbeat では placeholder name なら override** |
| `zone` | str | 物理ゾーン(main / study / kitchen など) | Frontend `/devices/{id}` PUT | LLM context、scheduler filter |
| `location` | str | 詳細位置(e.g. "北側壁") | Frontend `/devices/{id}` PUT | UI 表示 |
| `purpose` | str | LLM context (e.g. "起床補助ライト" / "水やりポンプ") | Frontend `/devices/{id}` PUT | **LLM tool decision に活用** |
| `description` | str | 説明文(e.g. "Zigbee IKEA GLEDOPTO RGB bulb") | heartbeat (初回のみ) or Frontend PUT | audit trail |
| `model_id` | str | 製造元型番(Z2M definition.model e.g. LED2109G6) | heartbeat (初回のみ) | firmware update tracking |
| `manufacturer` | str | 製造元(Z2M definition.vendor e.g. IKEA) | heartbeat (初回のみ) | compatibility matrix |
| `icon` | str | lucide icon name | Frontend PUT | UI 表示 |
| `last_state` | JSON dict | 最後の状態({on: true, brightness: 200}) | heartbeat (push each update) | 揮発性 |
| `last_value` | JSON dict | センサー最新値({temperature: 22.5, humidity: 55}) | heartbeat (push each update) | 揮発性 |
| `last_seen` | datetime | 最後に heartbeat を受け取った wall-clock 時刻 | heartbeat intake時に自動設定 | 揮発性、state machine の入力(online/stale/offline) |
| `last_seen_reported` | datetime | device が自身で報告した timestamp (Zigbee LQI last_seen等) | heartbeat payload の `last_seen_reported` | device-local time、ズレ検出用 |
| `battery_pct` | int (0-100) | バッテリー残量 | heartbeat (if present) | nullable |
| `link_quality` | int | 通信品質スコア(Zigbee LQI 0-255 or Switchbot RSSI) | heartbeat (if present) | 揮発性 |
| `is_enabled` | bool | 無効化フラグ(true = 使用中) | Frontend PUT (disable/enable) | control proxy で checked |
| `notes` | str | メモ(ユーザー編集) | Frontend PUT | audit |
| `metadata_json` | str | ベンダー固有設定(過去互換用 JSON) | Future | 拡張性予約 |
| `created_at` | datetime | 初回登録時刻 | auto (server_default) | audit trail |
| `updated_at` | datetime | 最後に更新した時刻 | auto (onupdate) | audit trail |

**重要**: heartbeat 時に display_name が placeholder name (empty / raw IEEE addr / device_id そのまま) なら override、それ以外は保持。

### 2.4 Approval / HITL Persistence

`services/backend/models.py` に定義された承認・ロールバックテーブル。

| Table | 主な役割 | 主要カラム | 所在 |
|-------|---------|-----------|------|
| `approvals` | 人間承認リクエストと履歴 | `id` (UUID), `rule_id`, `action_type`, `risk_tier`, `reversibility`, `proposed_payload`, `context`, `status`, `decision`, `reviewer_id`, `requested_at`, `decided_at`, `executed_at`, `rollback_status`, `audit_log` | Backend DB |
| `action_snapshots` | 実行前後のデバイス/シーン状態 | `approval_id`, `entity_type`, `entity_id`, `before_state`, `after_state`, `captured_at` | Backend DB |
| `rollback_log` | 補償操作の実行記録 | `approval_id`, `trigger`, `compensation_plan`, `execution_status`, `started_at`, `completed_at`, `error_message` | Backend DB |
| `intervention_efficacy` | 介入効果測定 + Phase 0 HITL 紐付け | `approval_id`, `human_decision`, `rolled_back`, `rollback_success`, `efficacy_score` | Brain `event_store` (events schema) |
| `agent_feedback` | 明示・暗黙フィードバック | `target_type`, `target_id`, `feedback_type`, `channel`, `payload`, `context`, `user_id`, `recorded_at` | Brain `event_store` (events schema)。Backend は `/feedback` REST 経由で受け取り、MQTT (`hems/feedback/{target_type}/{target_id}`) で Brain に転送 |
| `agent_trajectories` | 決定→結果の軌道 | `cycle_id`, `decision_id`, `trigger_events`, `tool_calls`, `world_state_snapshot`, `outcome_summary` | Brain `event_store` (events schema) |
| `threshold_drift_log` | 閾値ドリフト検知・提案 | `metric_key`, `detector`, `detected_at`, `old_value`, `proposed_value`, `reason`, `status`, `context_json` | Backend DB |
| `threshold_adjustments` | 適用済み閾値オフセット | `metric_key`, `base_value`, `offset`, `applied_at`, `approved_by`, `drift_log_id` | Backend DB |
| `drift_detections` | Brain 内ドリフト検知ログ | `metric_key`, `detector`, `old_threshold`, `proposed_threshold`, `detector_state` | Brain `event_store` (events schema) |

Backend API:
- `services/backend/routers/approvals.py` — 承認フロー
- `services/backend/routers/feedback.py` — `/feedback` / `/feedback/trajectory` エンドポイント
- `services/backend/routers/adaptive_thresholds.py` — `/thresholds/proposals` / `/thresholds/adjustments` エンドポイント
- `POST /approvals` — 承認リクエスト作成
- `GET /approvals` / `GET /approvals/{id}` — 一覧・詳細
- `POST /approvals/{id}/decide` — approve / reject / modify
- `POST /approvals/{id}/execute` — Brain 実行完了マーク
- `POST /approvals/{id}/rollback` — ロールバック記録
- `POST /approvals/{id}/snapshots` — 状態スナップショット記録
- `POST /approvals/cleanup/expired` — 期限切れクリーンアップ
- `GET /thresholds/proposals` / `GET /thresholds/proposals/{id}` — 閾値変更提案一覧・詳細
- `POST /thresholds/proposals/{id}/decide` — approve / reject / auto_apply
- `GET /thresholds/adjustments` — 適用済みオフセット一覧
- `POST /thresholds/adjustments` — Brain からの auto_applied 登録

---

## 3. Brain Tools 一覧 (LLM が呼べるもの)

`services/brain/src/tool_registry.py` の `get_tools()` が返す JSON Schema と、`tool_dispatch.py` の `TOOL_HANDLERS` を突合した結果(全 flag 有効時 **58 ツール**、schema↔handler 完全一致を §3.5 で検証)。

### 3.1 Always-on (gating: なし)

| Tool | 備考 |
|------|------|
| `create_task` | タスク作成 |
| `send_device_command` | レガシー MCP コマンド (廃止予定) |
| `get_zone_status` | ゾーン状態取得 |
| `speak` | 音声発話 (Stage 2 character overlay 適用) |
| `get_active_tasks` | アクティブタスク一覧 |
| `get_device_status` | レガシー (`describe_device` を推奨) |
| `get_sensor_history` | センサー履歴クエリ (event_store) |
| `add_shopping_item` | 買い物リスト追加 |
| `get_shopping_list` | 買い物リスト取得 |

### 3.2 Profile-gated

| Tool | 必要環境変数 | 備考 |
|------|--------------|------|
| `get_pc_status` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) | PC メトリクス |
| `run_pc_command` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) | shell command 実行 (sanitizer でブロック) |
| `control_browser` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) | Playwright 経由 |
| `send_pc_notification` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) | デスクトップ通知 |
| `get_service_status` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) + service データ存在時 | Gmail/GitHub/browser checker |
| `search_notes` | `OBSIDIAN_BRIDGE_URL` | Obsidian vault 検索 |
| `write_note` | `OBSIDIAN_BRIDGE_URL` | `HEMS/` 配下のみ書込可 |
| `get_recent_notes` | `OBSIDIAN_BRIDGE_URL` | 最新ノート取得 |
| `control_light` | `HA_BRIDGE_URL` | HA ライト制御 |
| `control_climate` | `HA_BRIDGE_URL` | HA エアコン制御 |
| `control_cover` | `HA_BRIDGE_URL` | HA カーテン制御 |
| `get_home_devices` | `HA_BRIDGE_URL` | HA エンティティ一覧 |
| `control_switch` | `HA_BRIDGE_URL` | HA スイッチ制御 |
| `get_sensor_data` | `HA_BRIDGE_URL` | HA センサー値 |
| `execute_scene` | `HA_BRIDGE_URL` | HA シーン実行 |
| `set_guest_mode` | `HA_BRIDGE_URL` | 来客モード ON/OFF |
| `get_weather` | (always-on) | world_model.weather (weather-bridge → MQTT) から読む |
| `get_biometrics` | `BIOMETRIC_BRIDGE_URL` | 生体データ |
| `get_sleep_summary` | `BIOMETRIC_BRIDGE_URL` | 睡眠サマリ |
| `get_perception_status` | `PERCEPTION_BRIDGE_URL` | カメラ検出状態 |
| `describe_scene` | `PERCEPTION_BRIDGE_URL` | VLM 即時シーン記述 |
| `list_scene_objects` | `PERCEPTION_BRIDGE_URL` | VLM 履歴オブジェクト |
| `get_scene_timeline` | `PERCEPTION_BRIDGE_URL` | VLM 履歴タイムライン |
| `get_switchbot_devices` | `SWITCHBOT_BRIDGE_URL` | SwitchBot 一覧 |
| `control_switchbot` | `SWITCHBOT_BRIDGE_URL` | SwitchBot 制御 |
| `send_switchbot_ir` | `SWITCHBOT_BRIDGE_URL` | Hub IR コマンド |
| `get_news_summary` | `NEWS_BRIDGE_URL` | RSS daily/urgent 取得 |
| `search_knowledge` | `KNOWLEDGE_BRIDGE_URL` | 外部ドキュメント検索 |
| `get_knowledge_sources` | `KNOWLEDGE_BRIDGE_URL` | 設定済みソース一覧 |
| `read_knowledge_document` | `KNOWLEDGE_BRIDGE_URL` | ドキュメント本文取得 |
| `list_processes` | `OPENCLAW_BRIDGE_URL` (`LOCALCRAW_BRIDGE_URL` alias) | PC プロセス一覧 (CPU/メモリでソート、name フィルタ) |
| `get_entity_status` | `HA_BRIDGE_URL` | HA 単一エンティティ状態 |
| `get_power_consumption` | `TAPO_BRIDGE_URL` | Tapo 瞬時電力 (W) — device_id 省略で全プラグ並列取得 |
| `get_recent_emails` | `GAS_BRIDGE_URL` | Gmail スレッド一覧 (sender/subject/unread でフィルタ) |
| `gas_query_free_slots` | `GAS_BRIDGE_URL` | カレンダー空き時間クエリ |
| `gas_query_sheet` | `GAS_BRIDGE_URL` | Google Sheets 値クエリ |
| `list_note_tags` | `OBSIDIAN_BRIDGE_URL` | Obsidian タグ一覧 |
| `get_recent_knowledge_changes` | `KNOWLEDGE_BRIDGE_URL` | 外部ナレッジ最近変更 |
| `get_biometric_trend` | `BIOMETRIC_BRIDGE_URL` | 生体メトリクスのトレンド |
| `get_sleep_history` | `BIOMETRIC_BRIDGE_URL` | 睡眠履歴 |
| `list_cameras` | `PERCEPTION_BRIDGE_URL` | カメラ一覧 |
| `get_vlm_status` | `PERCEPTION_BRIDGE_URL` | VLM 稼働状態 |
| `get_activity_history` | `PERCEPTION_BRIDGE_URL` | 活動履歴 |

### 3.3 Device Registry (default: enabled)

| Tool | 備考 |
|------|------|
| `control_actuator` | vendor 非依存の統一制御 (on/off/toggle/set_*/pulse/ir_send) |
| `list_devices` | kind/zone/vendor/capability/purpose で検索 |
| `describe_device` | デバイスメタ + 現在状態 |
| `execute_scene_by_name` | named scene の実行 |
| `list_scenes` | 利用可能 scene 一覧 |
| `zigbee_permit_join` | ペアリング許可 (60秒 / 任意秒) |

### 3.4 Chat-only allowlist

`get_chat_tools()` で読み取り系のみに絞られる: search_notes / search_knowledge / get_biometrics / get_zone_status / get_weather など。書込系 (speak / control_* / create_task) は除外。

### 3.5 Verification

```bash
PYTHONPATH=services/brain/src:services/backend .venv/bin/python - <<'PY'
from tool_dispatch import TOOL_HANDLERS
from tool_registry import get_tools

flags = dict(
    openclaw_enabled=True,
    services_enabled=True,
    obsidian_enabled=True,
    ha_enabled=True,
    biometric_enabled=True,
    perception_enabled=True,
    shopping_enabled=True,
    switchbot_enabled=True,
    news_enabled=True,
    knowledge_enabled=True,
    gas_enabled=True,
    tapo_enabled=True,
    device_registry_enabled=True,
)
schema_names = {tool["function"]["name"] for tool in get_tools(**flags)}
handler_names = set(TOOL_HANDLERS)
print("schema_count", len(schema_names), "handler_count", len(handler_names))
print("schema_only", sorted(schema_names - handler_names))
print("handler_only", sorted(handler_names - schema_names))
assert schema_names == handler_names
PY
```

---

## 4. MQTT Topic Map

### 4.0 トピックツリー(可読リファレンス)

ドメイン別の全トピック一覧。`hems/CLAUDE.md` から集約(プレフィックス概要のみ親に残す)。ブリッジ別の詳細は `docs/CLAUDE-bridges.md`。

```
# Sensor telemetry
hems/sensors/{zone}/{device_type}/{device_id}/{channel}   # canonical (W3.8c)

# PC metrics (OpenClaw bridge)
hems/pc/metrics/{cpu|memory|gpu|disk|temp}
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
hems/ha/bridge/status              # canonical (W3.3)
hems/home/bridge/status            # legacy compat (互換 window — 旧 ha-bridge が発行していたトピック)

# Biometric data (biometric-bridge)
hems/personal/biometrics/{provider}/heart_rate
hems/personal/biometrics/{provider}/spo2
hems/personal/biometrics/{provider}/sleep
hems/personal/biometrics/{provider}/activity
hems/personal/biometrics/{provider}/steps
hems/personal/biometrics/{provider}/stress
hems/personal/biometrics/{provider}/fatigue
hems/biometric/bridge/status       # canonical (W3.3)
hems/personal/biometrics/bridge/status  # legacy compat (互換 window)

# Perception (camera detection + activity tracking + VLM)
hems/sensors/{zone}/camera/{camera_id}/status   # canonical (W3.8c)
hems/sensors/{zone}/activity/{monitor_id}       # canonical (W3.8c)
hems/perception/bridge/status
hems/perception/vlm/{zone}
hems/perception/vlm/status
hems/perception/vlm/model_swap
hems/perception/vlm/request

# Personal data (future: data-bridge — service is a stub, no compose entry yet)
hems/personal/calendar/{id}/events
hems/personal/training/fitness
hems/system/gpu/utilization

# Tapo (direct LAN bridge)
hems/tapo/{vendor_ref}/state

# Zigbee2MQTT (direct, retained)
zigbee2mqtt/{device}              # device state
zigbee2mqtt/bridge/devices        # device listing

# Shopping list
hems/shopping/{added,updated,purchased,deleted}  # per-event (ShoppingClassifier + event_store)
hems/shopping/list                               # full pending snapshot (world_model ShoppingState reducer)

# SwitchBot (direct API bridge)
# device/sensor state は HA 互換で hems/home/* に publish(world_model _update_home_device で統合)
hems/home/{zone}/{domain}/{entity_id}/state
hems/home/{zone}/sensor/switchbot.{device_id}_{temperature,humidity,co2,power}/state
hems/switchbot/bridge/status   # bridge status のみ hems/switchbot/

# News (news-bridge)
hems/news/daily
hems/news/urgent
hems/news/bridge/status

# Knowledge (knowledge-bridge)
hems/personal/knowledge/changed
hems/personal/knowledge/stats

# Weather (weather-bridge, always-on)
hems/weather/{current,forecast,alerts}
hems/weather/bridge/status

# Brain control
hems/brain/reload-character
hems/brain/guest-mode

# Approval / feedback
hems/approvals/{id}/decide
hems/feedback/{target_type}/{target_id}

# Adaptive thresholds
hems/thresholds/drift_detected
hems/thresholds/adjustment_proposed
hems/thresholds/adjustment_applied
```

### 4.1 ブローカーへの subscribe (Brain)

`brain/src/main.py:on_connect` より:

```
mcp/+/response/#
office/+/task_report/#   # backend → brain task reports only (W3.8c)
hems/#
zigbee2mqtt/#
```

### 4.2 Publishers (サービスから出るトピック)

| Publisher | Topic | Payload 概要 |
|-----------|-------|--------------|
| MCP / ESP32 sensors | `hems/sensors/{zone}/sensor/{device_id}/{channel}` *(canonical — W3.8c)* | temperature / humidity / co2 / pressure / light / voc / pm25 / soil_moisture / motion / motion_count / vibration / door / presence |
| perception (camera) | `hems/sensors/{zone}/camera/{cam_id}/status` *(canonical — W3.8c)* | person_count, count |
| perception (activity) | `hems/sensors/{zone}/activity/{monitor_id}` *(canonical — W3.8c)* | activity_level / activity_class / posture / posture_duration_sec / posture_status |
| perception (VLM) | `hems/perception/vlm/{zone}` | scene_description / objects / scene_type / anomalies |
| perception (VLM mgmt) | `hems/perception/vlm/status` | service status |
| perception (VLM mgmt) | `hems/perception/vlm/model_swap` | swap event |
| perception (bridge) | `hems/perception/bridge/status` | health |
| brain (request) | `hems/perception/vlm/request` | rule engine からの再スキャン要求 |
| backend | `hems/approvals/{approval_id}/decide` | 人間承認決定通知 (approve/reject/modify)。Brain ApprovalClient はポーリングでも取得 |
| backend | `hems/feedback/{target_type}/{target_id}` | フィードバック作成通知。Brain `feedback_collector` が購読して event_store の `agent_feedback` へ複製 |
| brain | `hems/thresholds/drift_detected` | ドリフト検知通知。Backend `/thresholds/proposals` でも提案を受け付ける |
| OpenClaw bridge | `hems/pc/metrics/{cpu,memory,gpu,disk,temp}` | PC メトリクス |
| OpenClaw bridge | `hems/pc/processes/top` | top プロセス一覧 |
| OpenClaw bridge | `hems/pc/bridge/status` | bridge 状態 |
| OpenClaw bridge | `hems/services/{name}/status` | Gmail / GitHub / browser checker |
| OpenClaw bridge | `hems/services/{name}/event` | unread 増加などのエッジトリガー |
| obsidian-bridge | `hems/personal/notes/changed` | ファイル変更通知 |
| obsidian-bridge | `hems/personal/notes/stats` | vault 統計 |
| gas-bridge | `hems/gas/calendar/upcoming` | 直近イベント |
| gas-bridge | `hems/gas/calendar/free_slots` | 空き枠 |
| gas-bridge | `hems/gas/tasks/all` | 全タスク |
| gas-bridge | `hems/gas/tasks/due_today` | 今日期限 |
| gas-bridge | `hems/gas/gmail/summary` | Gmail サマリ |
| gas-bridge | `hems/gas/gmail/recent` | Gmail 最近 |
| gas-bridge | `hems/gas/sheets/{name}` | Sheets |
| gas-bridge | `hems/gas/drive/recent` | Drive 最近ファイル |
| gas-bridge | `hems/gas/bridge/status` | 健康状態 |
| ha-bridge | `hems/home/{zone}/{domain}/{entity_id}/state` | HA エンティティ状態 |
| ha-bridge | `hems/ha/bridge/status` | 健康状態 (canonical W3.3) |
| ha-bridge | ~~`hems/home/bridge/status`~~ | 旧トピック(互換 window — brain は新旧両方を受信) |
| biometric-bridge | `hems/personal/biometrics/{provider}/{metric}` | heart_rate / spo2 / sleep / activity / steps / stress / fatigue / hrv / body_temp / respiratory_rate |
| biometric-bridge | `hems/biometric/bridge/status` | 健康状態 (canonical W3.3) |
| biometric-bridge | ~~`hems/personal/biometrics/bridge/status`~~ | 旧トピック(互換 window — brain は新旧両方を受信) |
| switchbot-bridge | `hems/home/{zone}/sensor/switchbot.{device_id}_{temperature,humidity,co2,power}/state` | デバイス状態 |
| switchbot-bridge | `hems/switchbot/bridge/status` | 健康状態 |
| tapo-bridge | `hems/tapo/{vendor_ref}/state` | 電力計測 + on/off |
| news-bridge | `hems/news/daily` | 日次サマリ |
| news-bridge | `hems/news/urgent` | 緊急ニュース |
| news-bridge | `hems/news/bridge/status` | 健康状態 |
| knowledge-bridge | `hems/personal/knowledge/changed` | 変更通知 |
| knowledge-bridge | `hems/personal/knowledge/stats` | 統計 |
| weather-bridge | `hems/weather/{current,forecast,alerts}` | 現在天気・予報・警報 |
| weather-bridge | `hems/weather/bridge/status` | 健康状態 |
| zigbee2mqtt | `zigbee2mqtt/{device}` | デバイス状態 (retained) |
| zigbee2mqtt | `zigbee2mqtt/bridge/devices` | 全デバイス listing (retained) |
| backend | `hems/shopping/{added,updated,purchased,deleted}` | ショッピング連動 (per-event) |
| backend | `hems/shopping/list` | 全 pending snapshot (ShoppingState reducer 用) |
| brain | `hems/brain/reload-character` | self-trigger |
| brain | `hems/brain/guest-mode` | self-trigger |
| brain | `hems/brain/set-power-mode` | self-trigger |
| brain | `hems/brain/batch-run` | self-trigger |

### 4.3 Brain WorldModel 受信 (`update_from_mqtt`) → 状態反映

`update_from_mqtt`(ルーティング)は `world_model/mqtt_router.py`(`MqttRouterMixin`)、各 `_update_*` ハンドラは
`world_model/{physical,digital,user}_updates.py` のミキシンに分割済(facade `world_model.py` が全体を合成)。

| Topic Pattern | Handler | 反映先 |
|---------------|---------|--------|
| `hems/sensors/{zone}/sensor/{dev}/{ch}` *(canonical — W3.8c)* | `_update_sensor` / `_update_event_channel` / `_update_state_channel` | `zones[zone].environment` / `.occupancy.motion_*` / `.occupancy.door_states` |
| `hems/sensors/{zone}/camera/{cam}/status` *(canonical — W3.8c)* | inline | `zones[zone].occupancy.count` |
| `hems/sensors/{zone}/activity/{mon}` *(canonical — W3.8c)* | inline | `zones[zone].occupancy.activity_*` / `.posture` |
| `office/{zone}/task_report/{id}` | inline | `zones[zone].events` (task_report) |
| `hems/pc/*` | `_update_pc_state` | `digital.pc_state` |
| `hems/services/{name}/{status,event}` | `_update_service_state` | `digital.services_state` |
| `hems/home/{zone}/{domain}/{entity}/state` | `_update_home_device` | `physical.home_devices` |
| `hems/gas/*` | `_update_gas_state` | `digital.gas_state` |
| `hems/perception/vlm/*` | `_update_vlm` | `zones[zone].occupancy.scene_*` / `vlm_*` |
| `hems/news/{daily,urgent}` | `_update_news_state` | `digital.news_state` |
| `hems/weather/{current,forecast,alerts}` | `_update_weather_state` | `physical.weather` |
| `hems/personal/biometrics/{provider}/{metric}` | `_update_biometric_state` | `user.biometrics` |
| `hems/personal/notes/{changed,stats}` | `_update_personal` → `_update_knowledge_state` | `digital.knowledge_state` |
| `hems/personal/knowledge/{changed,stats}` | `_update_personal` → `_update_external_knowledge_state` | `digital.knowledge_state.external_sources` |
| `hems/tapo/{vendor_ref}/state` | `_update_tapo_state` | `physical.home_devices` (HA 不要経路) |
| `zigbee2mqtt/{device}` | `_update_zigbee_state` | `physical.home_devices` (HA 不要経路) |

### 4.4 部分統合 / 未活用 (受信はされるが Brain で十分に利用されていない)

分類: **partial** = state は更新されるが履歴・分析なし / **unused** = state 更新まで届くが consume するルール・アクションなし。

| Topic | 公開元 | 分類 | 状態 |
|-------|--------|------|------|
| `hems/perception/vlm/model_swap` | perception | partial | `vlm_model_swap_active` フラグは管理されるが、swap イベント履歴の記録・分析はなし |
| `*/bridge/status` (各サービス) | 各 bridge | partial | bridge_connected フラグ更新のみで outage 履歴は残らない。topic 自体も実装間で不統一 + 4 ブリッジ未発行(refactor/2026-06-11 W3.3 で追跡) |
| `hems/gas/sheets/{name}` | gas-bridge | unused | `_update_gas_state` で受けるが、業務的に活用するルール無し |
| `hems/gas/drive/recent` | gas-bridge | unused | 同上 |
| `hems/services/{name}/event` (edge events) | OpenClaw bridge | partial | 受信はするがイベント駆動の即時ルールは無く、次の 30s サイクルで拾う(即時トリガ経路なし)。**例外: motion/presence** は `brain_mqtt._trigger_motion_event` 経由で即時 `AutomationEngine.trigger_event("motion:{device_id}")` される |

### 4.5 公開先のあるが Subscriber が居ない (Orphan publish)

(none — 2026-04-30 以降 weather-bridge が常時起動に統合済)

### 4.6 Verification

```bash
# Publishers
grep -rnE '\.publish\("(hems|zigbee2mqtt)' services/ --include="*.py"
# Subscribers (brain only — ルーティングは mqtt_router.py に分割済)
grep -nE 'parts\[0\] == |parts\[1\] == ' services/brain/src/world_model/mqtt_router.py
```

---

## 5. World Model 状態クラスとデータソース

| 領域 | クラス | 主要フィールド | データソース |
|------|--------|----------------|--------------|
| Physical | ZoneState | environment / occupancy / devices / events | `hems/sensors/+/sensor` / `camera` / `activity` *(canonical — W3.8c)* |
| Physical | EnvironmentData | temperature / humidity / co2 / pressure / light / voc / pm25 / soil_moisture / trends | `hems/sensors/+/sensor` *(canonical — W3.8c)* |
| Physical | OccupancyData | count / activity_* / posture / motion_* / door_states / inferred_occupied / scene_* / vlm_history | camera + activity + VLM + sensor |
| Physical | HomeDevicesState | lights / climate / covers / switches / binary_sensors / sensors / events | hems/home + hems/tapo + zigbee2mqtt |
| Physical | WeatherState | condition / temperature / humidity / wind_speed / forecast / alerts | hems/weather/* |
| Digital | PCState | cpu / memory / gpu / disk / temp / events | hems/pc/* |
| Digital | ServicesState | services dict / events | hems/services/* |
| Digital | GASState | calendar_events / free_slots / tasks / gmail_summary / sheets / drive_files | hems/gas/* |
| Digital | KnowledgeState | obsidian / external_sources | hems/personal/notes/* + knowledge/* |
| Digital | ShoppingState | items / due_items / pending_count | `digital_updates._update_shopping_state` が `hems/shopping/list`(backend が mutation 毎に publish する全 pending snapshot)から rebuild。recurring-due / departure reminder rule(`rules/shopping.py`)が消費。per-event(added/updated/purchased)は ShoppingClassifier + event_store 経由。backend DB が依然 SoT |
| Digital | NewsState | daily_summary / urgent_articles | hems/news/* |
| User | BiometricState | heart_rate / sleep / activity / stress / fatigue / spo2 / hrv / body_temp / respiratory_rate / steps | hems/personal/biometrics/* |
| User | ScreenTimeData | accumulated_minutes_today / last_active_ts | PC アクティビティ + biometric |
| User | SchedulePredictions | next_arrival_ts / next_wake_ts / weekday_arrival_str / arrival_stdev_min | ScheduleLearner 出力 |

### 5.1 Verification

```bash
grep -nE "^@dataclass|^class " services/brain/src/world_model/data_classes.py
# _update_* ハンドラは physical/digital/user_updates.py に分割済
grep -nE "^\s+def _update_" services/brain/src/world_model/{physical,digital,user}_updates.py
```

---

## 6. RuleEngine トリガー一覧

`services/brain/src/rule_engine.py` の `evaluate()`(環境/PC/ライトはインライン)+ `rules/` パッケージの
8 ドメインミキシン(biometric/gas/home/perception/services/shopping/weather/zigbee、`evaluate` が `actions.extend`
で集約)。閾値は `world_model.world_model` のモジュール定数 + `rules/config.py` の `RuleThresholds` の二系統。

### 6.1 Critical (常時実行、LLM 関係なく即時)

| Rule | 条件 |
|------|------|
| HR critical (sleep) | sleep 中 HR > `HR_CRITICAL_SLEEP` (150 bpm) |
| SpO2 critical | SpO2 < `SPO2_CRITICAL_LOW` (88%) |
| Temp critical | temp > `TEMP_CRITICAL_HIGH` (40℃) |

### 6.2 環境

| Rule | 条件 | アクション |
|------|------|-----------|
| CO2 high | CO2 > `CO2_HIGH` (1000) | create_task "換気" |
| Temp high | temp > `TEMP_HIGH` (28) | speak "AC ON" |
| Temp low | temp < `TEMP_LOW` (16) | speak "暖房 ON" |
| Humidity high | humidity > 70 | speak "除湿" |
| Humidity low | humidity < 30 | speak "加湿" |
| Pressure drop | 5hPa 下降 | speak "気象痛アラート" |
| VOC high sustained | VOC > 500 ppb × 120s | create_task "空気清浄" |
| Soil moisture low | < 25% かつ `HEMS_ENABLE_AUTO_WATER=true` | control_actuator (水ポンプ pulse) |

### 6.3 ライト

| Rule | 条件 | アクション |
|------|------|-----------|
| Light low | < 20 lx 持続 | control_light ON |
| Light high | > 50000 lx 持続 | control_light OFF |
| Circadian lighting | デフォルト有効 | 24h カーブで brightness/color_temp 調整 (1h クールダウン) |
| Absence lighting | 17:00-23:00 不在 | fake occupancy (ランダム ON/OFF) |

### 6.4 行動

| Rule | 条件 | アクション |
|------|------|-----------|
| Sedentary | posture sustained > `SEDENTARY_MINUTES` (60) | speak "ストレッチ" |
| Sleep detection | biometric sleep_state | lights OFF (HA 経由) |

### 6.5 PC

| Rule | 条件 |
|------|------|
| CPU high | > `PC_CPU_HIGH` (90%) |
| Memory high | > `PC_MEMORY_HIGH` (90%) |
| GPU temp high | > 85℃ |
| Disk high | > 90% |
| Screen time | > `SCREEN_TIME_MINUTES` (120) |

### 6.6 Verification

```bash
# インライン環境/PC/ライト rule + cooldown helper
grep -nE "^\s+def _check_|create_task|speak|control_" services/brain/src/rule_engine.py | head -100
# ドメイン rule (biometric/gas/home/perception/services/shopping/weather/zigbee)
grep -rnE "^\s+def _evaluate_\w+_rules" services/brain/src/rules/
```

---

## 7. AutomationEngine / EventAutomation

### 7.1 AutomationEngine トリガー種別

- `sensor_threshold`: device + channel + op + value + sustain_s
- `schedule`: cron / `time: "HH:MM"`
- `device_state`: device_id + state_key + equals
- `event`: 外部 `trigger_event()` から発火。event 名は完全一致か、ルール側に glob パターン（`motion:*` 等）を指定可能

### 7.2 即時 event 発火源

| Event | 発火源 |
|-------|--------|
| `motion:{device_id}` | `zigbee2mqtt/{device}` occupancy/motion=True、または `hems/home/{zone}/binary_sensor/{entity_id}/state` の motion/occupancy/presence on/detected/open |
| `wake_up` | biometric sleep_end_ts / morning camera (5:00–10:00) |

### 7.3 EventAutomation 対応イベント

| Event | 発火源 |
|-------|--------|
| wake_up | biometric sleep_end_ts / morning camera (5:00–10:00) |
| arrival | reconcile_presence + ScheduleLearner |
| departure | 同上 |
| scheduled | cron / 時刻指定 |

### 7.4 実装済み Action

- `morning_greeting` (LLM 生成)
- `news_briefing` (news-bridge から取得)
- `weather_report` (world_model.weather から)
- `weather_alert_announce` (警報級アラートのみ読み上げ。`DEFAULT_AUTOMATIONS` の wake_up 先頭)
- `task_planning` (LLM タスク生成)
- `speak_custom` (任意テキスト発話)
- `scene:{name}` (named scene 実行)

### 7.5 Verification

```bash
grep -nE "^\s+(def |async def |@register)" services/brain/src/automation_engine.py services/brain/src/event_automation.py
```

---

## 8. Bridge HTTP API (Brain Tool 未公開のもの)

各 bridge には FastAPI のエンドポイントが多数あり、内部用は `control_actuator`/`describe_device` 経由で吸収されているが、明示的にツール化されていないものを列挙。

| Bridge | Endpoint | ツール化状態 | 備考 |
|--------|----------|--------------|------|
| ha-bridge | `/api/device/{entity_id}` GET | ✓ `get_entity_status` | エンティティ単体クエリ(tool_handlers_home.py:128) |
| biometric-bridge | `/api/biometric/activity` GET | ✗ | 活動量ログ。現状は world_model 経由のみ |
| obsidian-bridge | `/api/notes/tags` GET | ✓ `list_note_tags` | タグ一覧(tool_handlers_external.py:73) |
| obsidian-bridge | `/api/notes/decision-log` POST | (内部利用) | brain が直接呼ぶ |
| obsidian-bridge | `/api/notes/learning-memo` POST | (内部利用) | 同上 |
| switchbot-bridge | `/api/devices/{id}/status` GET | ✗ | 個別状態 (リスト経由で取得可) |
| tapo-bridge | `/api/devices/{ref}/status` GET | ✗ | 同上 |
| perception | `/api/perception/cameras` GET | ✓ `list_cameras` | カメラ一覧(tool_handlers_perception.py:138) |
| perception | `/api/perception/vlm/status` GET | ✓ `get_vlm_status` | VLM サービス状態(tool_handlers_perception.py:153) |
| knowledge-bridge | `/api/knowledge/recent` GET | ✓ `get_recent_knowledge_changes` | 最近変更されたドキュメント(tool_handlers_external.py:298) |
| knowledge-bridge | `/api/knowledge/reindex` POST | ✗ | 管理用 |

### 8.1 Verification

```bash
grep -rnE "@app\.(get|post|put|delete)" services/*-bridge/src/ services/perception/src/ services/stt/src/
grep -nE '"[^"]+": "_handle_' services/brain/src/tool_dispatch.py
```

---

## 9. 環境変数 — env.example との整合性メモ

`env.example` は canonical な環境変数テンプレート。以下は過去に不足していたが現在は `env.example` に定義済みの変数群、および注意事項。

### 9.1 News / Knowledge / STT / Tapo / Weather / EventAutomation / VLM / BootLoad

これらの変数は現在 `env.example` で定義されている:

- `NEWS_*`, `HEMS_PORT_NEWS_BRIDGE`, `OLLAMA_URL`, `OLLAMA_MODEL`
- `KNOWLEDGE_*`, `EMBEDDING_*`, `RRF_K`
- `STT_*`, `HEMS_PORT_STT`
- `TAPO_*`, `HEMS_PORT_TAPO_BRIDGE`
- `WEATHER_PROVIDER`, `JMA_*`, `OWM_*`, `HEMS_WEATHER_*_INTERVAL`
- `EVENT_AUTOMATIONS`
- `VLM_*`, `BOOT_LOAD_*`

詳細は `env.example` を参照。

### 9.2 TTS / STT プロバイダー

| Type | 実装済みプロバイダー | 備考 |
|------|---------------------|------|
| TTS | `espeak`, `voicevox`, `voisona`, `edge-tts`, `aivoice` | |
| STT | `whisper`, `sherpa-onnx`, `qwen3-asr` | |

### 9.3 Approval / Feedback

承認・フィードバック機能に新規の環境変数は追加されていない。コードから参照されるのは既存の MQTT 接続情報と内部 token のみ:

- `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASS` — `feedback.py` / `approvals.py` で Brain への通知発行に使用
- `DASHBOARD_API_URL` / `BACKEND_URL` — `approval/client.py` で Backend `/approvals` API 呼び出しに使用
- `HEMS_INTERNAL_TOKEN` — brain chat server の `brain_auth_middleware` 認証、backend → brain proxy、voice-service / stt 間認証に使用

### 9.4 Verification

注意: env 変数は Python サービスだけでなく `infra/docker-compose.yml`、`infra/scripts/*.py`、
`services/frontend/`(Vite `VITE_*` 変数) からも参照される。以下は Python サービスに限定した
高速チェック。完全な突合は compose / scripts / frontend も含める。

```bash
# Python サービス側で参照されている env キー一覧（LOG_LEVEL のデフォルト値 "INFO" 等、
# 文字列リテラル由来の誤検出があるため要マニュアルレビュー）
grep -rnE 'os\.(getenv|environ\.get)\(' services/ --include="*.py" \
  | grep -oE "['\"][A-Z_][A-Z0-9_]*['\"]" | tr -d '\"' | sort -u > /tmp/code_env_keys.txt

# env.example で定義されているもの（コメントアウトも含む）
(grep -oE '^[A-Z_][A-Z0-9_]*=' env.example; grep -oE '^#\s*[A-Z_][A-Z0-9_]*=' env.example) \
  | sed 's/^#\s*//;s/=$//' | sort -u > /tmp/example_env_keys.txt

# code にあって env.example に無いもの
comm -23 /tmp/code_env_keys.txt /tmp/example_env_keys.txt

# compose / scripts / frontend からの参照（env.example only の正当性確認用）
grep -rnE '\$\{[A-Z_][A-Z0-9_]*(:-|:-)' infra/docker-compose.yml | grep -oE '[A-Z_][A-Z0-9_]*' | sort -u
grep -rnE 'os\.(getenv|environ\.get)\(' infra/scripts/ --include="*.py" | grep -oE "['\"][A-Z_][A-Z0-9_]*['\"]" | tr -d '\"' | sort -u
grep -rnE 'import\.meta\.env\.VITE_[A-Z_][A-Z0-9_]*|process\.env\.VITE_' services/frontend/src --include="*.ts" --include="*.tsx" | grep -oE 'VITE_[A-Z_][A-Z0-9_]*' | sort -u
```

---

## 10. ハイレベル整合性チェック チェックリスト

以下を四半期ごとに走らせて、ドキュメント追従状況を確認する。

- [x] `services/` 配下のディレクトリすべてが docker-compose に登録されているか? (orphan 検出) — **2026-06-30 検証: 3 件の orphan を検出したが、いずれも意図的**。`_common`(共有ライブラリ)、`data-bridge`(Phase 2 scaffold)、`mobile-android`(Docker 対象外 Android プロジェクト)。詳細は §1.2。
- [x] `tool_registry.py` の tool 数 == `tool_dispatch.py` の `TOOL_HANDLERS` 数? — **2026-05-25 検証: 58==58 完全一致**(§3.5)
- [x] `world_model/mqtt_router.py:update_from_mqtt` のすべての elif 分岐が公開されているトピックを網羅?(reducer は `{physical,digital,user}_updates.py`) — **2026-06-30 検証: 15 分岐すべてが §4.3/§4.4 で網羅済み**。canonical bridge status(`hems/ha/bridge/status` / `hems/biometric/bridge/status`)は個別ハンドル済み、その他 bridge status は §4.4 partial として記載。
- [x] 各 bridge で `os.getenv` されている環境変数すべてが `env.example` に記載?(未解決: `AUTOMATION_ENGINE_ENABLED` が未記載 — audit/2026-05-25/brain-core-loop.md) — **2026-06-30 検証: `services/` 全体を `env.example` と突合**。`AUTOMATION_ENGINE_ENABLED` は既に記載済み。未記載は 4 件発見(`CONFIG_DIR`、`HEMS_DRIFT_DELTA`、`HEMS_DRIFT_DETECTOR`、`HEMS_DRIFT_MIN_SAMPLES`)し `env.example` へ追記。`INFO` は `LOG_LEVEL` のデフォルト値からの誤検出。**残存乖離クリーンアップ: `env.example`-only の残りは compose / scripts / frontend / 将来 data-bridge で正当に使用されているため削除対象なし**。
- [x] CLAUDE.md の MQTT topic 一覧が §4 と一致?(2026-06-17: SwitchBot publisher topic を `hems/home/{zone}/sensor/switchbot.{device_id}_*/*` に修正)
- [x] `data-bridge` の orphan 状態(README のみの scaffold、src 無し)— weather-bridge は always-on 化で解消済

最終更新: 2026-06-30(Phase 2 adaptive thresholds テーブル・API・MQTT トピック追記、approval/feedback MQTT トピック追記、HITL/学習テーブルの所在明記、§10 ハイレベル整合性チェック 3 項検証完了、env.example へ CONFIG_DIR / HEMS_DRIFT_* 追記、S1/S2 実装済みを audit/2026-06-11/SUMMARY.md と §9.3 に反映、§9.4 検証コマンドを compose/scripts/frontend 対応に拡張、audit/2026-05-25/brain-core-loop.md の P1 リファクタ完了を反映)
