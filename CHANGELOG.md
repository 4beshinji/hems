# HEMS Changelog

ユーザー向けの **運用上の注意・破壊的変更・必須マイグレーション** をここに記録する。
細かい機能追加は git log を参照。

ステータス凡例: ⚠️ = 既存環境で手作業が必要 / 🆕 = 純粋な新機能 / 🔧 = リファクタ・内部改善

---

## 2026-06-30

### 🆕 Phase 2 適応的閾値とドリフト検知

- `river` を依存関係に追加し、オンライン・ドリフト検知基盤を構築。
- Brain に `adaptive_thresholds` パッケージ (`MetricDriftTracker` / `AdaptiveThresholdManager` / `ThresholdAdjuster` / `ThresholdClient`) を追加。
- `RuleThresholds` を動的にラップする `AdaptiveRuleThresholds` を追加。rule engine と world model は自動的に動的閾値を参照する。
- Backend に `threshold_drift_log` / `threshold_adjustments` テーブルと `/thresholds` REST エンドポイントを追加。
- Brain event_store に `drift_detections` テーブルを追加。
- WorldModel のセンサー更新時に `AdaptiveThresholdManager` へ値をフィードし、ドリフト検出時に backend へ提案を送信。
- 日次メンテナンス (`_maybe_daily_maintenance`) で未送信の閾値提案を backend へフラッシュし、承認済みオフセットを再読み込み。
- 介入効果判定 (`_efficacy_eval_loop`) から `ThresholdAdjuster` を経由して閾値オフセットを更新。
- Frontend に `/settings/thresholds` ページと `ThresholdProposalCard` コンポーネントを追加。閾値変更提案の承認/棄却と適用履歴表示に対応。
- テスト: `tests/test_backend_adaptive_thresholds_router.py` / `services/brain/tests/adaptive_thresholds/` を追加。

### 🆕 Phase 1 フィードバック収集と介入効果測定

- Backend に `/feedback` REST エンドポイント (`POST /feedback`、`POST /feedback/trajectory`、`GET /feedback/*`) を追加。
- Brain event_store に `agent_feedback` / `agent_trajectories` / `intervention_efficacy` テーブルを追加し、`EventWriter` が書き込めるよう拡張。
- Brain `feedback` パッケージ (`FeedbackCollector` / `ImplicitFeedbackDetector` / `OutcomeRewardCalculator` / `TrajectoryRecorder`) を追加。`FeedbackCollector` は MQTT 経由で Backend からのフィードバックを受け取り event_store に複製; `OutcomeRewardCalculator` / `TrajectoryRecorder` / 完全な暗黙フィードバック配線は Phase 2 に予約。
- Frontend のタスク/発話/アラート/承認カードに 👍/👎/取り消し/再実行 フィードバックボタンを追加。
- `tests/test_backend_feedback_router.py` / `services/brain/tests/feedback/` / `tests/test_feedback_integration.py` でパイプラインを検証。

### 🆕 Phase 0 HITL 承認キュー (Frontend + Backend + Brain 統合)

- ダッシュボードに `/approvals` ページを追加。承認待ちアクションの一覧、承認/修正/棄却を UI 上で操作可能。
- Brain `ApprovalGate` → Backend `/approvals` API → Frontend 承認キュー のエンドツーエンドフローを統合。
- 棄却・期限切れ時のロールバック補償 (`RollbackPlanner` / `RollbackExecutor`) を統合テストで検証。
- Backend `mark_executed` が `modified` 決定も実行完了として記録できるよう修正。
- `tests/test_approval_integration.py` に承認 → 実行、修正 → 実行、棄却 → ロールバックの統合テストを追加。

## 2026-06-17

### 🔧 ドキュメント・env 既定値の整備

- README を単独でPJの目的と機能が分かる形にリライト。fork 元言及を削除。
- `env.example` / `infra/docker-compose.yml` / `services/voice/src/provider_factory.py` の既定値を統一:
  - TTS 既定値を `voicevox`（speaker 47、fallback `espeak`）に統一（`style-bert-vits2` プレースホルダーを削除）
  - LLM 既定値を `ollama` + `gemma4:e4b-it-q8_0` に統一
  - `BRAIN_CHAT_PORT` 既定値を `8080` に統一
- `style-bert-vits2` の未実装プレースホルダーを `env.example` / `docker-compose.yml` / 各ドキュメントから削除。
- コアサービスに `weather-bridge` を追加し、関連ドキュメントを更新。

## 2026-06-11

### ⚠️ PostgreSQL が既定 DB に変更 (W4.5' / W4.6)

SQLite から PostgreSQL 16 へ既定 DB を切り替え。既存 SQLite 環境の移行には `infra/scripts/migrate_sqlite_to_pg.py` を使用。

- `make quickstart` で `.env` + ランダムシークレット + PostgreSQL を自動セットアップ
- SQLite 軽量モードは `make quickstart-sqlite` / `docker-compose.sqlite-lite.yml` で引き続き利用可

### ⚠️ 内部サービス認証 `HEMS_INTERNAL_TOKEN` 導入 (W1.1 / W3.9)

voice-service / stt / 各 bridge の変更系エンドポイントに Bearer 認証を導入。`.env` で `HEMS_INTERNAL_TOKEN` を設定すると、brain/backend からの内部呼び出しと bridge 間呼び出しに `Authorization: Bearer <token>` が必要になる。未設定時はスキップ（dev モード）。

### ⚠️ `BACKEND_API_KEY` による dashboard API 認証再導入 (W1.1)

空の場合は LAN-trusted 動作。設定時は dashboard router 群と brain→backend 呼び出しで Bearer 検証。

### 🆕 `make quickstart` / `make quickstart-sqlite`

`.env` 自動生成 + base image ビルド + core stack 起動を1コマンドで実行。

### 🔧 Brain / Backend / Frontend 大規模リファクタ (W1–W5)

- Brain: `tool_registry` / `tool_schemas` / `tool_handlers_*` 分離、`world_model` mixin 化、ルールエンジン整理
- Backend: Device Registry 強化、Automation Engine、Scene、Mobile、BridgeStatus、Timeseries/Timeline 等を追加
- Frontend: vitest + MSW 導入、Context 分割、VRM dispose、環境変数統一
- Mosquitto: ACL 強化、全内部サービスを `127.0.0.1` バインド

### ⚠️ `get_weather` ツールを HA profile から独立

`get_weather` は `weather-bridge`（常時起動）由来のツールとなった。`ha` profile 非依存。

---

## 2026-05-01

### ⚠️ Mosquitto ACL / passwords 変更時は `docker compose restart mosquitto` 必須

`infra/mosquitto/acl.txt` または `infra/mosquitto/entrypoint.sh` (passwords.txt 生成スクリプト) を編集した場合、**mosquitto コンテナを再起動するまで変更が反映されない**。

```bash
docker compose restart mosquitto
```

理由: mosquitto は起動時に ACL とパスワードファイルを読み込み、以後はメモリ上のテーブルを参照する。ホスト側ファイルを書き換えても再読込しない。今回の weather-bridge 追加 (`hems-weather` user) では、ACL 編集後に mosquitto を再起動するまで `not authorised` になっていた。

該当する変更例:
- 新しい bridge service を追加して新しい MQTT user を割り当てるとき
- 既存 user の topic 権限を変えるとき
- パスワードを更新するとき

### 🆕 weather-bridge を常時起動として compose に追加

- `services/weather-bridge` を `infra/docker-compose.yml` に登録 (profile 無しで常時起動)
- mosquitto に `hems-weather` user 追加 (上記 ACL 注意点参照)
- env: `WEATHER_PROVIDER` (`jma` デフォルト) / `JMA_AREA_CODE` / `JMA_DETAIL_CODE` / OWM 系
- これにより `world_model.weather` が常に充填され、`get_weather` ツールおよび EventAutomation の `weather_report` action が実データで動作

詳細は `docs/wiring-gap-06-data-flow-consolidation.md` を参照（gap-05 は gap-06 に統合済み）。

### ⚠️ backend Device テーブルに `link_quality` / `last_seen_reported` 追加 — 既存 DB 要再生成

`services/backend/models.py:Device` に下記カラムを追加:

| カラム | 型 | 用途 |
|--------|-----|------|
| `link_quality` | INTEGER | Z2M LQI (0-255) / SwitchBot RSSI |
| `last_seen_reported` | TIMESTAMP TZ | デバイス自身が報告した最終アクセス時刻 (Z2M `last_seen`) |

backend は alembic 未導入 (`Base.metadata.create_all` のみ) のため、**既存 DB は新カラムを自動追加しない**。dev 環境では DB を削除して再生成:

```bash
docker compose stop backend brain
docker compose rm -f backend brain
docker volume rm hems_hems_backend_data
docker compose up -d --build backend brain
```

prod 想定なら手動マイグレーション:
```sql
ALTER TABLE device ADD COLUMN link_quality INTEGER;
ALTER TABLE device ADD COLUMN last_seen_reported TIMESTAMP WITH TIME ZONE;
```

### ⚠️ 古いコンテナボリュームの所有者問題 (brain / backend)

過去のイメージで作られた `hems_hems_brain_data` / `hems_hems_backend_data` は **root 所有のまま残ることがある**。Dockerfile の chown は **新規 (空) ボリュームの初期化時にのみ反映**され、既存ボリュームには影響しない。

症状: `event_store init failed: unable to open database file` が brain ログに出る、または backend が SQLite に書込めない。

復旧:

```bash
# ホットフィックス (再起動不要)
docker exec -u root hems-brain chown -R appuser:appgroup /app/data
docker compose restart brain

# 根治 (volume を捨てて Dockerfile の所有権で再生成)
docker compose stop brain
docker compose rm -f brain
docker volume rm hems_hems_brain_data
docker compose up -d brain
```

Dockerfile (`services/brain/Dockerfile` / `services/backend/Dockerfile`) には `RUN mkdir -p /app/data && chown appuser:appgroup /app/data` を含めてあるため、新規環境では問題は発生しない。

### 🆕 Brain ツール 4 件追加

| Tool | profile | 用途 |
|------|---------|------|
| `get_power_consumption` | tapo | Tapo P110/P115 の瞬時電力 (W) — `device_id` 省略時は `asyncio.gather` で全プラグ並列取得 |
| `get_entity_status` | ha | HA 単一エンティティの即時 state |
| `list_processes` | localcraw | PC プロセス一覧 (CPU/メモリソート、name フィルタ) |
| `get_recent_emails` | gas | Gmail スレッドを sender/subject/unread でフィルタ |

`get_tools()` / `get_chat_tools()` のシグネチャに `gas_enabled` / `tapo_enabled` 引数を追加。chat allowlist にも 4 ツールを反映済み。

### 🆕 RuleEngine に閾値追加

| 環境変数 | デフォルト | 用途 |
|----------|-----------|------|
| `HEMS_PROC_CPU_HIGH` | 90 | プロセス単体の CPU 高負荷判定 (%) |
| `HEMS_PROC_CPU_SUSTAIN_S` | 300 | 上記の継続時間 (秒) |
| `HEMS_PROC_MEM_HIGH_GB` | 4.0 | プロセス単体のメモリ高使用判定 (GB) |
| `HEMS_PROC_COOLDOWN_S` | 1800 | 同一プロセス再アラートまで (秒) |
| `HEMS_DEVICE_BATTERY_LOW` | 10 | デバイス低バッテリー警告閾値 (%) |
| `HEMS_DEVICE_LQI_LOW` | 50 | Z2M リンク品質低下閾値 (LQI 0-255) |
| `HEMS_DEVICE_STALE_HOURS` | 24 | デバイス無応答警告までの時間 (h) |
| `HEMS_GMAIL_VIP_SENDERS` | (空) | カンマ区切り、含まれる送信者の Gmail event を severity=2 に昇格 |
| `HEMS_GITHUB_VIP_REPOS` | (空) | カンマ区切り、含まれる repo の GitHub event を severity=2 に昇格 |

### 🔧 内部リファクタ

- `_parse_iso_ts` を `services/brain/src/brain_utils.py:parse_iso_ts` に集約 (device_dispatcher / rule_engine の重複を解消)
- `_handle_get_power_consumption` の全プラグ列挙を `asyncio.gather` 化 (直列 N×5s → 並列 1×5s)
- `_run_rule_actions` で low-power mode と VLM swap 中は persona rewrite を skip (応答性優先)

### 🗑️ Cleanup

- `services/sentinel/` 削除 (中身が `__pycache__` のみのデッドコード)
- `services/data-bridge/` に README.md 追加 (Phase 2 placeholder の意図明示)

---

## 履歴 (2026-04 以前)

git log 参照。
