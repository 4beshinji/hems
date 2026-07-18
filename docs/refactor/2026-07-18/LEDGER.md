# 分割レビュー修正 ledger — 2026-07-18

[`PLAN.md`](PLAN.md) の実装記録。1 row = 1 coherent commitを原則とする。

| Row | 状態 | Commit | 検証 |
|---|---|---|---|
| P0.1 task stats DB portability | Done | `3a91dac` | focused pytest 2 passed、target ruff pass |
| P0.2a biometric snapshot schema / mapping | Pending | — | — |
| P0.2b latest update / history insert停止 | Pending | — | — |
| P0.3 versioned Backend migration | Pending | — | — |
| P0.4 mobile non-biometric reducer | Pending | — | — |
| P1.1–P1.5 canonical observation | Pending | — | — |

監査文書だけのcommit:

- `629ca3a` — review series開始、Android生体・mobile
- `516cd52` — Backend persistence / domain ownership
- `ec1ac15` — Brain world model / MQTT / persistence
- `6817b67` — biometric ingestion
