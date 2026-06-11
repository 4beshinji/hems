# リファクタリング計画 — 2026-06-11

入力: [`../../audit/2026-06-11/SUMMARY.md`](../../audit/2026-06-11/SUMMARY.md)(本日監査)+ 2026-05-25 監査の deferred 9 行。
進行管理: 着手時に本ディレクトリへ `LEDGER.md` を作成し、1 row = 1 commit の規律を踏襲する(2026-05-25 方式)。

## 検証ゲート(全 Wave 共通)

```bash
make lint
PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest \
  tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"
# baseline: 1283 passed, 2 skipped, 19 deselected — 各 Wave 完了時にこれを下回らないこと
```

挙動変更を含む row(W1 全部、W2 の dispatcher)は該当サービスの docker compose 起動 + 手動疎通も gate に含める。

## 難度とワーカモデルの割当基準

各 row に難度を付記し、実装ワーカのモデルをコスト最適化する。

| 難度 | 定義 | 推奨ワーカ | 条件 |
|---|---|---|---|
| **低** | 機械的・仕様が一意・blast radius 小(grep/置換/追記/設定同期) | Haiku 4.5 | 受け入れ条件をチェックリスト化して渡す。検証ゲート通過が必須 |
| **中** | 複数ファイルだが既存パターン踏襲・設計判断は局所的 | Sonnet 4.6 | row 内の参照実装(例: stt の `_check_auth`)を prompt で明示 |
| **高** | 設計判断を含む・blast radius 大・回帰リスクが test で覆えない | Opus 4.8 以上 | 分割方針を先に短い design note で出させ、承認後に実装 |

運用ルール:

- **高 row の design → 中/低 row への降格**: 高 row でも「設計が確定すれば残りは機械的」なものは、上位モデルが分割方針・インターフェースだけ決め、続きを Sonnet/Haiku に引き継ぐ(W3.1→W3.2 が典型)。
- **反復 row の先頭だけ格上げ**: 同型作業の繰り返し(W3.2 の 9 ブリッジ移行)は、1 件目を Sonnet で実施してパターンを確立し、2 件目以降を Haiku に落とす。
- **レビューは常に実装ワーカより上位**: Haiku 実装は Sonnet 以上、Sonnet 実装の高リスク row は Opus 以上でレビュー。
- 難度に関わらず 1 row = 1 commit、検証ゲートは全 row 共通。

---

## Wave 1 — セキュリティ残課題(P0/P1、見積 2–3 日)

依存なし。最初に実施。

| Row | 内容 | 対象 | 受け入れ条件 | 難度 | ワーカ |
|---|---|---|---|---|---|
| W1.1 | brain chat server に `HEMS_INTERNAL_TOKEN` Bearer 認証(stt の `_check_auth` と同方式)。backend 側 proxy(chat.py / brain.py)に Authorization 付与 | `brain_chat_server.py`, `brain_startup.py`, backend `routers/chat.py`・`routers/brain.py`, compose env | token 未設定時は従来挙動(dev mode)、設定時に 401 を返す test 追加 | 中(参照実装あり、ただし呼び出し元の網羅が肝。2026-05-25 の BACKEND_API_KEY 配線漏れの再演に注意) | Sonnet 4.6 |
| W1.2 | `device_id` / `vendor_ref` の文字種検証 `^[\w.\-]+$` を (a) backend Device 登録/heartbeat、(b) dispatcher の topic 組み立て直前、の二層に追加 | backend `routers/devices.py`・`models.py`, brain `device_dispatcher.py` | 不正 ID の登録拒否 + dispatch 拒否の test。既存 DB 内不正値の startup 時 warning | 中(検証自体は単純だが、既存 DB の実データ互換を壊さない判断が要る) | Sonnet 4.6 |
| W1.3 | webhook replay 防御: biometric / mobile の HMAC に timestamp + nonce(±5min window) | `biometric-bridge`, backend `routers/mobile.py` | replay test(同一署名 2 回目は 401) | 中(プロトコル変更 — companion app 側との互換 window 設計を含む) | Sonnet 4.6 |
| W1.4 | `/devices/{id}/control` の params schema 検証(sanitizer の検証を REST 経路にも適用) | backend `routers/devices.py`, 共用化した validator | LLM 経路と REST 経路が同一 validator を通る test | 中(sanitizer の切り出し方の設計が小さく入る。validator の置き場所だけ先に決めること) | Sonnet 4.6 |
| W1.5 | chat エンドポイントの rate limit(単純な in-memory token bucket で可) | backend `routers/chat.py` | 連打で 429 | 低(独立・定型実装) | Haiku 4.5 |
| W1.6 | nginx に CSP ヘッダ追加 | `services/frontend/nginx.conf` | dashboard が CSP 違反なしで動作 | 中(ヘッダ追記自体は一瞬だが、three.js/VRM/wasm(VAD)/blob worker の許可リスト調整が試行錯誤になる) | Sonnet 4.6 |
| W1.7 | `tests/security/` 拡充: MQTT ACL 拒否 poc 復元、無認証アクセス網羅、W1.2 injection test | `tests/security/` | CI で実行可能(integration marker) | 中(テスト対象仕様は W1.1–W1.5 で確定済みのため判断は少ないが、MQTT broker を絡めた fixture 構築あり) | Sonnet 4.6 |

deferred 可: TLS/HSTS(LAN 運用前提のため distribution Phase と同期)、ブリッジ HTTP への token 横展開(S3、W3.1 の共通ライブラリに同梱すると一括で入る)。

## Wave 2 — 前回 deferred の高 blast-radius 構造改革(P1、見積 5–8 日)

2026-05-25 LEDGER の R3.6 / R5.x / R6.x をそのまま継承。順序が重要:

| Row | 内容 | 元 row | 依存 | 難度 | ワーカ |
|---|---|---|---|---|---|
| W2.1 | threshold を `RuleThresholds` 単一ソース化(world_model 定数 / UPPERCASE / RuleThresholds の三重ソース解消)。DI で mixin に注入 | R3.6 | — | 高(どの値を canonical にするかの設計判断 + 全 rule domain に波及) | Opus 4.8(design note 承認後に実装は Sonnet 可) |
| W2.2 | world_model mixin の facade 脱結合: stdlib・logger は直接 import、dataclass は `data_classes` から、定数は `brain_constants` / thresholds から | R6.1 | W2.1 | 高(置換自体は機械的だが循環 import の解消順序を誤ると即死。import グラフの設計が本体) | Opus 4.8 |
| W2.3 | rules mixin の同型脱結合(`_rule_engine.datetime` 等の排除) | R6.2 | W2.1 | 中(W2.2 で確立したパターンの同型適用) | Sonnet 4.6 |
| W2.4 | `RuleEngine.evaluate`(~490 行)の domain 別評価メソッド抽出 | R5.4 | W2.3 | 高(cooldown 等の共有状態を跨ぐ分割。rule 発火順序の回帰リスク) | Opus 4.8 |
| W2.5 | `cognitive_cycle`(~470 行)分割: `_run_preflight` / `_build_context` / `_run_react_loop` / `_postprocess` | R5.2 | — | 高(本計画の最難 row。fallback Guard 0-4・ReAct iteration・event 書き込みが絡む) | Opus 4.8 以上 |
| W2.6 | `_process_mqtt`(~240 行)分割: enrich / schedule-learner feed / wake 検出の分離 | R5.1 | — | 高(メッセージ順序・副作用の保存が必要) | Opus 4.8 |
| W2.7 | `_get_physical_context`(~257 行)・`_update_biometric_state`(~165 行)分割 | R5.3, R5.5 | W2.2 | 中(純粋な文字列組み立て/テーブル駆動化で、既存 test が厚い領域) | Sonnet 4.6 |
| W2.8 | 分割と同時に各抽出単位へ unit test 追加(`brain_cognitive` / `brain_mqtt` は現状テストゼロ。分割 PR にテストを同梱しないと再びテスト不能サイズに戻る) | — | 各 row | 中(対象の分割が済んでいればテスト自体は定型。fixture 設計のみ初回コストあり) | Sonnet 4.6(初回 fixture は実装 row と同一ワーカ) |

注: R5.6(parse_mqtt / _dict_to_config 可読性)は W3.4 の vendor parser 抽出に吸収。

## Wave 3 — ブリッジ共通基盤と冗長性排除(P1、見積 4–6 日)

| Row | 内容 | 効果 | 難度 | ワーカ |
|---|---|---|---|---|
| W3.1 | 共有パッケージ `services/_common/`(hems-base イメージに同梱)を新設: `MQTTPublisher`(retain/エラー/connected を引数化)、lifespan テンプレート、dataclass Config ローダ、`verify_internal_token`、統一 status publisher | 重複 ~610 行削減、S3 一括解消 | 高(9 ブリッジ全部が乗る API の設計。retain/エラー処理の現状差分をどの引数に吸収するかが本体) | Opus 4.8(API 設計)→ 実装は Sonnet 4.6 |
| W3.2 | 9 ブリッジを順次 `_common` へ移行(1 ブリッジ = 1 commit。weather → tapo → switchbot → gas → news → knowledge → obsidian → ha → biometric の低リスク順) | 挙動互換を test で担保 | 低〜中(1 件目で移行パターン確立後は同型反復。ha=WebSocket reconnect、biometric=send queue の 2 件のみ固有処理が厚い) | 1 件目 Sonnet 4.6 → 2〜7 件目 Haiku 4.5 → ha/biometric は Sonnet 4.6 |
| W3.3 | bridge status topic を `hems/<service>/bridge/status` に統一 + 未発行 4 ブリッジ(gas/weather/news/knowledge)に発行追加。brain 側 subscribe を旧 topic と互換 window 併読 | 監視の一貫性 | 低(W3.1 の status publisher を使うだけ。互換併読も追記のみ) | Haiku 4.5 |
| W3.4 | `device_dispatcher.py`(901 行)を vendor parser クラス群(`HAParser`/`SwitchBotParser`/`TapoParser`/`ZigbeeParser`…)+ dispatch core に分割。`ALLOWED_ACTIONS` を `DEVICE_ALLOWED_ACTIONS` に改名し sanitizer 側 `_ALLOWED_BROWSER_ACTIONS` と区別 | 新 vendor 追加が 1 ファイル追加に | 高(Parser インターフェース設計 + topic 正規表現の挙動保存。物理デバイス操作の回帰は test で覆いきれない) | Opus 4.8 |
| W3.5 | Device Registry の責務境界を doc 化(backend = 永続 SoT、brain = TTL 付き runtime cache)し、dispatcher の仲介ロジックを registry 側へ寄せる。**統合はしない**(in-memory ビューの存在意義は妥当) | 二重実装の誤解消滅 | 中(主体は doc + 小規模な移動。境界の言語化は W3.4 の設計者が兼ねると一貫する) | Sonnet 4.6 |
| W3.6 | `dashboard_client.py`(758 行)を transport / cache / domain mapper に分割 | — | 中(内部分割のみで外部 API 不変。既存 test_dashboard_client_* が回帰網) | Sonnet 4.6 |
| W3.7 | 依存バージョン統一: fastapi / paho-mqtt の下限を `infra/base/requirements.txt` に揃え、ブリッジ個別 requirements は差分のみ | — | 低(機械的な突合と書き換え) | Haiku 4.5 |

## Wave 4 — インフラ・env 整備(P2、見積 2–3 日)

| Row | 内容 | 難度 | ワーカ |
|---|---|---|---|
| W4.1 | env.example 同期: 未記載 ~30 変数の追加(BOOT_LOAD_*、AMBIENT_SPEAK_*、PERSONA_REWRITE_*、VLM_* 完全同期、STT_BEAM_SIZE、KNOWLEDGE_SOURCE_PWS)、未使用 2 変数(ROOMS、COMPOSE_PROJECT_NAME)の削除、`HSA_OVERRIDE_GFX_VERSION` の ollama service への配線 | 低(監査で対象リスト確定済み。突合と追記のみ) | Haiku 4.5 |
| W4.2 | compose に YAML anchor 導入(`x-healthcheck-*`、`x-resource-limits-*`)+ 欠落 6 サービスへ healthcheck 追加 + 主要サービスに memory limits(brain 2G / ollama 8G / perception 4G を初期値に実測調整) | 中(anchor 化は機械的だが、limits の初期値は実測調整が要り、誤ると OOM kill で稼働系を壊す) | Sonnet 4.6 |
| W4.3 | CI に `docker compose config` validation と env.example ↔ compose 突合スクリプトを追加(以後の乖離を機械防止) | 中(スクリプト自体は小品だが false positive の調整が要る) | Sonnet 4.6 |
| W4.4 | `ext:/` ローカル削除、`services/data-bridge` の README に「存続決定・C1(Strava/Fitbit)として W3.1 後に実装」と明記、Android 2 プロジェクトの位置づけを各 README に明記 | 低(機械的) | Haiku 4.5 |
| W4.5 | ~~event_store retention の DB 別デフォルト~~ → **2026-06-11 決定により W4.5'(PostgreSQL 既定化)に差し替え**。下記「意思決定記録」セクション参照 | — | — |

## Wave 5 — Frontend 品質(P2、見積 3–4 日)

| Row | 内容 | 難度 | ワーカ |
|---|---|---|---|
| W5.1 | vitest + MSW 導入、api 層と主要 hooks の test(現状テストゼロの解消が最優先) | 中(初期セットアップの設計 — MSW handler 構成と React Query の test wrapper。以後のテスト追加は低に降格) | Sonnet 4.6 |
| W5.2 | queryKey 重複排除: voiceEvents / tasks / zones を共有 hook 化(`useVoiceEvents()` 等)し、ポーリングを 1 系統に | 中(挙動同一性の確認が画面目視に依存。W5.1 の test を先に通すと安全) | Sonnet 4.6 |
| W5.3 | VRM dispose 処理(`useVrmLoader` cleanup で scene traverse + geometry/material/texture 解放) | 中(コード量は少ないが three.js の解放漏れ/二重解放はクラッシュ・黒画面になりやすく、検証は DevTools メモリプロファイラでの手動確認) | Sonnet 4.6 |
| W5.4 | Context 分割(Avatar/STT/Audio)で Header/AppSidebar の 13+ props を解消 | 中(機械的な移動が主だが再レンダリング境界の設計を 1 段含む) | Sonnet 4.6 |
| W5.5 | `VITE_API_BASE` / `VITE_BACKEND_URL` を後者に統一、`types.ts`(828 行)のドメイン分割 | 低(rename + ファイル分割。tsc が回帰網) | Haiku 4.5 |

## 意思決定記録(2026-06-11 ユーザー決定済み)

1. **MQTT 二重プレフィックス → 段階移行を採用**(推奨案 (a) を棄却)。`office/*` を `hems/sensors/*` へ移行する。W3.8 として計画化(下記)。互換 window を挟むため即時の breaking change はない。
2. **data-bridge → 存続・実装する**。Strava/Fitbit 連携は [`../../feature-proposals-2026-06-11.md`](../../feature-proposals-2026-06-11.md) C1 として W3.1 完了後に着手。W4.4 から「方針決定」項目を削除済み。
3. **PostgreSQL 既定化に踏み込む**。retention 短縮(旧 W4.5)は不要になり、W4.5 を「PostgreSQL 既定化 + SQLite→PG 移行」に差し替え。retention は 730d を維持。

### W3.8(決定 1 の計画化)— `office/*` → `hems/sensors/*` 段階移行

| Phase | 内容 | 難度 | ワーカ |
|---|---|---|---|
| W3.8a | brain `mqtt_router.py` で `office/{zone}/...` と `hems/sensors/{zone}/...` を併読(reducer 共通化、二重発火防止のデデュープ付き)。IMPLEMENTATION_MAP §4 に移行状態を明記 | 中(reducer 自体は共通、デデュープ条件の設計のみ) | Sonnet 4.6 |
| W3.8b | `edge/` 配下ファームの publish 先を `hems/sensors/*` へ変更 + mosquitto ACL の新 topic 追加。**実機への書き込みはユーザー作業**(コード変更はワーカ、flash と疎通確認は手元) | 中(コード変更は機械的だが実機検証が律速) | Sonnet 4.6 + ユーザー実機作業 |
| W3.8c | 全 edge デバイスの移行確認後、`office/*` subscribe・ACL・docs(CLAUDE.md トピック規約 / IMPLEMENTATION_MAP / CLAUDE-bridges)を削除・更新 | 低(削除と doc 同期のみ。着手条件 = 旧 topic の受信が 7 日間ゼロ) | Haiku 4.5 |

### W4.5 差し替え(決定 3 の計画化)— PostgreSQL 既定化

| Row | 内容 | 難度 | ワーカ |
|---|---|---|---|
| W4.5' | PostgreSQL を既定 DB に昇格: compose の `postgres` を profile 不要のコアサービス化、backend / brain event_store の `DATABASE_URL` デフォルト切替、SQLite は `--profile sqlite-lite` 相当の軽量オプションとして温存。SQLite→PG データ移行スクリプト(tasks / shopping / event_store の 3 系統、dry-run モード付き)。CLAUDE.md「SQLite default」記述・README・`db-improvement-plan.md`・distribution.md の整合更新 | 高(既存稼働データの無損失移行 + zero-config だった初期体験の再設計。移行スクリプトの設計は design note 先行) | Opus 4.8(設計)→ Sonnet 4.6(実装) |

## 工数サマリと推奨順序

```
W1 (2–3d) → W2 (5–8d) → W3 (5–8d, W3.8a-b 含む) → W4 (4–6d, W4.5' 含む) → W5 (3–4d)   計 19–29 日
```

W1 と W5 は他 Wave と独立で並行可。W2 → W3.4 は brain を連続で触るため直列推奨。W3.8c は実機移行完了待ちのため非同期(他 Wave をブロックしない)。W4.5' は distribution.md の Phase 計画と整合を取ってから着手。

---

## 拡張可能性への示唆

調査で判明した「新規追加 1 件あたりの摩擦」と、各 Wave がそれをどう下げるか:

| 拡張シナリオ | 現状コスト | ボトルネック | 改善後 |
|---|---|---|---|
| 新ブリッジ追加 | 18–23 ファイル / 300–700 行 / 2–3h | scaffold 3 ファイル + compose + env + brain tool 5 点セットが全て手作業 | W3.1/W3.2 で scaffold が `_common` import + 差分のみ(~8 ファイル)。さらに下げるなら scaffold generator(`make new-bridge name=foo`)を W3 完了後に検討 |
| 新 tool 追加 | 5 ファイル同時修正(schema / registry / dispatch / handler / sanitizer 許可リスト) | 許可リスト更新忘れを検出するテストがない | schema↔handler 一致 test は既存。sanitizer 許可リストを tool_registry から自動導出する row を W2 完了後に追加可能 |
| 新 rule domain 追加 | mixin 作成 + facade re-export + threshold 三重定義 | 準循環 import 規約への追従が暗黙 | W2.1–W2.3 後は「mixin 1 ファイル + RuleThresholds 1 フィールド」で完結 |
| 新 IoT vendor 追加 | device_dispatcher 901 行への追記 | god-module | W3.4 後は Parser クラス 1 ファイル追加 |
| イベント駆動拡張 | `hems/services/{name}/event` は 30s サイクル待ち(既知 gap) | 即時トリガ経路の不在 | wiring-gap-06 の Wave 計画に既出。W2.6 で `_process_mqtt` が分割されると immediate-dispatch hook の挿入点が自然に生まれる |
| マルチ occupant / 配布 | guest-mode・BACKEND_API_KEY は単一テナント前提 | 認可モデルがバイナリ(key あり/なし) | distribution.md の Phase 計画と合流。W1 の internal token 統一が前提整備になる |
