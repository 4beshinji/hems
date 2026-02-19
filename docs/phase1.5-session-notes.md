# Phase 1.5 — デバイス出資モデル & 比例配分リワード: セッションノート

## ステータス: 全テスト完了 ✓

**コミット**: `53a6157` (pushed to `origin/main`)
**日付**: 2026-02-16

---

## 完了済み

### Wallet サービス (衝突なし — テスト可能)

| ファイル | 変更内容 |
|----------|---------|
| `services/wallet/src/models.py` | Device に 11 カラム追加 (shares, metrics, utility_score) + DeviceStake, FundingPool, PoolContribution テーブル |
| `services/wallet/src/schemas.py` | 15 新 Pydantic スキーマ + DeviceResponse 拡張 |
| `services/wallet/src/services/stake_service.py` | **NEW** — open/close/buy/return/distribute_reward |
| `services/wallet/src/services/pool_service.py` | **NEW** — create_pool/contribute/activate_pool |
| `services/wallet/src/services/xp_scorer.py` | compute_contribution_weight (hw × utility) + grant_xp_to_zone_weighted |
| `services/wallet/src/routers/stakes.py` | **NEW** — Model A: 6 エンドポイント (funding open/close, buy/return, device stakes, portfolio) |
| `services/wallet/src/routers/pools.py` | **NEW** — Model B: 6 エンドポイント (admin CRUD + contribute + activate, public list) |
| `services/wallet/src/routers/devices.py` | heartbeat → distribute_reward() 比例配分 + metrics 更新 + utility-score EP |
| `services/wallet/src/main.py` | relay_node/remote_node seed + stakes/pools router 登録 |

### Brain サービス (他ワーカーと衝突あり — 要マージ)

| ファイル | 変更内容 | 衝突リスク |
|----------|---------|-----------|
| `services/brain/src/device_registry.py` | utility_score/\_last\_used + record_zone_action + decay_utility_scores | **なし** |
| `services/brain/src/wallet_bridge.py` | **NEW** — MQTT→Wallet heartbeat 中継 | **なし** |
| `services/brain/src/main.py` | WalletBridge 統合 + utility 記録 + decay loop | **あり** (event_store ワーカーと同一ファイル) |
| `infra/docker-compose.yml` | brain に WALLET_SERVICE_URL 追加 | **あり** (event_store ワーカーが depends_on, DATABASE_URL 追加) |

---

## 他ワーカーの作業 (未コミット)

別ワーカーが Event Store 機能を実装中:
- `services/brain/src/event_store/` (新ディレクトリ: `__init__.py`, `models.py`, `database.py`, `writer.py`, `aggregator.py`)
- `services/brain/requirements.txt` に `sqlalchemy[asyncio]`, `asyncpg` 追加
- `services/brain/src/main.py` に EventWriter/HourlyAggregator 統合
- `infra/docker-compose.yml` に brain の depends_on postgres + DATABASE_URL 追加

### マージ時の注意点

**`services/brain/src/main.py`** — 両方のワーカーが以下を変更:
1. import 行 (Phase 1.5: `wallet_bridge`, Event Store: `event_store`)
2. `Brain.__init__` (Phase 1.5: `self.wallet_bridge`, Event Store: `self.event_writer`)
3. `_process_mqtt_message` (Phase 1.5: heartbeat→Wallet転送, Event Store: sensor→EventWriter記録)
4. `cognitive_cycle` 末尾 (Phase 1.5: utility 記録, Event Store: decision 記録 + `elapsed` 移動)
5. `run()` (Phase 1.5: WalletBridge init + decay loop, Event Store: event_store init)

**重要**: Event Store が `elapsed = time.time() - cycle_start` を cognitive_cycle 内で上方に移動している。Phase 1.5 の utility 記録コードがその後に来るため、マージ後に `elapsed` 計算の重複がないか確認すること。

**`infra/docker-compose.yml`** — 両方が brain service の environment セクションを変更:
- Phase 1.5: `WALLET_SERVICE_URL=http://wallet:8000`
- Event Store: `DATABASE_URL=postgresql+asyncpg://...` + depends_on postgres

両方とも追加なので行単位では衝突しないが、コンテキスト行の位置によりGitが衝突と判定する可能性あり。

---

## テスト結果

### Wallet E2E: 全 52 テスト PASSED (2026-02-16)

テストスクリプト: `infra/scripts/test_phase1_5.py`

| カテゴリ | 結果 |
|----------|------|
| 1. Setup (wallets + seed) | PASS |
| 2. Device Registration (新カラム確認) | PASS |
| 3. Open Funding | PASS |
| 4. Buy Shares (残高移転確認) | PASS |
| 5. Stakeholders (owner 50% + investor 10%) | PASS |
| 6. Heartbeat #1 (timestamp 初期化) | PASS |
| 7. Portfolio | PASS |
| 8. Utility Score (set + clamp 0.5-2.0) | PASS |
| 9. Heartbeat with metrics body | PASS |
| 10. Share Return (buyback + refund) | PASS |
| 11. Error cases (4 パターン) | PASS |
| 12. Close Funding (reclaim + buy禁止) | PASS |
| 13. Pool Model B (create → contribute → funded → activate → shares割当) | PASS |

### Brain 統合テスト: 全 PASSED (2026-02-16)

| テスト | 結果 |
|--------|------|
| Brain 起動 (Event Store + WalletBridge + decay loop) | PASS |
| MQTT heartbeat → WalletBridge → Wallet 転送 | PASS (metrics 更新確認) |
| 比例配分 (95:5 → 62:3 = 65 total) | PASS |
| WalletBridge 300s スロットル | PASS (2回目未転送) |
| DeviceRegistry record_zone_action (+0.3/+0.5) | PASS |
| DeviceRegistry utility clamp (max 2.0) | PASS |
| DeviceRegistry decay (7d grace → 30d → 0.5) | PASS |
| to_dict utility_score 含む | PASS |
| XP contribution_weight (8 パターン, 0.5~4.0) | PASS |

### テスト手順参考

### 1. スキーマ検証 ✅ (wallet コンテナ起動成功で確認済み)

### 2. 出資フロー E2E

```bash
# ウォレット作成
curl -s -X POST localhost:8003/wallets/ -H 'Content-Type: application/json' -d '{"user_id":1}'
curl -s -X POST localhost:8003/wallets/ -H 'Content-Type: application/json' -d '{"user_id":2}'

# user 2 に初期残高 (task reward で代用)
curl -s -X POST localhost:8003/transactions/task-reward -H 'Content-Type: application/json' \
  -d '{"user_id":2,"amount":10000,"task_id":999,"description":"seed"}'

# デバイス登録
curl -s -X POST localhost:8003/devices/ -H 'Content-Type: application/json' \
  -d '{"device_id":"test_01","owner_id":1,"device_type":"sensor_node"}'

# 出資開始 (50 shares @ 100/share)
curl -s -X POST localhost:8003/devices/test_01/funding/open -H 'Content-Type: application/json' \
  -d '{"owner_id":1,"shares_to_list":50,"share_price":100}'

# shares 購入 (user 2)
curl -s -X POST localhost:8003/devices/test_01/stakes/buy -H 'Content-Type: application/json' \
  -d '{"user_id":2,"shares":10}'

# stakeholder 確認
curl -s localhost:8003/devices/test_01/stakes | python3 -m json.tool

# heartbeat × 2 (5分+ 間隔)
curl -s -X POST localhost:8003/devices/test_01/heartbeat
# ... wait 310s ...
curl -s -X POST localhost:8003/devices/test_01/heartbeat

# 残高確認 (owner=1: 90% 報酬 + 購入代金, investor=2: 10% 報酬)
curl -s localhost:8003/wallets/1 | python3 -m json.tool
curl -s localhost:8003/wallets/2 | python3 -m json.tool
```

### 3. 返却テスト

```bash
curl -s -X POST localhost:8003/devices/test_01/stakes/return -H 'Content-Type: application/json' \
  -d '{"user_id":2,"shares":5}'

# user 2: 残高に share_price × 5 = 500 が追加されていること
curl -s localhost:8003/wallets/2 | python3 -m json.tool

# ポートフォリオ
curl -s localhost:8003/users/2/portfolio | python3 -m json.tool
```

### 4. プール (Model B) テスト

```bash
# プール作成
curl -s -X POST localhost:8003/admin/pools -H 'Content-Type: application/json' \
  -d '{"title":"温湿度センサー3号機","goal_jpy":3000}'

# 出資記録
curl -s -X POST localhost:8003/admin/pools/1/contribute -H 'Content-Type: application/json' \
  -d '{"user_id":10,"amount_jpy":1500}'
curl -s -X POST localhost:8003/admin/pools/1/contribute -H 'Content-Type: application/json' \
  -d '{"user_id":11,"amount_jpy":1500}'

# status = funded 確認
curl -s localhost:8003/admin/pools/1 | python3 -m json.tool

# activate (デバイスリンク + shares 割当)
curl -s -X POST localhost:8003/admin/pools/1/activate -H 'Content-Type: application/json' \
  -d '{"device_id":"test_01"}'
```

### 5. XP 重み付けテスト

```bash
# power_mode=DEEP_SLEEP のデバイスを登録
curl -s -X POST localhost:8003/devices/ -H 'Content-Type: application/json' \
  -d '{"device_id":"battery_01","owner_id":1,"device_type":"sensor_node","topic_prefix":"office/main/sensor/battery_01"}'

# heartbeat で power_mode 設定
curl -s -X POST localhost:8003/devices/battery_01/heartbeat -H 'Content-Type: application/json' \
  -d '{"power_mode":"DEEP_SLEEP"}'

# XP grant して weighted 確認
curl -s -X POST localhost:8003/devices/xp-grant -H 'Content-Type: application/json' \
  -d '{"zone":"main","task_id":1,"xp_amount":10}'
```

### 6. Brain テスト (マージ後)

```bash
docker compose -f infra/docker-compose.yml up -d --build brain
docker logs -f soms-brain
# 確認: "Event store and aggregator started" + WalletBridge 初期化
# heartbeat が Wallet に転送されること (utility_score 添付)
```

---

## 完了

Phase 1.5 実装・テスト全完了。Event Store ワーカーとのマージも問題なし。
