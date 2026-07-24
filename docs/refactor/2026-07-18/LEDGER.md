# 分割レビュー修正 ledger — 2026-07-18

[`PLAN.md`](PLAN.md) の実装記録。1 row = 1 coherent commitを原則とする。

| Row | 状態 | Commit | 検証 |
|---|---|---|---|
| P0.1 task stats DB portability | Done | `3a91dac` | focused pytest 2 passed、target ruff pass |
| P0.2a biometric snapshot schema / mapping | Done | `162de5d` | 非DB focused pytest 2 passed、target ruff pass。既存`tests/test_backend_biometric_router.py` fixture testは60秒間無出力のままtimeout (exit 124) |
| P0.2b latest update / history insert停止 | Done | `162de5d` | fake sessionで100 cycle / add 1回 / commit 100回を検証。既存`tests/test_backend_biometric_router.py` fixture testは60秒間無出力のままtimeout (exit 124) |
| P0.3a Alembic scaffolding / baseline | Done | `db5757e` + this commit | fresh SQLite focused pytest、30 tables、0001/0002分離、二度目no-op、current=head、metadata driftなし。2026-07-25 に長すぎる P1.3a revision ID を修正し PostgreSQL gate を再実行 |
| P0.3b legacy bootstrap / reconciliation | Done | `a56afe6` | SQLite focused pytest 7 passed。empty/full/partial→head、sentinel/未知schema保持、二度目no-op、missing baseline/type/unknown revision fatal |
| P0.3c migration-first runtime cutover | Done | this commit | SQLite migration 10 passed、PostgreSQL 16 fresh/partial/idempotent migration + events schema isolation 1 passed、Brain event store runtime 1 passed、Core E2E 31/31 passed |
| P0.4 mobile non-biometric reducer | Pending | — | — |
| P1.1 observation envelope / Backend canonical store | Done | this commit | typed UTC envelope、immutable observation ID冪等/409、internal-token auth、latest/history分離、SQLite migration/model/route focused 12 passed |
| P1.2a bridge canonical intake transaction | Done | this commit | shared schema、private auth、inbox+metric/backend outbox atomic commit、duplicate/conflict/rollback/legacy併存 focused 5 passed |
| P1.2b bridge canonical delivery worker | Done | this commit | MQTT direct/Backend token POST、status分類、backoff/dead-letter、stale lease、mixed batch、lifecycle/schema upgrade focused 16 passed |
| P1.3a mobile durable observation foundation | Done | this commit | Alembic 0004、legacy/v2 adapter、time/ID semantics、inbox+outbox+device transaction、migration/adapter/helper focused 16 passed |
| P1.3b mobile durable ingress/delivery | Done | this commit | legacy/v2 route、atomic queue/idempotency、MQTT/bridge worker分類・retry・lifecycle focused 16 passed |
| P1.3c–P1.5 Brain reducer / Android / MQTT side-effect dedup | Pending | — | Brain consumer、Android wiringは未変更 |

監査文書だけのcommit:

- `629ca3a` — review series開始、Android生体・mobile
- `516cd52` — Backend persistence / domain ownership
- `ec1ac15` — Brain world model / MQTT / persistence
- `6817b67` — biometric ingestion
