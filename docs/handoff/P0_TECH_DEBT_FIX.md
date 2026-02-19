# P0 技術的負債修正 — 作業状態

**作成日**: 2026-02-13
**ブランチ**: main (未コミット)
**状態**: 実装完了・部分検証済み・テスト途中で中断

---

## 概要

ゼロベース技術的負債分析で発見された P0（最優先）3項目を修正した。
コア4サービス (mosquitto, brain, backend, postgres) は再起動・検証済み。
残りサービスの再起動と E2E テストは未完了。

---

## 修正1: Task モデル DB マイグレーション

**問題**: `create_all()` は既存テーブルにカラムを追加できない。`assigned_to`/`accepted_at` が既存 DB に反映されず、タスク受諾が永続化されない。

**対応ファイル**:
- `services/dashboard/backend/main.py` — `_migrate_add_columns()` 追加

**内容**:
- `inspect(conn)` で各テーブルのカラム存在をチェック
- 不在なら `ALTER TABLE ... ADD COLUMN` を実行
- 対象: `tasks.assigned_to`, `tasks.accepted_at`, `users.display_name`, `users.is_active`, `users.credits`, `users.created_at`
- Alembic 導入 (P1) までの暫定措置

**検証**: backend 再起動済み、PostgreSQL ログで `assigned_to`/`accepted_at` を含む SELECT 文を確認。

---

## 修正2: スレッド安全性 (Brain + Perception)

**問題**: paho-mqtt コールバックは別スレッドで実行されるが、`asyncio.Event.set()` / `asyncio.Future.set_result()` を直接呼んでいた（非スレッドセーフ → データ競合の可能性）。

**対応ファイル**:

| ファイル | 変更内容 |
|---------|---------|
| `services/brain/src/main.py` | `self._loop` を `run()` で保存。`on_message` が `call_soon_threadsafe` で `_process_mqtt_message` を asyncio スレッドにディスパッチ。WorldModel アクセスもスレッドセーフに。 |
| `services/brain/src/mcp_bridge.py` | `self._loop` を `call_tool()` で保存。`handle_response` の `future.set_result`/`set_exception` を `call_soon_threadsafe` 経由に変更。 |
| `services/perception/src/image_requester.py` | `self._loop` を `request()` で保存。`_on_message` の Future 操作を `call_soon_threadsafe` 経由に変更。`get_event_loop()` → `get_running_loop()` に修正。 |

**検証**: brain 再起動済み、MQTT 接続 `result code Success`、認知サイクル正常動作。perception は未再起動。

---

## 修正3: MQTT 認証 + PostgreSQL バインドアドレス制限

### 3a: MQTT 認証

**問題**: `allow_anonymous true` で `0.0.0.0:1883` に公開。ネットワーク上の誰でもデバイス制御コマンドを送信可能。

**対応ファイル**:
- `infra/mosquitto/mosquitto.conf` — `allow_anonymous false` + `password_file`
- `infra/mosquitto/passwd` — **新規** ハッシュ済みパスワードファイル (user: `soms`)
- `infra/docker-compose.yml` — passwd マウント + `MQTT_USER`/`MQTT_PASS` 環境変数
- `infra/docker-compose.edge-mock.yml` — `MQTT_USER`/`MQTT_PASS` 環境変数
- `env.example` / `.env` — `MQTT_USER=soms` / `MQTT_PASS=soms_dev_mqtt` 追加

**全 MQTT クライアント更新 (12箇所)**:

| クライアント | ファイル | 認証取得方式 |
|---|---|---|
| Brain | `services/brain/src/main.py` | `os.getenv("MQTT_USER")` |
| Perception (publisher) | `services/perception/src/state_publisher.py` | `os.getenv("MQTT_USER")` |
| Perception (requester) | `services/perception/src/image_requester.py` | `os.getenv("MQTT_USER")` |
| Virtual Edge | `infra/virtual_edge/src/main.py` | `os.getenv("MQTT_USER")` |
| ESP32 実機 | `edge/lib/soms_mcp.py` | `config.json` → `mqtt_user`/`mqtt_pass` |
| E2E テスト (full) | `infra/scripts/e2e_full_test.py` | `os.getenv("MQTT_USER", "soms")` |
| E2E テスト (dedup) | `infra/scripts/e2e_dedup_test.py` | 同上 |
| テスト (world_model) | `infra/scripts/test_world_model.py` | 同上 |
| テスト (human_task) | `infra/scripts/test_human_task.py` | 同上 |
| カメラシミュレータ | `edge/test-edge/camera-node/simulator.py` | `os.getenv("MQTT_USER")` |
| virtual_device.py | `virtual_device.py` | `os.getenv("MQTT_USER", "soms")` |
| trigger_humidity.py | `trigger_humidity.py` | 同上 |

### 3b: PostgreSQL バインドアドレス

**問題**: `0.0.0.0:5432` にデフォルトパスワードで公開。

**対応**: `infra/docker-compose.yml` で `"5432:5432"` → `"127.0.0.1:5432:5432"`

### 検証結果

| テスト | 結果 |
|--------|------|
| MQTT 認証なし接続 | `Connection Refused: not authorised` **(PASS)** |
| MQTT 認証あり接続 | 成功 **(PASS)** |
| PostgreSQL ポートバインド | `127.0.0.1:5432` **(PASS)** |
| Brain MQTT 接続 | `result code Success` **(PASS)** |

---

## 残作業

### 1. コンテナ再起動（必須）

perception と virtual-edge はまだ旧コードで動いている:

```bash
# perception (MQTT auth + thread safety)
docker compose -f infra/docker-compose.yml up -d --force-recreate perception

# virtual-edge (MQTT auth) — edge-mock compose 使用
docker compose -f infra/docker-compose.yml -f infra/docker-compose.edge-mock.yml \
  up -d --force-recreate virtual-edge
```

### 2. E2E テスト

```bash
MQTT_USER=soms MQTT_PASS=soms_dev_mqtt python3 infra/scripts/e2e_full_test.py
```

### 3. タスク受諾フロー手動テスト

```bash
# 1. タスク作成
curl -X POST http://localhost:8000/tasks/ \
  -H 'Content-Type: application/json' \
  -d '{"title":"test accept","description":"P0 test","bounty_gold":500,"urgency":2}'

# 2. 受諾 (task_id は上記レスポンスの id を使用)
curl -X PUT http://localhost:8000/tasks/{id}/accept \
  -H 'Content-Type: application/json' -d '{"user_id": 1}'

# 3. 完了
curl -X PUT http://localhost:8000/tasks/{id}/complete
```

### 4. コミット（推奨分割）

| コミット | 対象ファイル |
|---------|------------|
| `fix: add thread safety for paho-mqtt callbacks` | brain/main.py, mcp_bridge.py, image_requester.py |
| `fix: add MQTT broker authentication` | mosquitto.conf, passwd, docker-compose*, 全クライアント12箇所, env* |
| `fix: add DB migration for task assignment columns` | backend/main.py |
| `fix: restrict PostgreSQL to localhost binding` | docker-compose.yml |

---

## Docker 状態（中断時点）

| コンテナ | 状態 | P0 反映 |
|---------|------|---------|
| soms-mqtt | 再起動済み | 認証有効 |
| soms-brain | 再起動済み | スレッド安全性 + MQTT auth |
| soms-backend | 再起動済み | DB マイグレーション |
| soms-postgres | 再起動済み | 127.0.0.1 バインド |
| soms-perception | **要再起動** | 未反映 |
| soms-virtual-edge | **要再起動** | 未反映 |
| その他 (frontend, voice, wallet, ollama, mock-llm, voicevox) | 変更なし | — |
