# リファクタ進捗 ledger — 2026-06-11

監査所見([`docs/audit/2026-06-11/SUMMARY.md`](../../audit/2026-06-11/SUMMARY.md))の実コード反映。参照 doc・手順は
[`PLAN.md`](PLAN.md)・各設計ノート。**1 row = 1 commit**。先頭 `pending` row を 1 つ処理 → lint+test グリーンを
surface → commit → 当該行を `done <sha>` に更新。baseline: lint clean / **1283 passed, 2 skipped, 19 deselected**。

| Wave | # | row(変更) | 対象 file:symbol | 出所 unit | status | commit |
|---|---|---|---|---|---|---|
| W3.9 | 1 | weather-bridge に `verify_internal_token` 配線（/health 無認証維持）+ `HEMS_INTERNAL_TOKEN` env 追加 + 認証 test | `services/_common/hems_common/auth.py`, `services/weather-bridge/src/main.py`, `infra/docker-compose.yml:weather-bridge`, `tests/test_weather_bridge.py` | W3.9-bridge-http-auth-design-note | done | 079bfea |
| W3.9 | 2 | news-bridge に `verify_internal_token` 配線 | `services/news-bridge/src/main.py`, `infra/docker-compose.yml:news-bridge`, `tests/test_news_bridge.py` | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 3 | knowledge-bridge に `verify_internal_token` 配線 | `services/knowledge-bridge/src/main.py`, `infra/docker-compose.yml:knowledge-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 4 | gas-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/gas-bridge/src/main.py`, `infra/docker-compose.yml:gas-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 5 | tapo-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/tapo-bridge/src/main.py`, `infra/docker-compose.yml:tapo-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 6 | switchbot-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/switchbot-bridge/src/main.py`, `infra/docker-compose.yml:switchbot-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 7 | obsidian-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/obsidian-bridge/src/main.py`, `infra/docker-compose.yml:obsidian-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 8 | ha-bridge に `verify_internal_token` 配線 + backend→ha-bridge 呼び出しに Authorization 付与 | `services/ha-bridge/src/main.py`, `services/backend/routers/home.py`, compose, tests | W3.9-bridge-http-auth-design-note | pending | — |
| W3.9 | 9 | biometric-bridge に `verify_internal_token` 配線（/webhook/{vendor} は対象外） | `services/biometric-bridge/src/main.py`, `infra/docker-compose.yml:biometric-bridge`, tests | W3.9-bridge-http-auth-design-note | pending | — |

**残 pending:** W3.9.1–W3.9.9 全 9 row。
