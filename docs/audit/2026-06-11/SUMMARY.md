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
| S1 | High | `services/brain/src/brain_chat_server.py` / `brain_startup.py:217` 付近 | ~~brain の aiohttp サーバーの `/devices/control`・`/scenes/execute`・zigbee permit_join 等が無認証~~ → **2026-06-30 実装済み**。`brain_auth_middleware` で `/health` 以外の全 endpoint を `HEMS_INTERNAL_TOKEN` Bearer 検証。backend proxy(`chat.py`/`scenes.py`/`automations.py`/`devices.py`/`home.py`)も `internal_auth_headers()` で token を送信(commit `38f5937`) |
| S2 | Medium | `services/brain/src/device_dispatcher.py:730-741` + backend `models.Device` | ~~`device_id` / `vendor_ref` に文字種検証がなく~~ → **2026-06-30 実装済み**。`services/_common/hems_common/validation.py` で `^[\w.\-]+$` 検証を共通化。brain `devices/registry.py` dispatch と `devices/base.py` `DispatchContext.resolve_ref`、backend `routers/devices.py` `_ensure_valid_device_id` で二層検証(commit `3e19318`) |
| S3 | Medium | 各ブリッジ HTTP API | stt 以外のブリッジの REST endpoint は LAN-trusted 前提の無認証(`verify_bridge_key` が no-op)。127.0.0.1 バインドで外部露出はないが、`HEMS_INTERNAL_TOKEN` の横展開で同一ホスト内も統一可能 |
| S4 | Medium | hardening-audit-2026-04 P1 群 | **部分的実装済み**: `/devices/{id}/control` params 検証は `device_control_validator` へ共通化(commit `46230a2`)、chat rate limit は `chat.py` TokenBucket で実装。**未着手**: webhook replay 防御(HMAC に timestamp/nonce)、CSP ヘッダ、TLS/HSTS |
| S5 | Low | `tests/security/` | `poc_unauth_api.sh` のみ。MQTT ACL 拒否テスト(doc 記載の poc_mqtt_acl.sh)が実ファイル不在。device_id injection テストもなし |

P0 群(MQTT 認証/ACL、port の 127.0.0.1 バインド、シークレット排除)は**実装済みで健全**。

## 3. アーキテクチャ負債(Brain)

- **god-function 残存**(前回 deferred の通り): `cognitive_cycle` ~470 行、`_process_mqtt` ~240 行、`_get_physical_context` ~257 行、`RuleEngine.evaluate` ~490 行、`_update_biometric_state` ~165 行。
- **準循環 import**: world_model 6 mixin が `from . import world_model as _world_model` で facade 経由参照(stdlib・定数・dataclass まで)。rules 8 mixin も `import rule_engine as _rule_engine` で同型。新 domain 追加のたびに facade の re-export 更新が必須になる構造的摩擦。
- **新たな肥大**: `device_dispatcher.py` 901 行(8 vendor のパーサ+dispatch 混在)、`dashboard_client.py` 758 行(HTTP client + 状態 + キャッシュ混在)。
- **二重定義**: `sanitizer.py:470 _ALLOWED_ACTIONS`(browser 系)と `device_dispatcher.py:813 ALLOWED_ACTIONS`(device 系)が同名異義。誤同期リスク。
- **event_store スケール懸念**: 730d retention は SQLite 既定構成で raw_events が ~1.5 億行規模になりうる。retention の DB バックエンド別デフォルト分岐がない。
- **tool 整合は健全**: schema 58 = handler 58 の完全一致を再確認。ただし `get_active_tasks` のみ無引数特例(`tool_executor.py:104-105`)という署名不統一あり。
- **ShoppingState**: R1.3 で reducer 追加済みだが、context_builder では依然 context に含まれない(live 化の片側のみ)。
- **テスト実態の訂正**: 「brain テスト ~2%」という調査中間報告は誤り。トップレベル `tests/`(80 ファイル)で rule_engine / sanitizer / event_store / persona_rewriter 等は厚くカバー済み。**真のギャップ**は `brain_cognitive` / `brain_mqtt` / `tool_handlers_*` / `LLMRouter` / `PowerModeManager`。

## 4. 冗長な構成(Backend+ブリッジ)

- **MQTTPublisher のコピペ**: 9 ブリッジがほぼ同一クラスを独立実装(~250 行重複)。retain/エラー処理/connected 追跡が無秩序に分岐。
- **lifespan ボイラープレート**: 9 ブリッジ × 平均 40 行(~360 行)の同一パターン(env 読込→MQTT connect→polling task→cleanup)。
- **bridge status topic の不統一**: 規約は `hems/<service>/bridge/status`。2026-06-17 時点で ha/biometric は W3.3/W3.9 で統一済み。gas/weather/news/knowledge は未発行のまま。
- **Device Registry 二重実装**: backend `models.Device`(永続 SoT)と brain `device_registry.py`(in-memory ビュー)計 ~630 行。設計意図(SoT vs cache)は妥当だが、責務境界が doc 化されておらず dispatcher が両者を仲介して肥大。
- **config パターン分裂**: tapo のみ dataclass `load_config()`、他 7 ブリッジは素の `os.getenv`。
- **依存バージョン不揃い**: fastapi / paho-mqtt の下限指定がブリッジごとにばらばら。
- **新ブリッジ追加コスト実測: 18–23 ファイル / 300–700 行**(scaffold 3 + compose + env + brain tool 5 点セット + docs + tests)。

## 5. 孤児・残骸

| 対象 | 状態 | 処置案 |
|---|---|---|
| `ext:/sys.stderr`(1.5MB) | gitignore 済み未追跡のデバッグダンプ | ローカル削除 |
| `services/data-bridge/` | Phase-2 placeholder(src/bridges 空、compose 未登録) | 方針決定(実装再開 or アーカイブ)。topics 予約は doc 注記済み |
| `services/mobile-android/`, `apps/healthconnect-companion/` | compose 非参照の Android プロジェクト | リポジトリ分離候補。少なくとも README で位置づけ明記 |
| `hems/`(ネスト)・`scripts/gas-bridge`・`scripts/voisona-vm` | 役割不明瞭 | 棚卸しして README 1 行ずつでも由来を記録 |
| `ROOMS`(env.example L10) | コード参照ゼロ | 削除 |
| `COMPOSE_PROJECT_NAME`(env.example) | compose `name: hems` hardcode 済みで未参照 | 削除 |

## 6. インフラ・env

- **healthcheck 欠落**: ha-bridge / postgres / weather-bridge ほか計 6 サービス。
- **resource limits ゼロ**: 全サービス。brain / ollama / perception の暴走でホスト全体に波及しうる。
- **YAML anchor 不使用**: 同型 healthcheck ブロックが 15 回以上重複(831 行の主因の一つ)。
- **env.example 乖離**: コードが読むが未記載 ~30 変数(BOOT_LOAD_*、AMBIENT_SPEAK_*、PERSONA_REWRITE_*、VLM_* の一部、STT_BEAM_SIZE、KNOWLEDGE_SOURCE_PWS 等)。逆に未使用 2 変数(ROOMS、COMPOSE_PROJECT_NAME)。`HSA_OVERRIDE_GFX_VERSION` は記載されているが compose の ollama に配線されていない。
- CI(`.github/workflows/ci.yml`)は lint/test/build-frontend/security をカバー。compose config validation と env 突合の自動チェックが未導入。

## 7. Frontend

- **テストゼロ**(vitest 等の設定ファイル自体なし)。
- **同一 queryKey の重複ポーリング**: `['voiceEvents']` × 3 箇所(3s 間隔)、`['tasks']` × 3、`['zones']` × 3。dashboard 全体で 40+ 並行ポーリング。
- **VRM リソース解放漏れ**: `useVrmLoader` cleanup が `setVrm(null)` のみで geometry/texture の `dispose()` なし。モデル切替でリーク。
- **prop drilling**: Header/AppSidebar に 13+ props。Context 分割(Avatar/STT/Audio)推奨。
- **env var 命名不統一**: `VITE_API_BASE`(api.ts)vs `VITE_BACKEND_URL`(vite.config.ts)。
- 型安全性は良好(strict、any 2 箇所のみ)。`types.ts` 828 行はドメイン分割余地。

## 8. MQTT トピック規約

`office/{zone}/...`(物理センサ)と `hems/...`(その他全部)の二重プレフィックスは SOMS 遺産だが、**CLAUDE.md に明文化された現行規約**でもある。edge デバイスのファーム書き換えを伴うため、機械的統一はせず「設計判断として維持」か「互換 window 付き移行」かを PLAN 側で意思決定項目とした。
