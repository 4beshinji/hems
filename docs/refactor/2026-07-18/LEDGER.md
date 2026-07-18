# 分割レビュー修正 ledger — 2026-07-18

[`PLAN.md`](PLAN.md) の実装記録。1 row = 1 coherent commitを原則とする。

| Row | 状態 | Commit | 検証 |
|---|---|---|---|
| P0.1 task stats DB portability | Done | `3a91dac` | focused pytest 2 passed、target ruff pass |
| P0.2a biometric snapshot schema / mapping | Done | this commit | 非DB focused pytest 2 passed、target ruff pass。既存`tests/test_backend_biometric_router.py` fixture testは60秒間無出力のままtimeout (exit 124) |
| P0.2b latest update / history insert停止 | Done | this commit | fake sessionで100 cycle / add 1回 / commit 100回を検証。既存`tests/test_backend_biometric_router.py` fixture testは60秒間無出力のままtimeout (exit 124) |
| P0.3a Alembic scaffolding / baseline | Done | this commit | fresh SQLite focused pytest 2 passed、30 tables、0001/0002分離、二度目no-op、current=head、metadata driftなし。PostgreSQL gateはP0.3c |
| P0.3b legacy bootstrap / reconciliation | Design Done / Implementation Pending | — | full/partial/incompatible schema fixtures planned |
| P0.3c migration-first runtime cutover | Design Done / Implementation Pending | — | PostgreSQL CI + Uvicorn fail-fast planned |
| P0.4 mobile non-biometric reducer | Pending | — | — |
| P1.1–P1.5 canonical observation | Pending | — | — |

監査文書だけのcommit:

- `629ca3a` — review series開始、Android生体・mobile
- `516cd52` — Backend persistence / domain ownership
- `ec1ac15` — Brain world model / MQTT / persistence
- `6817b67` — biometric ingestion
