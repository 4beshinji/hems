# 分割レビュー修正計画 — 2026-07-18

入力:

- [`../../audit/2026-07-18/README.md`](../../audit/2026-07-18/README.md)
- [`biometric-mobile-observation-design.md`](biometric-mobile-observation-design.md)

実装進捗は [`LEDGER.md`](LEDGER.md) で管理する。監査は継続中のため、新しいP0/P1が見つかれば独立rowとして追加する。

## Phase 0 — 独立した緊急修正

| Row | 内容 | 受け入れ条件 | 状態 |
|---|---|---|---|
| P0.1 | task statsのSQLite専用SQLをdialect-neutral化 | PostgreSQL dialect compile + SQLite実行test | Done (`3a91dac`) |
| P0.2a | Brain nested biometric snapshotを型付きBackend schemaで受理・flat化 | 実mapper payloadのcontract test、SQLite/PostgreSQL互換 | Done (2026-07-18) |
| P0.2b | cycle snapshotの無条件history insertをlatest updateへ変更 | 100回POSTしてrow数不変、最新値更新 | Done (2026-07-18) |
| P0.3 | PostgreSQL startup migrationをversioned / fail-fast化 | 旧schema→head migration、失敗時起動停止 | Pending |
| P0.4 | mobile非biometric observationのsilent dropを停止 | webhook→Brain stateまでのcross-boundary test | Phase 1設計に依存 |

## Phase 1 — Canonical biometric/mobile observation

| Row | 内容 | 受け入れ条件 | 状態 |
|---|---|---|---|
| P1.1 | observation envelopeとBackend history schema | ID/source timestamp/aggregation保持、同一ID冪等 | Pending |
| P1.2 | bridge transactional inbox/outbox + private ingest | commit後のみ2xx、再起動後delivery継続 | Pending |
| P1.3 | mobile Backend outbox→bridge合流 | mobile biometricがcanonical MQTT/historyへ一度だけ到達 | Pending |
| P1.4 | Android strict HMAC + durable outbox + permission wiring | nonce/timestamp対応、offline lossなし | Pending |
| P1.5 | MQTT metadataとBrain side-effect dedup | retained/retryでwake/learning一度だけ | Pending |

## 共通ゲート

```bash
make lint
PYTHONPATH=services/brain/src:services/backend:services/_common timeout 1800s \
  .venv/bin/python -m pytest tests/ services/brain/tests/ \
  -v --tb=short -m "not integration and not e2e and not benchmark"
```

Android変更時は両Gradle projectの`test assembleDebug`も実行する。PostgreSQL固有修正はSQLite testだけで完了扱いにしない。
