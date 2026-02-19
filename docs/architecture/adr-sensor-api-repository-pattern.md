# ADR: Sensor Data API — Repository Pattern + PostgreSQL 維持

**Status**: Accepted
**Date**: 2026-02-17
**Context**: TASK_SCHEDULE C.2+ (Sensor Data API + SwarmHub Visualization)

---

## 1. Decision

Sensor Data API のデータアクセスに **Repository パターン** を採用し、現行の **PostgreSQL** (`events.*` スキーマ) をバックエンドとして維持する。

```
routers/sensors.py  (API エンドポイント)
       │
       ▼
SensorDataRepository  (ABC — バックエンド非依存インターフェース)
       │
       ├── PgSensorRepository   (現在: PostgreSQL events.* を直接クエリ)
       └── InfluxSensorRepository  (将来: Flux クエリに差し替え)
```

## 2. Rationale

### なぜ PostgreSQL 維持か

- **データ量**: Phase 0-1 で ~7,200 events/日 (~150 MB/月)。PostgreSQL で十分処理可能
- **運用コスト**: 2つの DB (PG + InfluxDB) を管理する複雑さを回避
- **既存インフラ**: Brain の event_store が PostgreSQL に書き込み中。新 DB 追加は不要
- **クエリ柔軟性**: JSONB + SQL でアドホッククエリが容易

### なぜ Repository パターンか

- Brain が所有する `events` スキーマへの読取アクセスを 1モジュールに隔離
- PostgreSQL → InfluxDB 切替時、`deps.py` の 1行変更 + 新 Repository 実装のみ
- Router 層はバックエンドを意識しない
- テストで Mock Repository を注入可能

## 3. InfluxDB 移行パス

### クエリパラメータ ↔ InfluxDB マッピング

| TimeSeriesQuery | PostgreSQL WHERE | InfluxDB Flux |
|-----------------|------------------|---------------|
| `zone` | `zone = :zone` | `filter(fn:(r) => r.zone == "...")` |
| `channel` | `data->>'channel' = :ch` | `filter(fn:(r) => r._field == "...")` |
| `start` / `end` | `timestamp BETWEEN` | `range(start:, stop:)` |
| `window` ("1h") | `hourly_aggregates` テーブル | `aggregateWindow(every: 1h)` |
| `limit` | `LIMIT :n` | `\|> limit(n:)` |

### 移行手順

1. `InfluxSensorRepository` を実装 (`repositories/influx_sensor_repository.py`)
2. `deps.py` の `get_sensor_repo` を差し替え
3. Router / Schema 変更なし

### 移行トリガー (いずれか 1 つ)

- 書込み頻度 > 10,000 events/sec
- ゾーン数 > 100
- ストレージ増加 > 10 GB/月

## 4. データ保持期間の再設計

### ストレージ概算

| Phase | センサー数 | raw_events/月 | 総使用量/月 (×2.5 idx+WAL) | 年間 |
|-------|-----------|-------------|--------------------------|------|
| 0 | ~10 | ~43 MB | **~150 MB** | ~1.8 GB |
| 1 | ~50-100 | ~216-432 MB | **~0.6-1.2 GB** | ~7-15 GB |

### 利用可能ストレージ

- Phase 0-1: **1TB SSD** (高速アクセス)
- Phase 1+: **+ 8TB HDD** (コールドストレージ追加可能)

### 保持期間

| データ | 変更前 | 変更後 | 理由 |
|--------|--------|--------|------|
| raw_events | 90日 | **2年 (730日)** | ML 季節パターン学習に 365+日必要。Phase 1 で 2年 = ~15-30 GB (SSD 1.5-3%) |
| llm_decisions | 90日 | **2年 (730日)** | LLM 判断品質の長期トレンド分析。~1-2 GB/年 |
| hourly_aggregates | 無期限 | **無期限 (変更なし)** | 圧倒的に小さい (~40 MB/年) |

**Phase 1 で 2年保持時の最大ディスク使用量**: ~30-60 GB (1TB SSD の 3-6%)

### 将来の HDD アーカイブ戦略 (Phase 2+)

都市スケール (1000+ センサー, ~12 GB/月) では:
- SSD: 直近 6ヶ月の hot データ
- HDD: 6ヶ月以上の cold データ (PostgreSQL tablespace or pg_dump アーカイブ)
- 8TB HDD で ~50年分保持可能

## 5. ML Pros/Cons 分析

### 適したタスク

| ML タスク | データソース | 実現性 |
|-----------|------------|--------|
| **異常検知** (教師なし) | raw_events (温度/CO2/湿度) | 高 — Isolation Forest, Autoencoder で 90日分で十分 |
| **在室予測** | hourly_aggregates (person_count + 時刻) | 高 — 特徴量が既に集約済み |
| **快適度最適化** | 環境データ → タスク作成頻度 (不快さの代理指標) | 中 — 多変量回帰 |
| **センサードリフト検出** | SensorFusion 前後の値比較 | 中 — 要: fusion 値の永続化 |
| **エネルギー消費予測** | llm_decisions.tool_calls (デバイス制御) + 環境データ | 中 |
| **LLM 判断品質評価** | llm_decisions + タスク完了率 | 低 — ラベル品質が課題 |

### Pros

1. **時系列データ**: センサーデータは ML の主要ユースケース (予測・異常検知) に直結
2. **集約済み特徴量**: `hourly_aggregates` の avg/max/min が前処理不要で特徴量として利用可能
3. **JSONB 柔軟性**: 新センサー追加時にスキーマ変更不要、特徴量抽出を SQL で完結可能
4. **マルチモーダル**: 環境 + 在室 + LLM 判断 + 経済 (Wallet) データの横断分析が同一 DB 内で可能
5. **因果推論の素材**: LLM 判断 → デバイス制御 → 環境変化の因果チェーンが記録されている

### Cons

1. **データ量不足** (Phase 0): ~7,200 events/日は深層学習には少ない。月単位の蓄積が必要
2. **JSONB パース負荷**: ML パイプラインで大量の `data->>'value'` 抽出はネイティブ float より 2-5x 遅い
3. **90日→730日保持**: 季節パターン学習には 365+日が必要 (保持期間延長で対応済み)。hourly_aggregates は無期限だが分布情報 (stddev, percentile) が欠落
4. **ラベル不在**: 教師あり学習のラベルがない。LLM 判断を擬似ラベルとすると精度 ~80% でノイジー
5. **Fusion 値未永続化**: SensorFusion の重み付け結果が DB に保存されない (メモリ内のみ)
6. **特徴量ストア未整備**: Feature Store / Experiment Tracking (MLflow 等) なし
7. **データバージョニング未整備**: DVC 等なし。クリーンアップで過去データが消滅
8. **時間軸不整合**: センサー種別ごとにサンプリングレートが異なる (BME680: 30s, CO2: 60s, PIR: sub-sec)

### 推奨アクション (将来の ML 準備)

- `hourly_aggregates` に `stddev` を追加 (分布情報の保持)
- `raw_events.data` に `fused_value` / `quality` フィールドを追加
- `heartbeat_missed` イベント型の追加 (欠測検知)

## 6. Alternatives Considered

### (A) InfluxDB 即時導入

- **Pros**: ネイティブ時系列圧縮、Flux 集約クエリ、Grafana 直結
- **Cons**: 追加コンテナ管理、Brain の event_store 書込み先を二重化する必要、Phase 0 のデータ量では過剰
- **Verdict**: Phase 1+ のセンサー数増加時に再検討

### (B) PostgreSQL 直接クエリ (Repository なし)

- **Pros**: コード量が少ない
- **Cons**: InfluxDB 移行時に Router 層の全面書換え、テスト困難
- **Verdict**: 移行コスト回避のため不採用
