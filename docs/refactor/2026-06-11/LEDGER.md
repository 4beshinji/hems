# リファクタ進捗 ledger — 2026-06-11

監査所見([`docs/audit/2026-06-11/SUMMARY.md`](../../audit/2026-06-11/SUMMARY.md))の実コード反映。参照 doc・手順は
[`PLAN.md`](PLAN.md)・各設計ノート。**1 row = 1 commit**。先頭 `pending` row を 1 つ処理 → lint+test グリーンを
surface → commit → 当該行を `done <sha>` に更新。baseline: lint clean / **1283 passed, 2 skipped, 19 deselected**。

| Wave | # | row(変更) | 対象 file:symbol | 出所 unit | status | commit |
|---|---|---|---|---|---|---|
| W1.1 | 1 | brain chat server に `HEMS_INTERNAL_TOKEN` Bearer 認証 + backend proxy への Authorization 付与 | `services/brain/src/brain_chat_server.py`, `services/brain/src/brain_startup.py`, backend `routers/chat.py`・`routers/devices.py`・`routers/scenes.py`・`routers/automations.py`, `tests/test_brain_chat_auth.py` | PLAN.md W1.1 | done | 38f5937 |
| W1.2 | 2 | `device_id` / `vendor_ref` の文字種検証を backend Device 登録/heartbeat と brain dispatch 直前の二層に追加 | backend `routers/devices.py`・`schemas.py`, brain `device_dispatcher.py` | PLAN.md W1.2 | done | 0049d4f |
| W1.3 | 3 | webhook replay 防御: biometric / mobile の HMAC に timestamp + nonce(±5min window) | `services/biometric-bridge/src/main.py`, backend `routers/mobile.py`, `tests/test_*_webhook*.py` | PLAN.md W1.3 | done | a394e67 |
| W1.4 | 4 | `/devices/{id}/control` の params schema 検証（sanitizer の検証を REST 経路にも適用） | backend `routers/devices.py`, `services/brain/src/device_control_validator.py` | PLAN.md W1.4 | done | 46230a2 |
| W1.5 | 5 | chat エンドポイントの rate limit（in-memory token bucket） | backend `routers/chat.py`, `tests/test_chat_rate_limit.py` | PLAN.md W1.5 | done | 27f357c |
| W1.6 | 6 | nginx に Content-Security-Policy ヘッダ追加 | `services/frontend/nginx.conf` | PLAN.md W1.6 | done | 015a4a4 |
| W1.7 | 7 | `tests/security/` 拡充: MQTT ACL 拒否 poc 復元、無認証アクセス網羅、W1.2 injection test | `tests/security/` | PLAN.md W1.7 | done | 578a1ba |
| **W1.8** | **8** | **(メタ監査追加分) `device_id` / `vendor_ref` 検証の backend/brain 統一 + パスパラメータ検証。連続ドット・先頭/末尾ドットを共通化し、`services/_common/hems_common/validation.py` へ集約** | `services/_common/hems_common/validation.py`, `backend/schemas.py`, `brain/device_id_validator.py`, `backend/routers/devices.py`, `backend/main.py` | W1.2-unified-device-id-validation-design-note | done | 819587e |
| W3.9 | 1 | weather-bridge に `verify_internal_token` 配線（/health 無認証維持）+ `HEMS_INTERNAL_TOKEN` env 追加 + 認証 test | `services/_common/hems_common/auth.py`, `services/weather-bridge/src/main.py`, `infra/docker-compose.yml:weather-bridge`, `tests/test_weather_bridge.py` | W3.9-bridge-http-auth-design-note | done | d5b9907 |
| W3.9 | 2 | news-bridge に `verify_internal_token` 配線 | `services/news-bridge/src/main.py`, `infra/docker-compose.yml:news-bridge`, `tests/test_news_bridge.py` | W3.9-bridge-http-auth-design-note | done | 7bd9553 |
| W3.9 | 3 | knowledge-bridge に `verify_internal_token` 配線 | `services/knowledge-bridge/src/main.py`, `infra/docker-compose.yml:knowledge-bridge`, tests | W3.9-bridge-http-auth-design-note | done | 0d90119 |
| W3.9 | 4 | gas-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/gas-bridge/src/main.py`, `infra/docker-compose.yml:gas-bridge`, tests | W3.9-bridge-http-auth-design-note | done | 5eb6273 |
| W3.9 | 5 | tapo-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/tapo-bridge/src/main.py`, `infra/docker-compose.yml:tapo-bridge`, tests | W3.9-bridge-http-auth-design-note | done | db9c473 |
| W3.9 | 6 | switchbot-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/switchbot-bridge/src/main.py`, `infra/docker-compose.yml:switchbot-bridge`, tests | W3.9-bridge-http-auth-design-note | done | f3b578d |
| W3.9 | 7 | obsidian-bridge に `verify_internal_token` 配線（/health 無認証維持） | `services/obsidian-bridge/src/main.py`, `infra/docker-compose.yml:obsidian-bridge`, tests | W3.9-bridge-http-auth-design-note | done | c8b9acb |
| W3.9 | 8 | ha-bridge に `verify_internal_token` 配線 + backend→ha-bridge 呼び出しに Authorization 付与 | `services/ha-bridge/src/main.py`, `services/backend/routers/home.py`, compose, tests | W3.9-bridge-http-auth-design-note | done | 4a46df5 |
| W3.9 | 9 | biometric-bridge に `verify_internal_token` 配線（/webhook/{vendor} は対象外） | `services/biometric-bridge/src/main.py`, `infra/docker-compose.yml:biometric-bridge`, tests | W3.9-bridge-http-auth-design-note | done | e3d3780 |
| **W4.6** | **1** | **(メタ監査追加分) PostgreSQL 既定化の zero-config UX。`make quickstart` / `infra/scripts/init_env.py` で安全なランダム値を自動生成。SQLite 軽量オプションを `docker-compose.sqlite-lite.yml` で維持。移行スクリプトの dry-run + サマリ強化** | `Makefile`, `infra/scripts/init_env.py`, `env.example`, `infra/docker-compose.sqlite-lite.yml`, `infra/scripts/migrate_sqlite_to_pg.py`, README/CLAUDE.md/distribution.md/db-improvement-plan.md | W4.6-postgres-zero-config-design-note | done | 7a26322 |

> W3.9.1 ゲート結果 (2026-06-16): `make lint` clean / pytest `2105 passed, 2 skipped, 44 deselected, 7 failed`。失敗 7 件は本 row 変更前から存在する `test_backend_home_router` の 503 系 3 件 + `test_knowledge_bridge` / `test_news_bridge` / `test_obsidian_bridge` の import 系 4 件。
>
> W3.9.2–W3.9.9 一括ゲート結果 (2026-06-16): `make lint` clean / pytest `2153 passed, 8 skipped, 44 deselected, 3 failed`。失敗 3 件は引き続き `test_backend_home_router` の 503 系（HA_BRIDGE_URL 未設定時の挙動）。
>
> 横断 commit:
> - `fe5e294` infra(compose): pass HEMS_INTERNAL_TOKEN to all 9 bridges
> - `18fcc5b` feat(brain,backend): pass HEMS_INTERNAL_TOKEN to internal bridge HTTP calls（backend→ha-bridge + brain→news/knowledge/biometric/obsidian/ha/tapo/switchbot）
>
> W1.8 ゲート結果 (2026-06-16): `make lint` clean / pytest `2169 passed, 8 skipped, 44 deselected, 3 failed`。失敗 3 件は引き続き `test_backend_home_router` の 503 系（HA_BRIDGE_URL 未設定時の挙動）。
>
> W4.6 ゲート結果 (2026-06-16): `make lint` clean / pytest `2169 passed, 8 skipped, 44 deselected, 3 failed`。失敗 3 件は同じく `test_backend_home_router` の 503 系。

**残 pending:** なし。PLAN.md 2026-06-11 の全 row 完了。W1.1–W1.7 / W2 / W3 / W4.1–W4.5' / W5 は main 上で先行実装済みのため本 LEDGER には未追記。
