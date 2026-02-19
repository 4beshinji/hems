# Session Handoff: Wallet E2E Test + nginx Fix

**日時**: 2026-02-16
**ブランチ**: main
**コミット**: `c4c37cc`, `0ac3969`

---

## 成果サマリー

| # | 作業 | コミット | 影響ファイル |
|---|------|---------|-------------|
| 1 | Wallet ↔ Dashboard E2E テスト (F.3) | `c4c37cc` | `infra/scripts/test_wallet_dashboard_e2e.py` (新規) |
| 2 | Backend MQTT publish 認証修正 | `c4c37cc` | `services/dashboard/backend/routers/tasks.py` |
| 3 | nginx 遅延DNS解決 (リスタートループ修正) | `0ac3969` | `services/dashboard/frontend/nginx.conf` |
| 4 | TASK_SCHEDULE.md 更新 (F.3完了) | `0ac3969` | `docs/TASK_SCHEDULE.md` |
| 5 | CLAUDE.md ドキュメント乖離修正 (6件) | 本セッション | `CLAUDE.md` |
| 6 | CURRENT_STATE.md セッション追記 | 本セッション | `docs/handoff/CURRENT_STATE.md` |

---

## 1. Wallet ↔ Dashboard E2E テスト (F.3)

**ファイル**: `infra/scripts/test_wallet_dashboard_e2e.py`

F.1 (`test_wallet_integration.py`) が Wallet 単体の REST テストだったのに対し、
F.3 は **Backend が内部で Wallet を呼ぶクロスサービス経路** を検証する。

### テスト一覧 (20テスト / 5グループ)

| グループ | テスト数 | 検証内容 |
|----------|---------|---------|
| 1. Zone Multiplier | 6 | デバイス 2000 XP → 約2.0x乗数 → バウンティ約2015 (1000ではない) |
| 2. MQTT Task Report | 1 | タスク完了時に `office/{zone}/task_report/{id}` へ JSON パブリッシュ |
| 3. Concurrent (5並列) | 4 | 5タスク同時完了 → 5件の TASK_REWARD + 正しい残高 |
| 4. XP Accumulation | 5 | 2タスク完了 → XP ≥ 40 (各タスク create:10 + complete:20) |
| 5. No Assignment | 4 | accept なしで complete → バウンティ 0、TASK_REWARD なし |

### 実行方法

```bash
# Wallet ポートの一時公開が必要
docker run -d --rm --name soms-wallet-proxy \
  --network infra_soms-net -p 8003:8000 \
  alpine/socat tcp-listen:8000,fork,reuseaddr tcp-connect:wallet:8000

python3 infra/scripts/test_wallet_dashboard_e2e.py

# 終了後クリーンアップ
docker stop soms-wallet-proxy
```

### テスト設計上の注意

- **重複回避**: Backend のタスク重複検出 (Stage 2: zone + task_type 重複) を避けるため、各タスクに一意の `task_type` を使用
- **MQTT 認証**: paho-mqtt クライアントに `soms:soms_dev_mqtt` を設定
- **paho-mqtt**: ホストに `pip install paho-mqtt` が必要 (未インストール時は Test 2 がスキップ)

---

## 2. Backend MQTT publish 認証修正

**ファイル**: `services/dashboard/backend/routers/tasks.py`

### 問題

`_publish_task_report()` が `mqtt_publish.single()` を認証なしで呼んでいた。
Mosquitto は `allow_anonymous false` で設定されているため、全パブリッシュが
`Not authorized` で失敗していた。

### 修正内容

```python
# Before
mqtt_publish.single(topic, payload, hostname=MQTT_BROKER)

# After
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
mqtt_publish.single(
    topic, payload, hostname=MQTT_BROKER,
    auth={"username": MQTT_USER, "password": MQTT_PASS},
)
```

---

## 3. nginx 遅延DNS解決 (リスタートループ修正)

**ファイル**: `services/dashboard/frontend/nginx.conf`

### 問題

`soms-frontend` が `Restarting` ループに陥っていた。原因:

```
nginx: [emerg] host not found in upstream "voice-service"
```

nginx.conf の `/api/voice/` と `/audio/` ブロックが `proxy_pass` にホスト名を
直書きしており、nginx 起動時にDNS解決を試みる → `voice-service` 未起動時にクラッシュ。

### 修正内容

全 upstream を `/api/wallet/` と同じ `resolver` + 変数パターンに統一:

```nginx
# Before (起動時DNS解決 → クラッシュ)
proxy_pass http://voice-service:8000/api/voice/;

# After (リクエスト時DNS解決 → 未起動なら502)
resolver 127.0.0.11 valid=30s;
set $voice_upstream http://voice-service:8000;
proxy_pass $voice_upstream/api/voice/;
```

対象: `/api/voice/`, `/api/`, `/audio/` の3ブロック。

### 検証結果

| ルート | voice-service 停止時 | voice-service 起動時 |
|--------|---------------------|---------------------|
| `/` (SPA) | 200 | 200 |
| `/api/tasks/` | 200 | 200 |
| `/api/voice/` | 502 (クラッシュしない) | 200 |

---

## 4. CLAUDE.md ドキュメント乖離 (6件)

調査で発見した乖離を修正:

| # | 箇所 | 乖離内容 |
|---|------|---------|
| 1 | Service Ports | Wallet が 8003 と記載されているが実際は非公開 |
| 2 | MQTT Topics | `task_report` トピックが未記載 |
| 3 | nginx Routing | resolver パターンの説明なし |
| 4 | Inter-Service Comm | MQTT 認証の記載なし |
| 5 | Environment Config | `MQTT_USER` / `MQTT_PASS` が未記載 |
| 6 | Testing | `test_wallet_dashboard_e2e.py` が未記載 |

---

## 既知の残課題

- `soms-frontend` の nginx proxy rebuild が必要 (nginx.conf はビルド時コピー)。
  ソースの bind-mount ではないため、conf 変更時は `docker compose up -d --build frontend`
- `services/wallet-app/` に未コミットの tailwindcss vite プラグイン変更あり (本セッション対象外)
- `hems/` ディレクトリが untracked (本セッション対象外)

---

## テスト結果サマリー

| テストスイート | 結果 |
|--------------|------|
| F.1: `test_wallet_integration.py` | 18 pass, 0 fail, 1 skip (nginx) |
| F.3: `test_wallet_dashboard_e2e.py` | 20 pass, 0 fail, 0 skip |
