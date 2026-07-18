# リファクタ進捗 ledger — 2026-06-11

> **Status as of 2026-07-18:** 本 ledger は当時の server-side scope の完了記録。Android client は当時の監査対象外であり、W1.3 は
> client の timestamp / nonce HMAC 移行を含む end-to-end 完了を意味しない。後続所見は
> [`../../audit/2026-07-18/android-biometric-mobile.md`](../../audit/2026-07-18/android-biometric-mobile.md) を参照。

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
| W3.8a | 1 | MQTT 段階移行第 1 段: brain `mqtt_router.py` で `office/{zone}/...` と `hems/sensors/{zone}/...` を併読(dedupe 付き) | `services/brain/src/world_model/mqtt_router.py`, `services/brain/src/brain_mqtt.py`, docs | PLAN.md W3.8a | done | `8197983` |
| W3.8b | 1 | edge/infra ファームウェアの publish 先を `hems/sensors/*` へ移行 + mosquitto ACL 新 topic 追加 | `edge/*/main.py`, `infra/mosquitto/acl.txt`, `edge/lib/soms_mcp.py` | PLAN.md W3.8b | done | `152fa09` |
| W3.8c | 1 | 全 edge デバイス移行確認後、`office/*` subscribe・ACL・docs を削除・更新し `hems/sensors/*` を canonical に | `services/brain/src/brain_mqtt.py`, `edge/lib/soms_mcp.py`, `infra/mosquitto/acl.txt`, `tests/security/test_mqtt_acl.py`, docs | PLAN.md W3.8c | done | `e48e47e` / `e8957df` |
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
| **W2.2** | **1** | **world_model mixin の facade 脱結合: stdlib・logger は直接 import、dataclass は `data_classes` から、定数・util は `constants` / `sanitizer` / `vip_detector` から直接参照。準循環 import 解消** | `services/brain/src/world_model/{presence,mqtt_router,physical_updates,user_updates,digital_updates,context_builder}.py`, `services/brain/src/world_model/{constants,sanitizer,vip_detector}.py` | PLAN.md W2.2 | done | `d8a7c33` |
| **W2.3** | **2** | **rules mixin の facade 脱結合: `_rule_engine.datetime` / `random` / `parse_iso_ts` を stdlib / `brain_utils` から直接 import。関連 test の patch 対象も各 rules モジュールに更新** | `services/brain/src/rules/{services,biometric,environment,gas,home,perception}.py`, `rule_engine.py`, `tests/test_rule_engine_*.py` | PLAN.md W2.3 | done | `36daf72` |
| **W2.3** | **3** | **(フォローアップ) world_model / rules mixin の facade 参照を一掃する追加クリーンアップ** | `services/brain/src/world_model/*.py`, `services/brain/src/rules/*.py`, `rule_engine.py` | PLAN.md W2.2-W2.3 残清理 | done | `13b2a24` |
| W2.4 | 1 | `RuleEngine.evaluate` / `evaluate_critical` を domain mixin メソッド群に分割(発火順序厳密保存) | `services/brain/src/rule_engine.py`, `services/brain/src/rules/{environment,pc,device,service,gas,home,zigbee,screen,biometric,perception,shopping}.py`, `tests/test_rule_engine_evaluate_characterization.py` | PLAN.md W2.4 | done | `e99560c` / `ea05a56` |
| W2.5 | 1 | `cognitive_cycle` を 5 フェーズに分割: `_run_preflight` / `_run_fallback_guards` / `_build_cycle_context` / `_run_react_loop` / `_postprocess_cycle` | `services/brain/src/brain_cognitive.py`, `tests/test_brain_cognitive_characterization.py` | PLAN.md W2.5 | done | `d5de32c` |
| W2.6 | 1 | `_process_mqtt` を 9 ステップに分割: enrich / classifier feed / timeline trigger / intervention / schedule-learner occupancy/sleep / wake-up detection / event_store persist / device registry / cycle trigger | `services/brain/src/brain_mqtt.py`, `tests/test_brain_mqtt_characterization.py` | PLAN.md W2.6 | done | `54fd034` |
| W2.7a | 1 | `_get_physical_context` を section builder メソッド群に分割 | `services/brain/src/world_model/context_builder.py`, `tests/test_get_physical_context_characterization.py` | PLAN.md W2.7 | done | `8d123b5` |
| W2.7b | 1 | `_update_biometric_state` をテーブル駆動ハンドラに分割 | `services/brain/src/world_model/user_updates.py`, `tests/test_update_biometric_state_characterization.py` | PLAN.md W2.7 | done | `70bb5cf` |
| W2.8 | 1 | 各 god-function 分割単位への characterization テスト追加(W2.4-W2.7 の C1 テスト群) | `tests/test_*_characterization.py` | PLAN.md W2.8 | done | `4f5e008` / `b773571` / `4bdcd58` / `fb96c13` / `50e27c7` |

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
>
> W2.2–W2.3 ゲート結果 (2026-06-17): `make lint` clean / pytest `2173 passed, 8 skipped, 44 deselected, 3 failed`。失敗 3 件は引き続き `test_backend_home_router` の 503 系（full-suite 実行時のみ発生する既存の test isolation 問題）。`test_rule_engine_environment.py` の datetime patch 対象を `rule_engine` から各 rules モジュールに修正し、40 件すべてパス。

> 推奨フォローアップ作業結果 (2026-06-17): [`RECOMMENDED_FOLLOW_UPS.md`](RECOMMENDED_FOLLOW_UPS.md) の全 row を実施。
>
> | # | row | status | commit |
> |---|---|---|---|
> | H1 | LLM/chat/REST 経路の device_id 検証を統一 | done | `3e19318` |
> | M1 | backend → ha-bridge Authorization ヘッダー付与テスト | done | `631795f` |
> | M2 | 内部 HTTP caller 用 Bearer ヘルパー集約 | done | `42a43b2` |
> | M3 | frontend API クライアントの二重実装と VITE_BACKEND_URL 対応 | done | `27d50a5` |
> | M4 | staleTime = refetchInterval の挙動確認 | done | `379644d` |
> | M5 | W2.2 脱結合の軽微クリーンアップ | done | `5e43428` |
> | L1 | コメント・ドキュメントの陳腐化修正 | done | `753bdd4` |
> | L2 | brain chat server health path trailing slash 対応 | done | `b467fd6` |
> | L3 | 移行スクリプトの恒真 assertion 修正 | done | `1e95797` |
> | L4 | init_env.py のユニットテスト追加 | done | `3fad1a8` |
> | L5 | bridge_lifespan startup 失敗時の disconnect 保証 | done | `626e7c3` |
> | L6 | MqttPublisher.subscribe / set_message_callback の単体テスト追加 | done | `6aa5f8f` |
>
> ゲート結果: `make lint` clean / pytest `2217 passed, 8 skipped, 47 deselected, 0 failed`。
> 注: M2 で backend router が `hems_common.auth` を import するようになったため、pytest 実行時の `PYTHONPATH` に `services/_common` を含める必要がある（`tests/conftest.py` および CI でも同様）。
>
> W3.8c 追加クリーンアップ (2026-06-17): `brain_mqtt.py` の falsy センサ値破棄を修正、`edge/lib/soms_mcp.py` の旧 `office/*` prefix オーバーライドを削除、`infra/mosquitto/aclfile` に `hems-iot` ユーザーを同期、`tests/security/test_mqtt_acl.py` の `aclfile` 参照を `acl.txt` に統一。非 integration pytest は `2219 passed, 8 skipped, 47 deselected, 0 failed`。integration ACL 許可テスト3件は実行中ブローカーが新 ACL/パスワードを読み込んでいないため失敗し、コンテナ再起動で解消。

**残 pending:** なし。PLAN.md 2026-06-11 の全 row 完了。W1.1–W1.7 / W2.1–W2.8 / W3 / W4.1–W4.6 / W5 は main 上で実装済み。
