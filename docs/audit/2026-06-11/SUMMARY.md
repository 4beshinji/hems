# 技術的負債・設計監査サマリ — 2026-06-11

対象リビジョン: `7e77409`(main) — 監査後、2026-06-17 時点で未コミット変更あり。
調査方式: 6 並列調査(前回監査照合 / セキュリティ / Brain / Backend+ブリッジ / インフラ+ドキュメント / Frontend)+ 主要矛盾点のコードレベル裏取り。
後続の実行計画: [`../../refactor/2026-06-11/PLAN.md`](../../refactor/2026-06-11/PLAN.md)（全 Wave 完了済み）。

## 1. 前回監査(2026-05-25)からの差分

- **非 deferred 34 項目は全消化済み**(LEDGER 全 done 行のコミット存在を確認、`git status` clean、1283 tests passed)。
- **意図的 deferred 9 項目が最大の残存負債**: R3.6(threshold 単一ソース化)、R5.1–R5.6(god-function 分割)、R6.1/R6.2(world_model / rules mixin の namespace 脱結合)。
- followups doc の P1(worktree / staging / BACKEND_API_KEY 配線トラップ)は全て解決済み。
- 前回スコープ外のまま残る領域: **frontend(2026-06-17 時点で vitest + MSW 導入済)**、stt、mobile-android、edge/、infra 構成。

## 2. セキュリティ所見

### 確認済みの誤検知(対応不要)

監査過程で出た以下の指摘はコード確認の結果**誤り**だったため、ここに明記して再燃を防ぐ:

| 疑い | 実態 |
|---|---|
| 「backend dashboard router の大部分が無認証」 | `services/backend/main.py:129-156` で全 dashboard router に `dependencies=[Depends(verify_api_key)]` を一括適用済み。mobile は admin=`verify_api_key`、device=`verify_mobile_device` の二段構え |
| 「POSTGRES_PASSWORD デフォルト空」 | compose は `${POSTGRES_PASSWORD:?...}` で必須化済み、env.example も `CHANGE_ME_BEFORE_USE` |
| 「ALTER TABLE f-string は SQLi」 | migration リストはハードコード(`main.py:52-69`)、外部入力なし |
| 「ffmpeg subprocess 注入」 | list-form argv、tempdir 固定名のみ。安全 |
| 「frontend に API key 埋め込み」 | nginx が `Authorization` ヘッダを注入する設計。JS には露出しない |

### 実在する課題(優先度順)

| # | 深刻度 | 場所 | 内容 |
|---|---|---|---|
| S1 | High | `services/brain/src/brain_chat_server.py` / `brain_startup.py:294` 付近 | ~~brain の aiohttp サーバーの `/devices/control`・`/scenes/execute`・zigbee permit_join 等が無認証~~ → **2026-06-30 実装済み**。`brain_auth_middleware` で `/health` 以外の全 endpoint を `HEMS_INTERNAL_TOKEN` Bearer 検証。backend proxy(`chat.py`/`scenes.py`/`automations.py`/`devices.py`/`home.py`)も `internal_auth_headers()` で token を送信(commit `38f5937`) |
| S2 | Medium | `services/_common/hems_common/validation.py` + brain `device_id_validator.py` / `devices/registry.py` / `devices/base.py` + backend `routers/devices.py` | ~~`device_id` / `vendor_ref` に文字種検証がなく~~ → **2026-06-30 実装済み**。`services/_common/hems_common/validation.py` で `^[\w.\-]+$` 検証を共通化。brain `device_id_validator.py`、`devices/registry.py` dispatch、`devices/base.py` `DispatchContext.resolve_ref`、backend `routers/devices.py` `_ensure_valid_device_id` で二層検証(commit `3e19318` / W1.8 `819587e`) |
| S3 | Medium | 各ブリッジ HTTP API | stt 以外のブリッジの REST endpoint は LAN-trusted 前提の無認証(`verify_bridge_key` が no-op)。127.0.0.1 バインドで外部露出はないが、`HEMS_INTERNAL_TOKEN` の横展開で同一ホスト内も統一可能 |
| S4 | Medium | hardening-audit-2026-04 P1 群 | **部分的実装済み**: `/devices/{id}/control` params 検証は `device_control_validator` へ共通化(commit `46230a2`)、chat rate limit は `chat.py` TokenBucket で実装、**webhook replay 防御は実装済み**(biometric-bridge で `X-Timestamp`/`X-Nonce` 付加、backend `verify_signature_with_replay` で ±5min ウィンドウ検証)、**CSP ヘッダは実装済み**(`services/frontend/nginx.conf`)。**未着手**: TLS/HSTS(LAN 運用前提、distribution Phase と同期) |
| S5 | Low | `tests/security/` | `poc_mqtt_acl.sh`・`test_mqtt_acl.py`・`test_device_id_injection.py`・`test_unauth_coverage.py` が存在。MQTT ACL 拒否・無認証 endpoint 網羅・device_id injection のカバレッジを追加済み(commit `578a1ba` 以降)。`poc_unauth_api.sh` も維持 |

P0 群(MQTT 認証/ACL、port の 127.0.0.1 バインド、シークレット排除)は**実装済みで健全**。

## 3. アーキテクチャ負債(Brain)

- **god-function は分割済み**(前回 deferred の通り): `cognitive_cycle` は `_run_preflight` / `_run_fallback_guards` / `_build_cycle_context` / `_run_react_loop` / `_postprocess_cycle` の 5 フェーズに分割、`RuleEngine.evaluate` / `evaluate_critical` は domain mixin メソッド群に分解、`_process_mqtt` は enrich / classifier feed / timeline trigger / intervention / schedule-learner feed / wake-up detection / event_store persist / device registry / cycle trigger の 9 ステップに分割、`_get_physical_context` / `_update_biometric_state` は section builder / テーブル駆動ハンドラに分割。
- **準循環 import**: ~~world_model / rules mixin の facade 経由参照~~ → **解消済み**。W2.2 / W2.3 で stdlib / dataclass / 定数は直接 import され、新 domain 追加時の facade re-export 更新は不要になった。
- **新たな肥大**: `device_dispatcher.py` は **60 行の後方互換 facade** に縮小(実装は `services/brain/src/devices/` サブパッケージへ移行)。`dashboard_client.py` は **294 行**に縮小し、`dashboard_transport.py` / `dashboard_mappers.py` に HTTP / マッピング責務を分離。
- **二重定義**: ~~`sanitizer.py` `_ALLOWED_ACTIONS` と `device_dispatcher.py` `ALLOWED_ACTIONS`~~ → **統一済み**。device 系 allowlist は `services/brain/src/devices/actions.py` の `DEVICE_ALLOWED_ACTIONS` を単一ソースとし、sanitizer 側は `_ALLOWED_BROWSER_ACTIONS` にリネーム。
- **event_store スケール懸念**: 730d retention は SQLite 既定構成で raw_events が ~1.5 億行規模になりうる。retention の DB バックエンド別デフォルト分岐がない。
- **tool 整合は健全**: schema 58 = handler 58 の完全一致を再確認。ただし `get_active_tasks` のみ無引数特例(`tool_executor.py:104-105`)という署名不統一あり。
- **ShoppingState**: R1.3 で reducer 追加済みだが、context_builder では依然 context に含まれない(live 化の片側のみ)。
- **テスト実態の訂正**: 「brain テスト ~2%」という調査中間報告は誤り。トップレベル `tests/`(80 ファイル)で rule_engine / sanitizer / event_store / persona_rewriter 等は厚くカバー済み。**真のギャップ**は `brain_cognitive` / `brain_mqtt` / `tool_handlers_*` / `LLMRouter` / `PowerModeManager`。

## 4. 冗長な構成(Backend+ブリッジ)

- **MQTTPublisher のコピペ**: ~~9 ブリッジがほぼ同一クラスを独立実装~~ → **統一済み**。`services/_common/hems_common/mqtt.py` の `MqttPublisher` 1 クラスに集約し、retain / エラー処理 / connected 追跡はコンストラクタ knob で表現。
- **lifespan ボイラープレート**: ~~9 ブリッジ × 平均 40 行~~ → **統一済み**。`services/_common/hems_common/lifespan.py` の `bridge_lifespan` を 9 ブリッジで共用。
- **bridge status topic の不統一**: ~~gas/weather/news/knowledge は未発行~~ → **9 ブリッジすべてが `hems/<service>/bridge/status` を発行**。ha/biometric は W3.3/W3.9 で統一済み、残り 4 ブリッジも `hems_common.status.publish_bridge_status` 経由で発行。
- **Device Registry 二重実装**: backend `models.Device`(永続 SoT)と brain `device_registry.py`(in-memory ビュー)計 ~630 行。設計意図(SoT vs cache)は妥当だが、責務境界が doc 化されておらず dispatcher が両者を仲介して肥大。
- **config パターン分裂**: ~~tapo のみ dataclass~~ → **9 ブリッジすべてが dataclass `config.py` ローダーを使用**。
- **依存バージョン不揃い**: ~~fastapi / paho-mqtt の下限指定がブリッジごとにばらばら~~ → **統一済み**。`infra/base/requirements.txt` で共通下限を一元管理し、各ブリッジ requirements は差分のみ。
- **新ブリッジ追加コスト実測: 18–23 ファイル / 300–700 行**(scaffold 3 + compose + env + brain tool 5 点セット + docs + tests)。

## 5. 孤児・残骸

| 対象 | 状態 | 処置案 |
|---|---|---|
| `ext:/sys.stderr`(1.5MB) | gitignore 済み未追跡のデバッグダンプ | ローカル削除 |
| `services/data-bridge/` | Phase-2 placeholder(src/bridges 空、compose 未登録) | 方針決定(実装再開 or アーカイブ)。topics 予約は doc 注記済み |
| `services/mobile-android/`, `apps/healthconnect-companion/` | compose 非参照の Android プロジェクト | リポジトリ分離候補。少なくとも README で位置づけ明記 |
| `hems/`(ネスト) | 重複ディレクトリ | 削除済み(commit `353fd0c`) |
| `scripts/gas-bridge` | 役割明瞭化 | `README.md` 追加済み |
| `scripts/voisona-vm` | PowerShell ヘルパー群 | `setup-scheduled-task.ps1` / `disable-audio-powersave.ps1` / `restart-voisona.ps1` で役割を明示 |
| `ROOMS`(env.example) | コード参照ゼロ | 削除済み |
| `COMPOSE_PROJECT_NAME`(env.example) | compose `name: hems` hardcode 済みで未参照 | 削除済み |

## 6. インフラ・env

- **healthcheck 欠落**: ~~計 6 サービス~~ → **主要サービスに healthcheck を追加済み**(`infra/docker-compose.yml` の `x-healthcheck-*` YAML anchor 経由)。
- **resource limits ゼロ**: ~~全サービス~~ → **主要サービスに memory limits 追加済み**(`x-limits-*` anchor 経由: brain / ollama / perception / stt / bridges 等)。
- **YAML anchor 不使用**: ~~同型 healthcheck ブロックが 15 回以上重複~~ → **`x-healthcheck-*` / `x-limits-*` anchor を導入済み**。
- **env.example 乖離**: ~~未記載 ~30 変数 / 未使用 2 変数~~ → **env.example を compose / コードと同期済み**(未使用変数 ROOMS / COMPOSE_PROJECT_NAME 削除、未記載変数を追加)。`HSA_OVERRIDE_GFX_VERSION` は compose の ollama service に配線済み。
- CI(`.github/workflows/ci.yml`)は lint/test/build-frontend/security に加え、**`docker compose config` validation と `infra/scripts/check_env_compose.py` による env/compose 突合チェックも実装済み**。

## 7. Frontend

- **テスト**: ~~ゼロ~~ → **vitest + MSW 導入済み**。api 層・主要 hooks(`useTasks` / `useVoiceEvents` / `useZones`)・contexts・`useVrmLoader` にテストを追加。
- **同一 queryKey の重複ポーリング**: ~~`['voiceEvents']` × 3 / `['tasks']` × 3 / `['zones']` × 3~~ → **共有 hook 化と `staleTime` 調整で重複排除済み**(`services/frontend/src/hooks/queries/`)。
- **VRM リソース解放漏れ**: ~~`setVrm(null)` のみ~~ → **`VRMUtils.deepDispose(vrm.scene)` で scene 全体の geometry/material/texture を解放**。
- **prop drilling**: ~~Header/AppSidebar に 13+ props~~ → **`AvatarContext` / `AudioContext` / `SttContext` / `AppUiContext` / `PowerContext` 等で Context 分割済み**。
- **env var 命名不統一**: ~~`VITE_API_BASE` vs `VITE_BACKEND_URL`~~ → **`VITE_BACKEND_URL` に統一済み**。
- 型安全性は良好(strict、any 2 箇所のみ)。`types.ts` 828 行はドメイン分割余地(未対応・P2)。

## 8. MQTT トピック規約

`office/{zone}/...`(物理センサ)と `hems/...`(その他全部)の二重プレフィックスは SOMS 遺産だったが、**段階移行を実施済み**: 物理センサ・カメラ・活動検出は `hems/sensors/{zone}/{device_type}/{device_id}/{channel}` へ移行。brain は併読期間を経て、残る `office/*` 受信は `office/{zone}/task_report/#` のみ。edge ファームウェア・mosquitto ACL・docs(CLAUDE.md / IMPLEMENTATION_MAP)を更新済み(commit `8197983` / `152fa09` / `e48e47e` / `e8957df`)。
