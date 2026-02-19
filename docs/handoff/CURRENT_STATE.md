# SOMS 作業状態ドキュメント — マルチワーカー引き継ぎ用

**更新日時**: 2026-02-16 (Session N 更新)
**ブランチ**: main
**HEAD**: `0f5b1f4` (feat: add investment UI to wallet-app PWA)

**Session N の成果**:
- Wallet App 出資 UI 追加: Invest ページ (3タブ: Portfolio/Devices/Pools) + DeviceDetail ページ
- Tailwind CSS v4 ビルド修正: `@tailwindcss/vite` プラグイン追加 (ユーティリティクラス未生成問題を解決)
- BottomNav に 5番目「Invest」タブ追加, App.tsx にルート追加
- API クライアント `stakes.ts`: 6 エンドポイント (getDevices, getDeviceFunding, buyShares, returnShares, getPortfolio, getPools)

---

## 0. セッション履歴

| セッション | 主な成果 | 代表コミット |
|-----------|---------|-------------|
| G | Brain 7層改善 (スレッド安全性, ReAct ガード, Sanitizer 強化) | `091f360` |
| H | ウォレット分離設計, ISSUES 対応 (M-4,M-6,M-8~M-11) | `246ffc6`, `5abaa10` |
| I | タスク完了レポート機能, 並行開発基盤 (WORKER_GUIDE, API_CONTRACTS) | `e07602e`, `c0467ac` |
| J | 全 CRITICAL/HIGH ISSUES 解消, healthcheck 追加, フロントエンド修正 | `c689908` |
| K | QR リワードフロー, wallet-app デプロイ, Brain 堅牢化, MQTT 認証 | `8dabbe2` |
| L | Phase 1.5 出資モデル, Event Store, Brain WalletBridge 統合 | `53a6157`, `2fbb556` |
| M | Wallet↔Dashboard E2E テスト, MQTT auth 修正, nginx DNS修正, ドキュメント更新 | `c4c37cc`, `0ac3969` |
| N | Wallet App 出資 UI (Invest/DeviceDetail ページ), Tailwind v4 ビルド修正 | `0f5b1f4` |

---

## 1. ISSUES.md — 全32件の解決状態

### 全件解決済み (32/32 = 100%)

| 重要度 | 件数 | 解決済みID |
|--------|------|-----------|
| CRITICAL (4) | 4/4 | C-1, C-2, C-3, C-4 |
| HIGH (8) | 8/8 | H-1~H-8 (H-5: Sanitizer timing 修正済み, H-6: WalletBadge 削除済み, H-7/H-8: Session J 修正) |
| MEDIUM (12) | 12/12 | M-1~M-12 (M-1: PG 127.0.0.1 制限, M-2: MQTT 認証有効化, M-5: Perception networks 除去) |
| LOW (8) | 8/8 | L-1~L-8 (L-1: Perception tag 固定, L-2: build-essential 除去, L-7: healthcheck 全12サービス) |

**注**: ISSUES.md ファイル自体は 2026-02-13 時点の記載のまま。内容は全件対応完了。

---

## 2. Phase 1.5 — デバイス出資モデル & 比例配分リワード

### 経済モデル概要

```
オーナー → デバイス登録 (100 shares) → 出資募集 open → N shares 公開
投資家 → shares 購入 (SOMS がオーナーへ) → インフラ報酬が shares 比率で自動配分
退出時 → shares 返却 → システムが share_price で買戻し (流動性保証)
```

### 2 つの出資モデル

| モデル | 対象 | フロー |
|--------|------|--------|
| **Model A: SOMS 出資** | 既存ユーザー | SOMS で直接 shares 購入 → 即時報酬配分開始 |
| **Model B: 現金プール** | カジュアル支援者 | 現金出資 → 管理者がプール運用 → 目標達成でデバイス購入 → shares 自動割当 |

### 新規テーブル (wallet スキーマ)

| テーブル | 用途 |
|---------|------|
| `device_stakes` | デバイス持分 (user_id × device_id, shares, unique constraint) |
| `funding_pools` | プール出資 (title, goal_jpy, raised_jpy, status lifecycle) |
| `pool_contributions` | プール出資記録 (user_id, amount_jpy, shares_allocated) |

### Device テーブル追加カラム

```
total_shares, available_shares, share_price, funding_open   — 出資モデル
power_mode, hops_to_mqtt, battery_pct                        — デバイスメトリクス
utility_score                                                — XP 重み付け (0.5~2.0)
```

### 新規 API エンドポイント (Wallet サービス)

**Model A: SOMS 出資 (6本)**

| Method | Path | 機能 |
|--------|------|------|
| POST | `/devices/{id}/funding/open` | 出資募集開始 |
| POST | `/devices/{id}/funding/close` | 出資募集停止 |
| POST | `/devices/{id}/stakes/buy` | shares 購入 |
| POST | `/devices/{id}/stakes/return` | shares 返却 (システム買戻し) |
| GET | `/devices/{id}/stakes` | 全 stakeholder 一覧 |
| GET | `/users/{id}/portfolio` | ユーザーの出資ポートフォリオ |

**Model B: プール出資 (6本)**

| Method | Path | 機能 |
|--------|------|------|
| POST | `/admin/pools` | プール作成 |
| GET | `/admin/pools` | プール一覧 (admin) |
| GET | `/admin/pools/{id}` | プール詳細 |
| POST | `/admin/pools/{id}/contribute` | 出資記録 |
| POST | `/admin/pools/{id}/activate` | デバイスリンク + shares 割当 |
| GET | `/pools` | 公開プール一覧 |

**追加エンドポイント**

| Method | Path | 機能 |
|--------|------|------|
| POST | `/devices/{id}/utility-score` | utility_score 更新 (clamp 0.5~2.0) |

### XP 貢献度重み付け (2層)

```
total_weight = hardware_weight × utility_score

hardware_weight (静的, 1.0~2.0):
  Base 1.0 + バッテリー駆動 +0.5 + hops×0.2 (max +0.6)

utility_score (動的, 0.5~2.0):
  Base 1.0 + decision使用 +0.3 + task作成 +0.5
  7日間未使用 → 減衰開始, 30日で 0.5 到達
```

### テスト結果

| テストスイート | 結果 | スクリプト |
|--------------|------|-----------|
| Wallet E2E (52テスト) | ALL PASSED | `infra/scripts/test_phase1_5.py` |
| Brain 統合 (9テスト) | ALL PASSED | 手動実行 (docker exec) |

テスト詳細: `docs/phase1.5-session-notes.md`

---

## 3. Event Store (Brain サービス)

### 概要

Brain の MQTT イベントを PostgreSQL に永続化。非同期バッファ書込み + 時間単位集計。

### ファイル構成 (`services/brain/src/event_store/`)

| ファイル | 役割 |
|---------|------|
| `models.py` | SQLAlchemy テーブル定義 (raw_events, hourly_aggregates) |
| `database.py` | async engine + session factory |
| `writer.py` | `EventWriter` — 非同期バッファ (10秒 or 100件でフラッシュ) |
| `aggregator.py` | `HourlyAggregator` — 毎時集計 (count, avg, min, max) |

### Brain main.py への統合

- `_process_mqtt_message()`: sensor データを `EventWriter.add()` でバッファ
- `cognitive_cycle()`: decision を記録
- `run()`: event_store 初期化 + HourlyAggregator タスク起動

---

## 4. WalletBridge (Brain → Wallet)

### 概要

MQTT heartbeat を Wallet REST API に中継。メッシュ葉デバイス (REST 不可) の報酬確保。

| 項目 | 値 |
|------|-----|
| ファイル | `services/brain/src/wallet_bridge.py` |
| 転送間隔 | 300秒 / デバイス (スロットル) |
| ペイロード | power_mode, battery_pct, hops_to_mqtt, utility_score |
| 子デバイス | `forward_children()` で再帰的に転送 |

### Brain main.py 統合ポイント

- `__init__`: `self.wallet_bridge = None`
- `run()`: `WalletBridge(session, device_registry)` 初期化 + `_utility_decay_loop()` タスク起動
- `_process_mqtt_message()`: heartbeat 検出時に `forward_heartbeat()` + `forward_children()` 呼出
- `cognitive_cycle()` 末尾: アクション結果から zone 抽出 → `record_zone_action()`

---

## 5. ファイル変更マップ (Session L)

### Wallet サービス (`services/wallet/src/`) — 2,476行

| ファイル | 行数 | 変更内容 |
|---------|------|---------|
| `models.py` | ~300 | Device 11カラム追加 + DeviceStake + FundingPool + PoolContribution |
| `schemas.py` | ~250 | 15+ 新 Pydantic スキーマ + DeviceResponse 拡張 |
| `services/stake_service.py` | ~180 | **NEW** — open/close/buy/return/distribute_reward |
| `services/pool_service.py` | ~130 | **NEW** — create/contribute/activate (shares 一括割当) |
| `services/xp_scorer.py` | ~100 | compute_contribution_weight + grant_xp_to_zone_weighted |
| `routers/stakes.py` | ~130 | **NEW** — Model A 6EP + portfolio |
| `routers/pools.py` | ~130 | **NEW** — Model B admin 5EP + public 1EP |
| `routers/devices.py` | ~150 | heartbeat 比例配分 + metrics 更新 + utility-score EP |
| `main.py` | ~100 | relay_node/remote_node seed + 4 router 追加 |

### Brain サービス (`services/brain/src/`) — 3,717行

| ファイル | 変更内容 |
|---------|---------|
| `device_registry.py` | utility_score + _last_used + record_zone_action + decay_utility_scores |
| `wallet_bridge.py` | **NEW** — MQTT→Wallet heartbeat 中継 (300s スロットル) |
| `main.py` | WalletBridge 統合 + Event Store 統合 + utility 記録 + decay loop |
| `event_store/` | **NEW** — 4ファイル (models, database, writer, aggregator) |

### インフラ

| ファイル | 変更内容 |
|---------|---------|
| `infra/docker-compose.yml` | brain に WALLET_SERVICE_URL + DATABASE_URL 追加 |
| `infra/scripts/test_phase1_5.py` | **NEW** — E2E テストスイート (52テスト) |

---

## 6. アーキテクチャ上の重要な変更点

### Brain の統合パターン (Session L 後)

```
Brain.run()
 └─ async with aiohttp.ClientSession() as session:
      ├─ LLMClient(session)
      ├─ DashboardClient(session)
      ├─ TaskReminder(session)
      ├─ ToolExecutor(session)
      ├─ WalletBridge(session, device_registry)  ← NEW
      ├─ EventWriter(engine)                     ← NEW
      ├─ HourlyAggregator(engine)                ← NEW
      └─ _utility_decay_loop()                   ← NEW (3600s interval)
```

### Wallet 報酬配分の変更

```
Before: heartbeat → 100% to owner
After:  heartbeat → distribute_reward()
         ├─ stakes なし → 100% to owner (後方互換)
         └─ stakes あり → 各 stakeholder へ比例配分 (端数はオーナーへ)
```

### トランザクション種別 (追加)

| Type | 用途 | reference_id パターン |
|------|------|----------------------|
| `STAKE_PURCHASE` | shares 購入代金 (投資家→オーナー) | `stake:buy:{device}:{user}:{epoch}` |
| `STAKE_REFUND` | shares 返却払戻 (システム→投資家) | `stake:return:{device}:{user}:{epoch}` |
| `INFRA_REWARD` | インフラ報酬 (比例配分) | `infra:{device}:{epoch}:{user}` |

---

## 7. Docker サービス状態

### ポートマップ (最新)

| ポート | サービス | コンテナ名 | 備考 |
|--------|---------|-----------|------|
| 80 | frontend (nginx) | soms-frontend | SPA + API リバースプロキシ |
| 1883/9001 | MQTT | soms-mqtt | Edge デバイス接続用 |
| 127.0.0.1:5432 | PostgreSQL | soms-postgres | localhost のみ |
| 8000 | backend | soms-backend | Dashboard REST API |
| 8001 | mock-llm | soms-mock-llm | 開発用 LLM |
| 8002 | voice-service | soms-voice | TTS |
| 8004 | wallet-app | soms-wallet-app | PWA (Mobile) |
| 11434 | ollama | soms-ollama | GPU LLM |
| 50021 | voicevox | soms-voicevox | VOICEVOX エンジン |
| — | wallet | soms-wallet | ポート非公開 (nginx 経由のみ) |
| — | brain | soms-brain | ポート非公開 (MQTT + REST 内部) |

### サービス間依存

```
mosquitto ← brain (MQTT + WalletBridge)
         ← wallet (MQTT subscribe)
         ← perception (MQTT publish)

postgres  ← brain (Event Store)
         ← backend (Dashboard DB)
         ← wallet (Ledger DB)

wallet    ← brain (WalletBridge REST)
         ← wallet-app (PWA frontend)
         ← frontend/nginx (reverse proxy)
```

---

## 8. 並行作業に関する注意点

### 変更が競合しやすい領域

| ファイル | 理由 |
|---------|------|
| `services/brain/src/main.py` | 最多改変集中 (Event Store + WalletBridge + cognitive_cycle + decay loop) |
| `infra/docker-compose.yml` | サービス追加・環境変数変更が頻繁 |
| `services/wallet/src/models.py` | テーブル・カラム追加が集中 |

### 並行開発で安全な領域

| 領域 | 理由 |
|------|------|
| `edge/` | ファームウェアは他サービスと独立 |
| `services/perception/` | Brain とは MQTT のみで接続 |
| `services/voice/` | REST API のみ、独立性高い |
| `docs/` | ドキュメントは並行編集可能 |
| `services/wallet-app/` | PWA フロントエンド、Wallet REST のみ依存 |

---

## 9. 全体サマリー (コードベース規模)

| カテゴリ | ファイル数 | 行数 | 状態 |
|----------|-----------|------|------|
| Brain (LLM決定エンジン) | ~22 .py | 3,717 | 完成 (Event Store + WalletBridge 統合済み) |
| Voice (音声合成) | 5 .py | ~864 | 完成 |
| Perception (画像認識) | ~20 .py | ~1,687 | 完成 |
| Dashboard Backend | 9 .py | ~605 | 95% (users.py スタブ) |
| Dashboard Frontend | ~11 .tsx/.ts | ~823 | 完成 |
| Wallet (クレジット経済) | ~15 .py | 2,476 | 完成 (Phase 1.5 追加) |
| Wallet App (PWA) | ~15 .tsx/.ts | ~1,100 | 完成 (Session N: 出資UI追加) |
| Edge Firmware (Python) | 33 .py | ~2,562 | 完成 |
| Edge Firmware (C++) | 4 .cpp/.h | ~817 | 完成 |
| Infra/テスト | ~18 .py | ~3,500 | 完成 |
| **合計** | **~150+** | **~17,500+** | |

---

## 10. 環境情報

セッション開始時に以下を確認すること:

```bash
# OS / カーネル
uname -r

# CPU / GPU
lscpu | head -15
lspci | grep -i vga

# Docker アクセス
docker info --format '{{.ServerVersion}}' 2>/dev/null || echo "Docker not accessible (check group membership)"

# 稼働中コンテナ
docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null

# .env 設定 (LLM_API_URL, LLM_MODEL 等)
cat infra/.env 2>/dev/null || echo ".env not found"
```

---

## 11. 残作業 / 次セッションの候補

ISSUES.md の 32件は全件解決済み。以下は新規タスク候補:

| タスク | 優先度 | 備考 |
|--------|--------|------|
| C.2: バッテリー監視ダッシュボード | 中 | SwarmHub 状態の可視化 |
| C.3: フロントエンドエラーバウンダリ | 低 | 依存なし |
| C.4: 認証レイヤー (nginx / API 基本認証) | 中 | C.1 完了済み |
| C.5: Event Store ダッシュボード表示 | 中 | B.2 完了済み、hourly_aggregates をグラフ表示 |
| E.1: 受諾音声ストック化 | 低 | 1-2秒レイテンシ解消 |
| Model B 外部決済連携 (Stripe 等) | 中 | Phase 1.5 スキーマ対応済み、API 実装のみ |
| Eda/Ha メッシュネットワーク実装 | 中 | 設計ドキュメント完了 (`docs/08_edge_mesh_network`) |
| `hems/` ディレクトリ (untracked) | 低 | 要確認: 新プロジェクトか一時ファイルか |
