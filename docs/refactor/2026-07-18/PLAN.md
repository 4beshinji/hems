# 分割レビュー修正計画 — 2026-07-18

入力:

- [`../../audit/2026-07-18/README.md`](../../audit/2026-07-18/README.md)
- [`biometric-mobile-observation-design.md`](biometric-mobile-observation-design.md)
- [`backend-migration-design.md`](backend-migration-design.md)

実装進捗は [`LEDGER.md`](LEDGER.md) で管理する。監査は継続中のため、新しいP0/P1が見つかれば独立rowとして追加する。

## Phase 0 — 独立した緊急修正

| Row | 内容 | 受け入れ条件 | 状態 |
|---|---|---|---|
| P0.1 | task statsのSQLite専用SQLをdialect-neutral化 | PostgreSQL dialect compile + SQLite実行test | Done (`3a91dac`) |
| P0.2a | Brain nested biometric snapshotを型付きBackend schemaで受理・flat化 | 実mapper payloadのcontract test、SQLite/PostgreSQL互換 | Done (2026-07-18) |
| P0.2b | cycle snapshotの無条件history insertをlatest updateへ変更 | 100回POSTしてrow数不変、最新値更新 | Done (2026-07-18) |
| P0.3a | Alembic scaffolding + fixed baseline revision | fresh SQLite/PostgreSQL→head、metadata driftなし | Done (2026-07-19) |
| P0.3b | unversioned legacy DB bootstrap / reconciliation | 完全/部分schemaをidempotent revisionで検証・reconcile、非互換はfatal | Done (2026-07-18) |
| P0.3c | container migration-first cutover + runtime DDL削除 | upgrade成功後のみUvicorn起動、CI PostgreSQL gate | Done (2026-07-19) |
| P0.4 | mobile非biometric observationのsilent dropを停止 | webhook→Brain stateまでのcross-boundary test | Phase 1設計に依存 |

## Phase 1 — Canonical biometric/mobile observation

| Row | 内容 | 受け入れ条件 | 状態 |
|---|---|---|---|
| P1.1 | observation envelopeとBackend history schema | ID/source timestamp/aggregation保持、同一ID冪等 | Done (2026-07-19) |
| P1.2a | bridge transactional inbox/outbox + private ingest受理境界 | commit後のみ2xx、同一ID冪等、異body 409 | Done (2026-07-19) |
| P1.2b | bridge delivery worker | MQTT/Backend停止後・再起動後delivery継続 | Done (2026-07-19) |
| P1.3a | mobile observation schema/adapter/inbox/outbox foundation | legacy/v2 time semantics、ID冪等、transaction helper。router未配線 | Done (2026-07-19) |
| P1.3b | mobile webhook→durable outbox配線 | commit後2xx、worker retry、同期publish廃止 | Done (2026-07-19) |
| P1.3c | Brain mobile reducer / biometric metadata consumer | canonical MQTTからstate/side effectへ一度だけ反映 | Pending |
| P1.4 | Android strict HMAC + durable outbox + permission wiring | nonce/timestamp対応、offline lossなし | Pending |
| P1.5 | MQTT metadataとBrain side-effect dedup | retained/retryでwake/learning一度だけ | Pending |

## 2026-07-25 post-merge verification

P0.3 の PostgreSQL 受け入れ条件を fresh Docker volume で再検証した際、P1.3a で追加された revision ID
`0004_mobile_observation_foundation` が Alembic 標準の `version_num VARCHAR(32)` を超えることを検出した。
revision ID を `0004_mobile_observation` に短縮し、旧 ID を持つ SQLite DB は bootstrap 時に正規化する。
専用 PostgreSQL 16 DB で fresh / partial / idempotent migration と `events` schema 非干渉を再検証済み。

## 共通ゲート

```bash
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common timeout 1800s \
  .venv/bin/python -m pytest tests/ services/brain/tests/ \
  -v --tb=short -m "not integration and not e2e and not benchmark"
```

Android変更時は両Gradle projectの`test assembleDebug`も実行する。PostgreSQL固有修正はSQLite testだけで完了扱いにしない。
