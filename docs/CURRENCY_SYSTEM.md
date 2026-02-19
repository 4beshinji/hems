# SOMS 通貨システム — 全貌ドキュメント

**作成日**: 2026-02-13
**参照**: `IMPLEMENTATION_STATUS.md`, wallet サービス全ソース, dashboard backend/frontend

---

## 1. 概要

SOMS の通貨システムは **複式簿記 (double-entry ledger)** ベースのクレジット経済。LLM Brain がタスクを作成し、人間がそれを完了すると報酬 (bounty) がシステムウォレットからユーザーウォレットへ移転される。デバイスにもタスク貢献に応じた XP が蓄積され、動的な報酬乗数を形成する。

### 経済循環図

```
┌─────────────────────────────────────────────────────────────────┐
│                        SOMS 経済循環                             │
│                                                                 │
│  Brain (LLM)                                                    │
│    │ create_task(bounty=500-5000)                               │
│    ▼                                                            │
│  Dashboard Backend ───── POST /tasks/ ────► Task (bounty_gold)  │
│                                                │                │
│  User (Frontend)                               │                │
│    │ PUT /tasks/{id}/accept                    │                │
│    │ PUT /tasks/{id}/complete ─────────────────┘                │
│    │                                                            │
│    ▼                                                            │
│  Dashboard Backend ─── POST /transactions/task-reward ──►       │
│                                                                 │
│  ┌──────────────┐    transfer()    ┌──────────────┐            │
│  │ System Wallet │ ──────────────► │ User Wallet  │            │
│  │ (user_id=0)  │   -bounty_gold  │ +bounty_gold │            │
│  │ 負残高可能    │                  │ 残高 ≥ 0     │            │
│  └──────────────┘                  └──────────────┘            │
│         │                                                       │
│         ▼                                                       │
│  SupplyStats.total_issued += bounty_gold                       │
│                                                                 │
│  Zone Devices ─── grant_xp_to_zone() ──► Device.xp += 10-20   │
│                                          reward_multiplier()    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. サービス構成

| コンポーネント | 場所 | ポート | DB |
|---------------|------|--------|-----|
| Wallet Service | `services/wallet/` | 8003 (内部 8000) | PostgreSQL `wallet` スキーマ |
| Dashboard Backend | `services/dashboard/backend/` | 8000 | SQLite (`soms.db`) |
| Dashboard Frontend | `services/dashboard/frontend/` | 80 (nginx) | — |
| Brain Service | `services/brain/` | — | — |

**nginx プロキシルーティング**:
```
/api/wallet/*  →  http://wallet:8000/*     (Wallet Service)
/api/voice/*   →  http://voice-service:8000/api/voice/*
/api/*         →  http://backend:8000/*    (Dashboard Backend)
```

---

## 3. データモデル

### 3.1 Wallet Service (PostgreSQL `wallet` スキーマ)

#### `wallets` テーブル

| カラム | 型 | 制約 | 説明 |
|--------|-----|------|------|
| `id` | Integer | PK, auto | 内部ID |
| `user_id` | Integer | UNIQUE, NOT NULL | Dashboard User.id との 1:1 対応 |
| `balance` | BigInteger | DEFAULT 0 | 残高 (ミリ単位) |
| `created_at` | DateTime(tz) | server_default=now() | 作成日時 |
| `updated_at` | DateTime(tz) | onupdate=now() | 更新日時 |

**制約**: `CHECK(balance >= 0 OR user_id = 0)` — システムウォレット (user_id=0) のみ負残高を許可。

#### `ledger_entries` テーブル (複式仕訳帳)

| カラム | 型 | 制約 | 説明 |
|--------|-----|------|------|
| `id` | BigInteger | PK, auto | エントリID |
| `transaction_id` | UUID | NOT NULL, INDEX | 1取引で2行 (DEBIT+CREDIT) が同一UUIDを共有 |
| `wallet_id` | Integer | FK→wallets.id | 対象ウォレット |
| `amount` | BigInteger | NOT NULL | 正=入金 (CREDIT), 負=出金 (DEBIT) |
| `balance_after` | BigInteger | NOT NULL | この仕訳後のウォレット残高 |
| `entry_type` | String(50) | NOT NULL | `"DEBIT"` / `"CREDIT"` |
| `transaction_type` | String(50) | NOT NULL | `"TASK_REWARD"` / `"INFRASTRUCTURE_REWARD"` / `"P2P_TRANSFER"` |
| `description` | Text | nullable | 人間可読な説明 (例: `"Task: コーヒー豆を補充"`) |
| `reference_id` | String(200) | nullable, INDEX | 冪等キー (例: `"task:42"`) |
| `counterparty_wallet_id` | Integer | FK→wallets.id | 取引相手ウォレット |
| `created_at` | DateTime(tz) | server_default=now() | 作成日時 |

**インデックス**: `ix_ledger_transaction_id`, `ix_ledger_wallet_created` (wallet_id, created_at), `ix_ledger_reference`

#### `devices` テーブル

| カラム | 型 | 制約 | 説明 |
|--------|-----|------|------|
| `id` | Integer | PK | 内部ID |
| `device_id` | String(200) | UNIQUE, NOT NULL | MQTT デバイス識別子 (例: `"swarm_hub_01.leaf_env_01"`) |
| `owner_id` | Integer | NOT NULL | デバイスオーナーの User.id |
| `device_type` | String(50) | NOT NULL | `"llm_node"` / `"sensor_node"` / `"hub"` |
| `display_name` | String(200) | nullable | 表示名 |
| `topic_prefix` | String(500) | nullable | MQTTトピックプレフィックス (XPゾーンマッチに使用) |
| `registered_at` | DateTime(tz) | server_default=now() | 登録日時 |
| `is_active` | Boolean | DEFAULT true | アクティブなデバイスのみXP獲得 |
| `last_heartbeat_at` | DateTime(tz) | nullable | 最終ハートビート |
| `xp` | BigInteger | DEFAULT 0 | 蓄積XP (報酬乗数の計算に使用) |

#### `reward_rates` テーブル

| カラム | 型 | 制約 | 説明 |
|--------|-----|------|------|
| `id` | Integer | PK | 内部ID |
| `device_type` | String(50) | UNIQUE, NOT NULL | デバイス種別 |
| `rate_per_hour` | BigInteger | NOT NULL | 時間あたり報酬 (ミリ単位) |
| `min_uptime_for_reward` | Integer | DEFAULT 300 | 報酬資格の最低稼働秒数 |

**初期シードデータ**:

| device_type | rate_per_hour | min_uptime_for_reward |
|-------------|---------------|----------------------|
| `llm_node` | 5000 | 300 |
| `sensor_node` | 500 | 300 |
| `hub` | 1000 | 300 |

#### `supply_stats` テーブル (シングルトン)

| カラム | 型 | 説明 |
|--------|-----|------|
| `id` | Integer | PK (常に id=1) |
| `total_issued` | BigInteger | システムウォレットから発行された累計 |
| `total_burned` | BigInteger | 焼却 (バーン) された累計 |
| `circulating` | BigInteger | 流通量 = total_issued - total_burned |

### 3.2 Dashboard Backend (SQLite)

#### `tasks` テーブル (通貨関連フィールド)

| カラム | 型 | デフォルト | 説明 |
|--------|-----|----------|------|
| `bounty_gold` | Integer | 10 | 報酬額 (ミリ単位、Brain は 500-5000 を設定) |
| `bounty_xp` | Integer | 50 | システムXP (デバイスXPとは別) |
| `assigned_to` | Integer | NULL | 受諾したユーザーのID |
| `accepted_at` | DateTime | NULL | 受諾日時 |

#### `users` テーブル

| カラム | 型 | 説明 |
|--------|-----|------|
| `id` | Integer | PK |
| `username` | String | UNIQUE |
| `credits` | Integer | **非推奨**: Wallet.balance が正の残高ソース |

---

## 4. 複式簿記エンジン (ledger.py)

### 4.1 `transfer()` 関数

```python
async def transfer(
    db: AsyncSession,
    from_user_id: int,      # 送金元 (0=システム)
    to_user_id: int,         # 送金先
    amount: int,             # 正のミリ単位
    transaction_type: str,   # "TASK_REWARD" | "INFRASTRUCTURE_REWARD" | "P2P_TRANSFER"
    description: str = None,
    reference_id: str = None # 冪等キー (例: "task:42")
) -> uuid.UUID
```

### 4.2 処理フロー

```
1. バリデーション
   ├── amount > 0
   ├── from_user_id ≠ to_user_id
   └── reference_id が既存 → ValueError("Duplicate reference_id")

2. デッドロック防止ロック
   └── user_ids = sorted([from, to]) → FOR UPDATE 順序ロック

3. 残高チェック
   ├── from_user_id = 0 (システム) → 無制限 (負残高OK)
   └── from_user_id ≠ 0 → balance < amount → ValueError("Insufficient funds")

4. 残高更新
   ├── from_wallet.balance -= amount
   └── to_wallet.balance   += amount

5. 仕訳作成 (同一 transaction_id)
   ├── DEBIT  エントリ: wallet=送金元, amount=-N, balance_after=新残高
   └── CREDIT エントリ: wallet=送金先, amount=+N, balance_after=新残高

6. 供給統計更新 (システム発行時のみ)
   ├── total_issued += amount
   └── circulating = total_issued - total_burned
```

### 4.3 安全性保証

| 性質 | 実現手段 |
|------|---------|
| **原子性** | SQLAlchemy セッション内の単一トランザクション |
| **冪等性** | `reference_id` 重複チェック (例: `"task:42"`) |
| **デッドロック防止** | ウォレットID昇順の `FOR UPDATE` ロック |
| **監査性** | 全取引が `ledger_entries` に永続記録 |
| **残高整合** | `balance_after` で各時点の残高を追跡可能 |
| **負残高防止** | CHECK制約 (システムウォレット以外) |

---

## 5. タスク報酬フロー (End-to-End)

### Phase 1: タスク作成

```
Brain (ReAct Loop)
  ↓ create_task(title, bounty=2000, urgency=3, zone="main")
  ↓
tool_executor.py → dashboard_client.py
  ↓ POST /tasks/
  ↓
Dashboard Backend
  ↓ Task レコード作成 (bounty_gold=2000, bounty_xp=50)
  ↓ announce_with_completion → Voice Service で音声事前生成
  ↓
  ※ この時点でウォレットへの操作なし
```

**Brain の bounty ガイドライン** (`tool_registry.py`):
| 難易度 | bounty 範囲 |
|--------|------------|
| 簡単 (コーヒー補充等) | 500 - 1,000 |
| 中程度 (プリンタ修理等) | 1,000 - 2,000 |
| 重労働 (大掃除等) | 2,000 - 5,000 |

### Phase 2: タスク受諾

```
Frontend: ユーザーが「受ける」ボタンをクリック
  ↓ PUT /tasks/{id}/accept { user_id: 5 }
  ↓
Dashboard Backend
  ↓ task.assigned_to = 5
  ↓ task.accepted_at = NOW()
  ↓
Frontend: 受諾音声再生 (/api/voice/synthesize)
  ↓
  ※ この時点でウォレットへの操作なし
```

### Phase 3: タスク完了 → 報酬支払い

```
Frontend: ユーザーが「完了」ボタンをクリック
  ↓ PUT /tasks/{id}/complete
  ↓
Dashboard Backend
  ├── task.is_completed = True
  ├── task.completed_at = NOW()
  ├── system_stats.total_xp += bounty_xp
  ├── system_stats.tasks_completed += 1
  │
  └── [非同期 fire-and-forget]
      POST http://wallet:8000/transactions/task-reward
      {
        "user_id": 5,
        "amount": 2000,
        "task_id": 42,
        "description": "Task: コーヒー豆を補充"
      }
      ↓
      Wallet Service: ledger.transfer()
        from: System Wallet (user_id=0, balance: -125000 → -127000)
        to:   User 5 Wallet (balance: 6750 → 8750)
        reference_id: "task:42" (二重支払い防止)
        ↓
        LedgerEntry (DEBIT):  txn=UUID-A, wallet=system, amount=-2000
        LedgerEntry (CREDIT): txn=UUID-A, wallet=user5,  amount=+2000
        ↓
        SupplyStats: total_issued += 2000, circulating += 2000

Frontend: 完了音声再生 (事前生成済み)
WalletBadge: 10秒ポーリングで新残高表示
```

### Phase 4: タスク無視

```
Frontend: ユーザーが「無視」ボタンをクリック
  ↓ リジェクション音声再生 (/api/voice/rejection/random)
  ↓
  ※ ウォレットへの操作なし
  ※ タスクは他ユーザーが受諾可能な状態のまま
```

---

## 6. デバイス XP システム

### 6.1 XP 付与ロジック (`xp_scorer.py`)

| イベント | XP/デバイス | トリガー |
|---------|------------|---------|
| タスク作成 | 10 | Brain が create_task 実行時 |
| タスク完了 | 20 | ユーザーがタスク完了時 |

**ゾーンマッチング**:
```python
# topic_prefix が "office/{zone}/%" に LIKE マッチするアクティブデバイスを検索
pattern = f"office/{zone}/%"
devices = SELECT * FROM devices WHERE is_active=true AND topic_prefix LIKE pattern
```

**例**: zone="main" のタスク完了時、`office/main/%` にマッチする全デバイスに XP 20 付与。

### 6.2 動的報酬乗数

```python
def compute_reward_multiplier(device_xp: int) -> float:
    multiplier = 1.0 + (device_xp / 1000.0) * 0.5
    return min(multiplier, 3.0)
```

| 蓄積XP | 乗数 |
|--------|------|
| 0 | 1.0x (基本) |
| 500 | 1.25x |
| 1,000 | 1.5x |
| 2,000 | 2.0x |
| 4,000+ | 3.0x (上限) |

**設計意図**: 高価値ゾーンにセンサーを設置する経済的インセンティブを創出。良いセンサー → 良いデータ → より多くのタスク → より多くのXP → より高い報酬という正のフィードバックループ。

### 6.3 時間ベース報酬レート

| デバイス種別 | 時間あたりレート | 最低稼働時間 |
|-------------|----------------|------------|
| `llm_node` | 5,000 ミリ単位 | 300秒 (5分) |
| `sensor_node` | 500 ミリ単位 | 300秒 |
| `hub` | 1,000 ミリ単位 | 300秒 |

※ 現時点では時間ベース報酬の自動付与ロジックは未実装 (レートテーブルのみ定義済み)。

---

## 7. API エンドポイント一覧

### 7.1 Wallet Service (ベース: `/api/wallet/`)

| メソッド | パス | 入力 | 出力 | 説明 |
|---------|------|------|------|------|
| POST | `/wallets/` | `{ user_id }` | WalletResponse | ウォレット取得/作成 |
| GET | `/wallets/{user_id}` | — | WalletResponse | 残高照会 |
| GET | `/wallets/{user_id}/history` | `?limit=50&offset=0` | List[LedgerEntry] | 取引履歴 |
| POST | `/transactions/task-reward` | TaskRewardRequest | TransactionResponse | タスク報酬支払い |
| POST | `/transactions/p2p-transfer` | P2PTransferRequest | TransactionResponse | ユーザー間送金 |
| GET | `/transactions/{txn_id}` | — | TransactionResponse | 取引詳細 |
| POST | `/devices/` | DeviceCreate | DeviceResponse | デバイス登録 |
| GET | `/devices/` | — | List[DeviceResponse] | デバイス一覧 |
| PUT | `/devices/{device_id}` | DeviceUpdate | DeviceResponse | デバイス更新 |
| GET | `/supply` | — | SupplyResponse | 供給統計 |
| GET | `/reward-rates` | — | List[RewardRateResponse] | 報酬レート一覧 |
| PUT | `/reward-rates/{device_type}` | RewardRateUpdate | RewardRateResponse | レート更新 |

### 7.2 Dashboard Backend (タスク報酬関連)

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/tasks/` | タスク作成 (bounty_gold 設定) |
| PUT | `/tasks/{id}/accept` | タスク受諾 (assigned_to 設定) |
| PUT | `/tasks/{id}/complete` | タスク完了 → wallet に fire-and-forget 報酬支払い |

### 7.3 スキーマ定義

**TaskRewardRequest**:
```json
{
  "user_id": 5,
  "amount": 2000,
  "task_id": 42,
  "description": "Task: コーヒー豆を補充"
}
```

**TransactionResponse**:
```json
{
  "transaction_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "entries": [
    {
      "id": 10001,
      "wallet_id": 1,
      "amount": -2000,
      "balance_after": -127000,
      "entry_type": "DEBIT",
      "transaction_type": "TASK_REWARD",
      "reference_id": "task:42",
      "counterparty_wallet_id": 2
    },
    {
      "id": 10002,
      "wallet_id": 2,
      "amount": 2000,
      "balance_after": 8750,
      "entry_type": "CREDIT",
      "transaction_type": "TASK_REWARD",
      "reference_id": "task:42",
      "counterparty_wallet_id": 1
    }
  ]
}
```

**WalletResponse**:
```json
{
  "id": 2,
  "user_id": 5,
  "balance": 8750,
  "created_at": "2026-02-13T09:00:00+09:00",
  "updated_at": "2026-02-13T10:30:45+09:00"
}
```

---

## 8. フロントエンド UI

### 8.1 コンポーネント構成

```
App.tsx
├── UserSelector         ユーザー選択ドロップダウン
├── WalletBadge          残高バッジ (10秒ポーリング)
├── TaskCard (×N)        タスクカード (bounty表示、受諾/完了ボタン)
└── WalletPanel          取引履歴サイドパネル (スライドイン)
```

### 8.2 WalletBadge

- `/api/wallet/wallets/{userId}` を 10秒間隔でポーリング
- 残高をゴールドコインアイコン付きで表示
- クリックで WalletPanel を開く

### 8.3 WalletPanel

- 右端スライドインパネル (z-50)
- `/api/wallet/wallets/{userId}/history?limit=20` から取引履歴取得
- 入金 (緑) / 出金 (赤) を色分け表示
- ラベル: 「ウォレット」「取引履歴はありません」

### 8.4 TaskCard (通貨関連部分)

- `bounty_gold` を「{N} SOMS」バッジで表示
- `bounty_xp` を「{N} システム活動値」で表示
- urgency による色分け (0-1: 緑, 2: 橙, 3-4: 赤)
- 受諾 → 対応中 → 完了 のステート遷移

### 8.5 UserSelector

- `/api/users/` からユーザー一覧取得
- ドロップダウンで現在のユーザーを選択
- 選択により WalletBadge のポーリング対象が切り替わる

---

## 9. Docker / インフラ構成

### 9.1 docker-compose.yml (wallet 関連)

```yaml
wallet:
  build: ../services/wallet
  container_name: soms-wallet
  restart: always
  ports:
    - "8003:8000"
  depends_on:
    - postgres
    - mosquitto
  environment:
    - DATABASE_URL=postgresql+asyncpg://soms:soms_dev_password@postgres:5432/soms
    - MQTT_BROKER=mosquitto
    - MQTT_PORT=1883
  volumes:
    - ../services/wallet/src:/app
  networks:
    - soms-net

postgres:
  image: postgres:16-alpine
  container_name: soms-postgres
  restart: always
  ports:
    - "5432:5432"
  environment:
    - POSTGRES_USER=soms
    - POSTGRES_PASSWORD=soms_dev_password
    - POSTGRES_DB=soms
  volumes:
    - postgres_data:/var/lib/postgresql/data
  networks:
    - soms-net
```

### 9.2 起動時初期化 (`wallet/src/main.py`)

1. `wallet` スキーマ自動作成 (`CREATE SCHEMA IF NOT EXISTS wallet`)
2. 全テーブル作成 (`metadata.create_all`)
3. システムウォレット自動作成 (user_id=0, balance=0)
4. 報酬レートシードデータ挿入 (3種)
5. SupplyStats シングルトン作成

---

## 10. 既知の問題と未完成部分

### 10.1 要修正 (高優先度)

| 問題 | 詳細 | 影響 |
|------|------|------|
| **App.tsx マージコンフリクト** | wallet stash pop 由来の `UU` 状態 | フロントエンドビルド不可 |
| **Task モデルのカラム欠損** | `assigned_to`, `accepted_at` が models.py に未定義 | タスク受諾データが永続化されず、再起動でassigned_toが消失 |

### 10.2 API 不整合 (中優先度)

| 問題 | 詳細 |
|------|------|
| **WalletPanel のエンドポイント不一致** | フロントが `/transactions/{userId}` を期待するが API は `/wallets/{userId}/history` |
| **WalletPanel のフィールド名不一致** | フロントが `transactions` キーを期待するが API は `entries` を返す |
| **User.credits の二重管理** | Dashboard の `User.credits` と Wallet の `Wallet.balance` が並存 |
| **users.py がスタブ** | ハードコードされた mock データを返す (DB 連携なし) |

### 10.3 未実装 (低優先度)

| 項目 | 詳細 |
|------|------|
| **時間ベース報酬自動付与** | `reward_rates` テーブルは定義済みだが、自動付与の cron/scheduler 未実装 |
| **デバイスXP → 報酬乗数の実適用** | `compute_reward_multiplier()` は定義済みだが、bounty 計算時に未使用 |
| **バーン (焼却) メカニズム** | `total_burned` フィールドは存在するが、焼却のトリガーや用途が未定義 |
| **P2P 送金の UI** | API は実装済みだが、フロントエンドの送金UIなし |
| **認証・認可** | 全API に認証レイヤーなし (PoC 段階) |

---

## 11. 通貨単位

| 表記 | 値 | 用途 |
|------|-----|------|
| 1 SOMS | 1 ミリ単位 (コード内の `amount`/`balance` の値) | 内部表現 |
| bounty 500-5000 | Brain が設定するタスク報酬 | タスク作成時 |
| XP | デバイス経験値 (通貨とは独立) | 報酬乗数の計算 |
| システム活動値 | `bounty_xp` (通貨とは独立) | Dashboard 表示用 |

※ 現時点では「1 SOMS = 1 ミリ単位」の変換レートだが、UI 表示での単位変換ロジックは未実装。`balance: 8750` が「8750 SOMS」として表示される。

---

## 12. セキュリティ考慮事項

| 項目 | 現状 | リスク |
|------|------|--------|
| 認証 | なし | 誰でも任意のユーザーとしてタスク受諾/完了可能 |
| レート制限 | Brain 側のみ (10件/時) | API 直接呼び出しは無制限 |
| 二重支払い防止 | `reference_id` で対応済み | 堅牢 |
| 残高チェック | CHECK制約 + アプリ層 | 堅牢 |
| SQL インジェクション | SQLAlchemy ORM 使用 | 低リスク |

---

## 13. ファイル一覧

```
services/wallet/
├── src/
│   ├── main.py              (64行)  FastAPIアプリ、起動時初期化
│   ├── database.py          (17行)  asyncpg エンジン
│   ├── models.py            (80行)  Wallet, LedgerEntry, Device, RewardRate, SupplyStats
│   ├── schemas.py          (139行)  Pydantic 2.x スキーマ
│   ├── services/
│   │   ├── ledger.py       (168行)  複式簿記 transfer()
│   │   └── xp_scorer.py     (96行)  ゾーンXP付与、報酬乗数計算
│   └── routers/
│       ├── wallets.py        (54行)  残高照会、ウォレット作成
│       ├── transactions.py   (80行)  取引履歴、タスク報酬API
│       ├── devices.py        (67行)  デバイス登録/一覧
│       └── admin.py          (47行)  供給統計、報酬レート管理

services/dashboard/backend/
├── models.py                         Task.bounty_gold, User.credits
├── schemas.py                        TaskCreate, TaskAccept
└── routers/tasks.py                  完了時の wallet 連携

services/dashboard/frontend/src/
├── components/
│   ├── TaskCard.tsx                   bounty 表示、受諾/完了ボタン
│   ├── WalletBadge.tsx               残高バッジ
│   ├── WalletPanel.tsx               取引履歴パネル
│   └── UserSelector.tsx              ユーザー選択
└── App.tsx                           ウォレット UI 統合 (マージコンフリクト)
```
