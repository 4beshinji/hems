# 機能不整合修正 — ダッシュボード・ウォレット連携

**作業者**: ワーカー A (Claude Code)
**日時**: 2026-02-13 19:05 JST
**ステータス**: 中断 — API検証完了、フロントエンドE2E検証未完了

---

## 1. 背景

Wallet サービス追加に伴う未コミット変更で以下の機能不整合が発生していた:

- Backend の accept/complete エンドポイントが AttributeError でクラッシュ
- nginx wallet proxy が 404 を返す
- ユーザー選択が動作しない (id フィールド欠落)
- App.tsx の git UU ステータス未解決

参照: `ISSUES.md` の C-1, C-2 および関連 HIGH 問題

---

## 2. 変更したファイル

| ファイル | 変更内容 |
|---------|---------|
| `services/dashboard/backend/models.py` | Task に `assigned_to` (Integer), `accepted_at` (DateTime) 追加。User に `display_name`, `is_active`, `created_at` 追加。`credits` は wallet 管理のため不要 |
| `services/dashboard/backend/main.py` | `def _migrate_add_columns()`: 既存テーブルへのカラム追加マイグレーション。デフォルトユーザー「ゲスト」の seed 処理 |
| `services/dashboard/backend/routers/users.py` | ハードコードから DB 連動に書き換え (`GET /users/`, `POST /users/`) |
| `services/dashboard/frontend/nginx.conf` | `/api/wallet/` に `rewrite ^/api/wallet/(.*) /$1 break;` 追加。変数 proxy_pass ではプレフィックス自動除去が効かないため |
| `services/dashboard/frontend/src/components/TaskCard.tsx` | Task interface に `assigned_to?: number` 追加 |
| `services/dashboard/frontend/src/App.tsx` | fetchTasks 内で `assigned_to != null` のタスクを `acceptedTaskIds` に復元。`git add` 済み (UU 解消) |

---

## 3. 作業中に発見・修正した追加バグ

### 3-1. `async def` → `def` (マイグレーション関数)

別ワーカーが `_migrate_add_columns` を `async def` で定義していたが、`conn.run_sync()` は同期関数を要求する。`async def` のままだとコルーチンオブジェクトが返されるだけで実行されず、`RuntimeWarning: coroutine was never awaited` が出る。`def` に修正。

### 3-2. PostgreSQL 既存テーブルへのカラム追加

`Base.metadata.create_all()` は既存テーブルにカラムを追加できない。`sqlalchemy.inspect()` でカラム存在チェックし、不足分を `ALTER TABLE ADD COLUMN` するマイグレーション機構を実装。対象:

```
tasks.assigned_to, tasks.accepted_at
users.display_name, users.is_active, users.created_at
```

### 3-3. credits カラムの経緯

`User.credits` は wallet サービス導入に伴い models.py から削除済み (残高は `wallet.wallets.balance` で管理)。ただし PostgreSQL の `users` テーブルには別途手動で `credits INTEGER DEFAULT 0` を追加済み (既存クエリとの互換性のため)。マイグレーションリストには含めていない。

---

## 4. API 検証結果

全て `curl` で直接確認済み。

| テスト | 結果 | 備考 |
|--------|------|------|
| `GET localhost:8000/users/` | OK | ゲスト (id:1) 返却 |
| `POST localhost:8000/tasks/` | OK | テストタスク作成 (id:5) |
| `PUT localhost:8000/tasks/5/accept` | OK | assigned_to=1, accepted_at セット |
| `PUT localhost:8000/tasks/5/complete` | OK | is_completed=true, wallet へ報酬送信 |
| `GET localhost/api/wallet/wallets/1` (nginx経由) | OK | wallet API に正常到達 |
| `GET localhost/api/wallet/supply` (nginx経由) | OK | total_issued=1500 |

---

## 5. 未完了タスク

### フロントエンド E2E ブラウザ検証

以下のフローをブラウザで確認する必要がある:

1. ユーザー選択ドロップダウンにユーザーが表示される
2. WalletBadge に残高が表示される
3. タスク受諾 → 「対応中」表示
4. タスク完了 → wallet 残高増加
5. ページリロード → 受諾中タスクが「対応中」のまま維持

### wallet stale connection

wallet サービスが長時間稼働後に PostgreSQL 接続が切断される。`docker restart soms-wallet` で一時解消。根本対策はコネクションプールの `pool_recycle` 設定。

---

## 6. 依存関係の整理

### DB スキーマ構成

```
PostgreSQL (soms DB)
├── public スキーマ — dashboard backend 管理
│   ├── tasks (assigned_to, accepted_at 追加済み)
│   ├── users (display_name, is_active, created_at 追加済み)
│   ├── voice_events
│   └── system_stats
└── wallet スキーマ — wallet サービス管理
    ├── wallets (user_id で users.id と論理紐づけ、FK なし)
    ├── ledger_entries
    ├── devices
    ├── reward_rates
    └── supply_stats
```

### nginx ルーティング順序 (順序依存あり)

```
1. /api/wallet/  → wallet:8000   (rewrite で /api/wallet/ 除去)
2. /api/voice/   → voice-service:8000/api/voice/
3. /api/         → backend:8000/ (catchall — wallet/voice より後)
4. /audio/       → voice-service:8000/audio/
```

### サービス間通信フロー (タスク完了時)

```
Frontend  PUT /api/tasks/{id}/complete
  → nginx → backend:8000/tasks/{id}/complete
    → backend: task.is_completed = True, sys_stats.total_xp += bounty_xp
    → backend: POST wallet:8000/transactions/task-reward (fire-and-forget)
      → wallet: system_wallet → user_wallet に bounty_gold 移転
```

---

## 7. 現在のサービス状態

| コンテナ | 状態 | 最終操作 |
|---------|------|---------|
| soms-backend | Running | restart (マイグレーション適用) |
| soms-frontend | Rebuilt | nginx.conf rewrite 修正 |
| soms-wallet | Running | restart (stale connection 解消) |
| soms-postgres | Running | users.credits カラム手動追加 |
| その他 | Running | 変更なし |
