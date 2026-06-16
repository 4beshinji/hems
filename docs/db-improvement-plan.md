# DB構成 改善計画

調査日: 2026-04-03
更新日: 2026-06-16
ステータス:
  - W4.5' により PostgreSQL を既定 DB に昇格済。
  - W4.6 により `make quickstart` / `python infra/scripts/init_env.py` で
    PostgreSQL/MQTT/dashboard 用の安全な乱数値を自動生成。
  - SQLite は `make quickstart-sqlite` または
    `docker-compose.sqlite-lite.yml` オーバーライドで継続利用可能。

---

## 現状サマリー

### DBを使用するサービス

| サービス | DB | 用途 |
|---------|-----|------|
| backend | SQLite/PostgreSQL (SQLAlchemy async) | タスク、ユーザー、音声イベント、時系列、買い物リスト等 |
| brain | SQLite/PostgreSQL (event_store) | センサイベント、LLM意思決定ログ、時間別集計 |
| biometric-bridge | SQLite (aiosqlite) | MQTT再接続時のoutboxキュー |
| その他ブリッジ/frontend | なし | ステートレス・MQTT中継のみ |

### DB接続

- Backend と Brain は同一 `DATABASE_URL` 環境変数。Docker Compose では PostgreSQL がコアサービスとして起動。
- PostgreSQL 時は同一DB（Brain は `events` スキーマで分離）。
- SQLite 時は別ファイル（`/app/data/hems.db` 等）。`make quickstart-sqlite` または
  `infra/docker-compose.sqlite-lite.yml` オーバーライドで起動する。

---

## 課題一覧

| # | 課題 | 重要度 | 影響 | 状態 |
|---|------|--------|------|------|
| 1 | SQLite WAL モード未設定 | 高 | 並行書き込みで SQLITE_BUSY | SQLite 運用時に該当。PG 既定化で緩和 |
| 2 | timeseries テーブルのリテンション欠如 | 高 | 無制限テーブル肥大 | 未対応（PG 既定化で優先度維持） |
| 3 | Backend の pool 設定なし | 中 | PostgreSQL 時の安定性 | **W4.5' で対応済** |
| 4 | Biometric リテンションの設計問題 | 中 | クリーンアップの信頼性 | 未対応 |
| 5 | インデックス不足 | 中 | クエリ性能 | 未対応 |
| 6 | マイグレーション管理の脆弱性 | 低 | 保守性 | 未対応 |
| 7 | event_store DDL 分割の脆弱性 | 低 | 将来の堅牢性 | 未対応 |

---

## 1. SQLite WAL モード未設定

### 問題

Brain は EventWriter (5s flush) と HourlyAggregator (10min) が同一 SQLite に並行書き込み。Backend は複数 FastAPI ワーカーが同一 SQLite に R/W。デフォルトの DELETE ジャーナルモードでは `SQLITE_BUSY` が発生しうる。

### 対象ファイル

- `services/backend/database.py`
- `services/brain/src/event_store/database.py`

### 案A: SQLAlchemy event listener で PRAGMA 設定 (推奨)

```python
from sqlalchemy import event

engine = create_async_engine(DATABASE_URL, echo=False)

if "sqlite" in DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
```

- 変更量: 各 database.py に5行追加
- 利点: 全コネクションに確実に適用。SQLAlchemy 公式パターン。busy_timeout もカバー
- 欠点: なし
- PostgreSQL影響: if 分岐で SQLite のみ適用、影響なし

### 案B: init_db() 内で初回接続時に1回だけ PRAGMA 実行

```python
async with engine.begin() as conn:
    await conn.execute(text("PRAGMA journal_mode=WAL"))
    await conn.execute(text("PRAGMA busy_timeout=5000"))
```

- 変更量: 各 init 関数に2行追加
- 利点: 最もシンプル。WAL はファイルレベル設定なので1回で永続化
- 欠点: busy_timeout はコネクション単位なので新規コネクションに効かない。pool 再接続時に未設定

### 案C: SQLite URI パラメータで指定

- **動かない**: aiosqlite は URI パラメータで PRAGMA を渡せない。却下

### 結論: 案A

---

## 2. timeseries テーブルのリテンション欠如

### 問題

`TimeSeriesPoint` は Brain が毎サイクル (30s) に ingest するが削除処理が一切ない。他のテーブルも同様。

| テーブル | 現状のリテンション | 推奨 |
|---------|------------------|------|
| `raw_events` | 730日 (aggregator) | 維持 |
| `llm_decisions` | 730日 (aggregator) | 維持 |
| `biometric_readings` | 90日 (リクエスト駆動) | 90日 (bg task化) |
| **`timeseries`** | **なし** | **30日** |
| **`voice_events`** | **なし** | **90日** |
| **`tasks` (completed)** | **なし** | **365日** |
| **`purchase_history`** | **なし** | **365日** |

データ量見積もり (timeseries): HA power sensor 5台 → 約14,400行/日 → 年間500万行

### 対象ファイル

- `services/backend/main.py`
- `services/backend/routers/biometric.py` (既存 cleanup 削除)

### 案A: Backend lifespan にバックグラウンド cleanup タスク追加 (推奨)

```python
async def _retention_cleanup_loop():
    while True:
        await asyncio.sleep(3600)  # 1時間ごと
        async with AsyncSessionLocal() as db:
            for model, col_name, days in RETENTION_POLICIES:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                col = getattr(model, col_name)
                await db.execute(delete(model).where(col < cutoff))
            await db.commit()

RETENTION_POLICIES = [
    (TimeSeriesPoint, "recorded_at", 30),
    (VoiceEvent, "created_at", 90),
    (BiometricReading, "recorded_at", 90),
    (PurchaseHistory, "purchased_at", 365),
]
```

- 変更量: main.py に20行追加 + biometric.py から cleanup 削除
- 利点: 全テーブルを一元管理。リクエスト非依存。biometric の既存問題も同時解決
- 欠点: 大量 DELETE で SQLite lock 時間が長くなりうる（頻度 1h なら実運用では問題なし）

### 案B: ingest エンドポイントでインライン削除 (biometric と同パターン)

- 変更量: timeseries.py に10行追加
- 利点: 最小変更
- 欠点: biometric と同じ問題を再生産 (リクエスト駆動、カウンタリセット)。テーブルごとにバラバラ

### 案C: RetentionManager クラス新設で一元管理

- 変更量: 新規 `retention.py` 50行 + main.py + biometric.py 修正
- 利点: バッチ削除。全テーブル一元管理。拡張容易
- 欠点: SQLAlchemy の `delete().limit()` は SQLite 非対応 (サブクエリで回避要)。やや過剰

### 案D: SQLite トリガーで行数制限

- 却下: COUNT(*) 毎INSERT、時間ベースでない、PostgreSQL 非互換

### 結論: 案A (Phase 0相当。将来的に案Cへ発展可)

---

## 3. Backend の pool 設定なし

### 問題

`services/backend/database.py` で `create_async_engine(DATABASE_URL, echo=False)` のみ。PostgreSQL 時に pool_size/max_overflow/pool_pre_ping が未設定。

### 対象ファイル

- `services/backend/database.py`

### 案A: DB種別で分岐して pool パラメータ追加 (推奨)

```python
if "postgresql" in DATABASE_URL:
    engine = create_async_engine(
        DATABASE_URL, echo=False,
        pool_size=5, max_overflow=5, pool_pre_ping=True,
    )
else:
    engine = create_async_engine(DATABASE_URL, echo=False)
```

- 変更量: database.py 5行変更
- 利点: Brain の event_store/database.py と統一

### 案B: 環境変数で pool パラメータを設定可能にする

- 変更量: database.py 10行 + env.example
- 欠点: 個人用システムに不要な設定項目の増加。YAGNI

### 案C: pool_pre_ping のみ追加

- 変更量: 1行
- 欠点: pool_size/max_overflow がデフォルト (5/10) のまま

### 結論: 案A

---

## 4. Biometric リテンションの設計問題

### 問題

`services/backend/routers/biometric.py` L16-81:
- `_write_count` グローバル変数は再起動でリセット
- リクエストが来なければ cleanup が走らない
- ルーター層に DB 管理ロジックが混在

### 対象ファイル

- `services/backend/routers/biometric.py`
- `services/backend/main.py`

### 案A: 課題2の cleanup loop に統合 (推奨)

biometric router の `_write_count` / cleanup ブロック (L16-19, L73-81) を削除し、課題2の `RETENTION_POLICIES` に `BiometricReading` を追加。

- 変更量: biometric.py から15行削除
- 利点: ルーターが本来の責務に専念。一元管理

### 案B: lifespan 内の独立バックグラウンドタスクに移動

- 変更量: main.py に15行追加 + biometric.py から削除
- 欠点: テーブルごとにバラバラの cleanup ループが増える

### 案C: 現行方式を改善 (カウンタ → 時刻ベース)

```python
_last_cleanup: datetime | None = None
# ... in snapshot handler:
if _last_cleanup is None or (now - _last_cleanup).total_seconds() > 3600 * 6:
    ...
```

- 変更量: biometric.py 5行変更
- 欠点: 依然リクエスト駆動。ルーター層にロジック残存

### 結論: 案A (課題2と同時対応)

---

## 5. インデックス不足

### 問題

| テーブル | 不足カラム | 利用パターン |
|---------|-----------|------------|
| `voice_events` | `created_at` | `WHERE created_at >= max_age` |
| `tasks` | `is_completed`, `zone` | 重複チェック、一覧フィルタ |

### 対象ファイル

- `services/backend/models.py`
- `services/backend/main.py`

### 案A: モデル定義に index=True 追加のみ

```python
class VoiceEvent(Base):
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class Task(Base):
    is_completed = Column(Boolean, default=False, index=True)
    zone = Column(String, nullable=True, index=True)
```

- 変更量: models.py 3行変更
- 欠点: 既存 DB には反映されない (`create_all` は既存テーブルの ALTER を行わない)

### 案B: 案A + lifespan で CREATE INDEX IF NOT EXISTS (推奨)

```python
async with engine.begin() as conn:
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_voice_events_created_at ON voice_events(created_at)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_is_completed ON tasks(is_completed)"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_tasks_zone ON tasks(zone)"
    ))
```

- 変更量: models.py 3行 + main.py 3行
- 利点: 新規・既存 DB 両方カバー。冪等

### 案C: 複合インデックスで最適化

- 欠点: 現状のデータ量 (個人用) では過剰最適化

### 結論: 案B

---

## 6. マイグレーション管理の脆弱性

### 問題

- Backend: `try/except pass` で ALTER TABLE (`main.py` L28-35)
- Brain: `PRAGMA table_info` で列存在チェック → ALTER (`event_store/database.py` L146-157)
- バージョン管理なし。毎起動で例外が飛ぶ

### 対象ファイル

- `services/backend/main.py`
- (将来的に `services/backend/migrations.py` 新設)

### 案A: 自前マイグレーションテーブル (推奨)

```python
MIGRATIONS = [
    ("001_voice_events_motion_id",
     "ALTER TABLE voice_events ADD COLUMN motion_id VARCHAR"),
    ("002_idx_voice_events_created_at",
     "CREATE INDEX IF NOT EXISTS idx_voice_events_created_at ON voice_events(created_at)"),
    ("003_idx_tasks_is_completed",
     "CREATE INDEX IF NOT EXISTS idx_tasks_is_completed ON tasks(is_completed)"),
    ("004_idx_tasks_zone",
     "CREATE INDEX IF NOT EXISTS idx_tasks_zone ON tasks(zone)"),
]

async def run_migrations(conn):
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    for mid, sql in MIGRATIONS:
        row = await conn.execute(
            text("SELECT 1 FROM _migrations WHERE id = :id"), {"id": mid}
        )
        if not row.scalar():
            await conn.execute(text(sql))
            await conn.execute(
                text("INSERT INTO _migrations (id) VALUES (:id)"), {"id": mid}
            )
```

- 変更量: 新規30行 + main.py の既存 migration 置き換え
- 利点: 適用済み判定が確実。冪等。課題5のインデックス追加もここに統合可能

### 案B: Alembic 導入

- 変更量: Alembic 設定 + 既存DDLをrevision化
- 欠点: async 対応に工夫要。Phase 0 の zero-config 思想と相反。依存追加

### 案C: Brain パターンに統一 (PRAGMA table_info チェック)

- 変更量: main.py 5行書き換え
- 欠点: SQLite 限定。マイグレーション増加に弱い

### 結論: 案A (課題5のインデックス追加と自然に統合できる)

---

## 7. event_store DDL 分割の脆弱性

### 問題

`services/brain/src/event_store/database.py` L140:
```python
for statement in ddl.strip().split(";"):
```
ナイーブな `;` 分割。文字列リテラル内の `;` で壊れる。

### 対象ファイル

- `services/brain/src/event_store/database.py`

### 案A: DDL をリスト管理に変更 (推奨)

```python
DDL_SQLITE = [
    """CREATE TABLE IF NOT EXISTS raw_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        zone TEXT,
        event_type TEXT NOT NULL,
        source_device TEXT,
        data TEXT DEFAULT '{}'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events(timestamp)",
    # ...
]

# 実行
for stmt in DDL_SQLITE:
    await conn.execute(text(stmt))
```

- 変更量: レイアウト変更のみ (文字列 → リスト)
- 利点: 分割ロジック不要。各ステートメントが明確。`;` 問題が根本解消

### 案B: sqlparse で正確に分割

- 変更量: 2行変更 + `sqlparse` 依存追加
- 欠点: 新規依存。現状のDDLには過剰

### 案C: 放置

- リスク: 将来 DEFAULT 値に `;` を含む場合に壊れる（現実的にはほぼない）

### 結論: 案A

---

## 実装順序 (推奨)

Phase 0 の設計思想 (zero-config, 最小依存) を維持しつつ、影響度順に対応。

| 順序 | 課題 | 採用案 | 変更規模 | 備考 |
|------|------|--------|---------|------|
| 1 | #1 SQLite WAL | A: event listener | 各 database.py +5行 | 最優先。並行書き込み安定化 |
| 2 | #2 timeseries リテンション | A: bg cleanup | main.py +20行 | #4 と同時対応 |
| 3 | #4 Biometric リテンション | A: #2に統合 | biometric.py -15行 | #2 の一部 |
| 4 | #3 Backend pool | A: DB種別分岐 | database.py 5行 | 単独で完結 |
| 5 | #6 マイグレーション | A: migration table | 新規30行 | #5 のインデックスを含む |
| 6 | #5 インデックス | B: model + DDL | #6 に統合 | #6 の MIGRATIONS に追加 |
| 7 | #7 DDL分割 | A: リスト化 | レイアウト変更 | 最後。低リスク |
