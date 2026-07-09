# リファクタ計画: 監査所見の実コード反映(自走 /goal の参照 doc)

> **HISTORICAL / COMPLETED** — 本計画は 2026-05-25 のリファクタ計画です。非 deferred 行は全て [`LEDGER.md`](LEDGER.md) で完了し、deferred 9 行は [`../2026-06-11/PLAN.md`](../2026-06-11/PLAN.md) に移管済み。現行の計画は `../2026-06-11/` を参照してください。
>
> **この doc の役割**: `/goal` 自走リファクタの **in-repo SoT(参照ドキュメント)**。/clear を跨いで生存させる。
> 各セッションはまず [`LEDGER.md`](LEDGER.md) を読み、先頭 pending row を 1 つ処理して commit する。
> 進捗 ledger は [`LEDGER.md`](LEDGER.md)、所見の出所は [`docs/audit/2026-05-25/`](../../audit/2026-05-25/)。

## Context — なぜこれをやるか

直前の「サービス単位 実装監査」([`docs/audit/2026-05-25/`](../../audit/2026-05-25/SUMMARY.md))は
**監査 + doc 乖離是正のみ・コード無改変**で完了した(P0=0)。P1/P2 の所見は per-service doc に
「後続リファクタがそのまま着手できる」粒度で記録済。**本パスはその所見を実コードに反映する**フェーズ。

`/goal` の評価役(Haiku)は会話に **surface された出力のみ**から終端判定する(評価役はファイル/コマンドを
実行しない)。よって各 row 完了時に `lint`/`test`/`git` の結果を必ず transcript に出力してから commit する。

## 決定事項(ユーザー確認済 2026-05-25)

| 項目 | 決定 |
|---|---|
| 範囲 | **P1+P2 全部(deep-audit 除く)**。機能バグ + god-function 分割 + namespace 脱結合 + 命名/型/magic number/重複/session 共有。annotator・voice_capsule deep-audit、knowledge RRF 行精査、biometric 疲労式精査は「監査(読む)作業」=**対象外** |
| backend auth | **共有鍵認証を実装**(mobile と同様の最小 shared-key 検証)。挙動変更・env 追加・test 追加あり |
| 出力先 | `docs/refactor/2026-05-25/`(本 doc + LEDGER.md) |
| 変更境界 | **実コード変更**。bridge 7個(obsidian/gas/ha/switchbot/tapo/weather/news)は所見ゼロ→対象外。biometric/knowledge bridge は deferred deep-audit のみ→対象外 |
| コミット | **1 ledger row = 1 コヒーレントな変更 = 1 commit**。push しない。現ブランチ `refactor/upstream-port` |
| 検証 | 各 row で `make lint` && `make test-quick`(**baseline: 1257 passed, 2 skipped, 19 deselected / lint clean**)+ `git diff --stat` sanity。regression が出たら即停止・報告 |

## 中核原則: 1 row = 1 commit + test 網

監査パスは「1 unit = 1 file = 1 commit」だったが、本パスは code 変更のため revert 可能性を優先し
**ledger row 単位で commit** する(1 サービスが複数 row に跨る)。各 row 完了時に lint+test-quick グリーン
(baseline ≥1257 passed)を **transcript に surface** してから commit。これにより /clear を跨いでも進捗が
git に残り、再入時に「次の pending row」が一意に決まる。

## 検証コマンド(重要: venv 必須)

`make test-quick` は PATH 上の `pytest` を呼ぶため **venv を有効化していないと `pytest: not found`** になる。
必ず以下で実行する:

```bash
cd "$(git rev-parse --show-toplevel)"
source .venv/bin/activate
make lint          # ruff check + format check
make test-quick    # pytest tests/ services/brain/tests/ -m "not integration and not e2e and not benchmark"
```

baseline(本パス開始時、2026-05-25): `lint` クリーン / `test-quick` = **1257 passed, 2 skipped, 19 deselected**(~65s)。

## per-row 手順(各 row でこれを踏む)

1. [`LEDGER.md`](LEDGER.md) の先頭 `pending` row を選ぶ。
2. その row の **出所 unit doc**([`docs/audit/2026-05-25/{unit}.md`](../../audit/2026-05-25/))の該当所見を Read。
3. その row の変更**のみ**を適用(scope creep 厳禁。複数 row をまたぐ変更をしない)。
4. `source .venv/bin/activate && make lint && make test-quick` を実行し、**結果(passed 数)を surface**。
5. `git diff --stat` で変更範囲が当該 row scope のみであることを確認・surface。
6. commit(下記コミット規約)。
7. LEDGER の当該行 status を `done <sha>` に更新(この更新も同 commit または直後の小 commit に含めてよい)。
8. /clear 判断(コンテキストが重ければ /clear。再入は下記プロトコル)。

### コミット規約

```
refactor(<unit>): <row 要旨>   例: refactor(automation): _llm_review に LLMResponse.content を使用

<1-2 行で何を・なぜ。出所 audit doc を参照>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

W7 の auth は挙動変更のため `feat(backend): shared-key 認証を実装` とし、test 追加を同 commit に含める。

## 再入プロトコル(/clear 後はこれで始める)

1. `cd "$(git rev-parse --show-toplevel)"`
2. `git log --oneline -8` で最後に done した row を確認
3. 本 doc を Read → [`LEDGER.md`](LEDGER.md) の先頭 `pending` row を選ぶ
4. 出所 unit doc を Read → per-row 手順を実行
5. `source .venv/bin/activate` を忘れない

## Wave / Ledger row 一覧(blast radius 昇順 = 実行順)

機械的・低リスクを先に流して test 網を温め、最後に最高 blast radius の namespace 脱結合を置く。
行番号は監査時点の目安(実装時に再確認)。出所列は `docs/audit/2026-05-25/{unit}.md`。

### W0 — 機能バグ修正(低リスク・高 ROI)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R0.1 | `_llm_review` の戻り値型バグ | `brain/src/automation_engine.py:293-294` `_llm_review` | `llm_client.chat()` は `LLMResponse`。`(response or "").strip()`/`.splitlines()` を `response.content`(+`response.error` ガード)へ。**回帰 test 追加**(llm_review mode が無音 skip しない確認) | rules-automation / llm-tools |
| R0.2 | `should_dispatch` presence 不整合 | `brain/src/task_scheduling/decision.py:13` | camera `count>0` ではなく `world_model.is_anyone_home()`(多ソース)を使用。camera offline でも PC/HR で在宅なら dispatch | world-model |
| R0.3 | falsy-zero 閾値クロス漏れ | `brain/src/world_model/user_updates.py:152,162,209…` | `prev_bpm if prev_bpm else None` → `prev_bpm is not None`。初回 0 を None 扱いして閾値クロスを取りこぼすバグ | world-model |
| R0.4 | dead guard `if inferred is not None` 常真 | `brain/src/brain_mqtt.py:143`(init `:118`) | `inferred` は 0 初期化で None にならず常真。init を `None` にするか guard 撤去+意図 doc。全 MQTT で reconcile_presence が走る負荷も是正 | core-loop |

### W1 — dead code + find-replace 事故(無リスク)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R1.1 | dead code `_build_character_section` 削除 | `brain/src/system_prompt.py:458-529` + `build_system_message` の未使用 `character` 引数 | 呼び出し 0(Stage 2 へ移行済)。関数 + 未使用引数を削除 | core-loop |
| R1.2 | find-replace 事故 `_world_model.time`(コメント) | `brain/src/world_model/digital_updates.py:100,105,116` + `context_builder.py:600` | コメント/docstring 内の `_world_model.time` → `time` へ復元(コード無影響) | world-model |
| R1.3 | dead state `ShoppingState` 除去 | `brain/src/world_model/data_classes.py:708,749` + `world_model.py:276-281` | reducer 無し・context_builder 未参照。world_model から除去(backend DB を SoT とする) | world-model |
| R1.4 | timeline dead param/const | `brain/src/timeline/generator.py:52`(`auth_headers`)・`:21`(`HEMS_HOME_LOCATION_KEYWORDS`) | 未使用 param と未参照 const を削除 | world-model |

### W2 — 命名 / 型 / alias / magic number(低リスク・機械的)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R2.1 | 誤誘導 `_` rename(public 化) | `brain/src/brain_constants.py:79` `_summarize_action`(+3 caller) | 外部 import されているので `summarize_action` へ | core-loop |
| R2.2 | 誤誘導 `_` rename(local) | `brain_mqtt.py:158` `_wake_up_fired`・`brain_cognitive.py:375,429` `_vmap`/`_gpu` | local 変数の先頭 `_` を除去 | core-loop |
| R2.3 | `split_for_speak` alias 撤去 | `boot_load_manager.py:29`・`event_automation.py:16` | `import ... as _split_for_speak` を public 名へ統一 | core-loop / rules-automation |
| R2.4 | 型注釈 `X=None`→`X\|None=None` | `boot_load_manager.py:124`(`now`)・`task_scheduling/priority.py:24`(`task_type`) | default None に合わせ Optional 化 | core-loop / world-model |
| R2.5 | magic number 定数化 | `event_automation.py:318`(`[:67]`→`SPEAK_CHUNK_LIMIT`)・`low_power_mode.py:115`(`25`→`MIN_CYCLE_INTERVAL` を import)・cognitive/loops/mqtt の時間定数(300/1800/7200/600/86400) | 名前付き定数へ(`brain_constants.py` 集約) | core-loop / rules-automation |
| R2.6 | misleading 関数名 `generate_for_today` | `brain/src/timeline/generator.py:314` | 実体は週生成 → `generate_week` rename + docstring 整合 | world-model |
| R2.7 | 雑多な低リスク整理 | `brain_mqtt.py:331`(dup `import json as _json`)・`brain_loops.py:126`(`except (json.JSONDecodeError, Exception)`)・`brain_cognitive.py:449-487`(guard 採番 0/1/2/4)・`system_prompt.py:39-42`(prompt 採番 1/2/4/5)・`brain_chat_server.py`(`aiohttp.web` を module top へ)・`brain_startup.py:94`/`brain_loops.py:56-59`(`event_classifier`/`_bridge_*` を `__init__` 宣言) | 重複 import 削除・冗長 except 単純化・採番連番化・local import hoist・属性 `__init__` 宣言 | core-loop |
| R2.8 | facade 経由 stdlib + docstring | `rules/biometric.py:227`(`_dt = _rule_engine.datetime`→直 import)・`timeline/generator.py:50`("Stateless" 誤 docstring 修正) | stdlib を直 import、docstring を実体に合わせる | rules-automation / world-model |
| R2.9 | env.example 追記 | `env.example` | `AUTOMATION_ENGINE_ENABLED`(default true)を追記 | SUMMARY 未解決 |

### W3 — 重複統合(中リスク)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R3.1 | `_ALLOWED_ACTIONS` 単一 SoT | `device_dispatcher.py:808`(canonical)← `sanitizer.py:385` | dispatcher 側を SoT にし sanitizer は import。二重定義の sync bug 解消 | llm-tools |
| R3.2 | provider tool-call 整形共通化 | `brain_cognitive.py:496-516,540-543` ↔ `brain_chat_server.py:207-227,242-245` | `format_tool_call_blocks(provider,calls)`/`format_tool_result_msg(...)` を共通 util へ抽出 | core-loop |
| R3.3 | PersonaRewriter `_rewrite_impl` 抽出 | `persona_rewriter.py:35-98`/`100-157`(`rewrite`/`rewrite_long`) | ~80% 重複を `_rewrite_impl(message,tone,max_len,max_tokens)` に集約 | llm-tools |
| R3.4 | EventWriter `_bulk_insert` helper | `event_store/writer.py:333-460` | IS_POSTGRES 分岐 INSERT を `_bulk_insert(conn,table,cols,rows,jsonb_cols)` に集約、`tp` を定数化 | world-model |
| R3.5 | snapshot 構築 helper | `brain_cognitive.py:560-579` ↔ `:624-646`(`_record_rule_cycle_summary`) | `_last_cycle_summary` 構築を単一 helper に | core-loop |
| R3.6 | threshold 単一ソース化 | `rule_engine.py:17` + `rules/config.py`(`RuleThresholds`) | world_model 定数 / module UPPERCASE / RuleThresholds の三重ソースを `RuleThresholds` に統一(W6 の前提) | rules-automation |
| R3.7 | `_summarize_action` dict 化 + 重複 block | `brain_constants.py:79-140`(if/elif→dict dispatch + 欠落 tool 追加)・`brain_mqtt.py:301` ↔ `brain_cognitive.py:303`(`if OPENCLAW_ENABLED:` 重複統合) | dispatch table 化、重複条件ブロック統合 | core-loop |
| R3.8 | reducer 重複整理 | `physical_updates.py:20-35`(channel→field を `setattr` 化 + 冗長 `hasattr` 撤去)・`event_automation.py:256-518`(`_action_*` の speak dict helper 抽出) | mapping を setattr、speak dict を helper 化 | world-model / rules-automation |

### W4 — session 共有 + encapsulation(中リスク)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R4.1 | 共有 aiohttp session | `task_scheduling/queue_manager.py:31,60`・`scene_executor.py:41-58`・`voice/src/speech_generator.py:78` | per-call の `ClientSession` 生成を共有 session(`Brain._session`/`dashboard_client.session`/lifespan)注入へ | world-model / rules-automation / voice |
| R4.2 | ScheduleLearner public history API | `timeline/generator.py:82-84,98-99`(getattr `_wake_history` 等) | ScheduleLearner に public な median/history API を追加し private 直アクセス除去 | world-model |
| R4.3 | event_automation public method | `brain_cognitive.py:47`(`_run_batch`→`event_automation._execute_action`) | EventAutomation に public method を生やし private 呼び出し除去 | core-loop |
| R4.4 | `add_task` no-op 明示 | `task_scheduling/queue_manager.py:17-23` | logging stub である旨を docstring 明示 or deprecate(隠れ no-op の解消) | world-model |

### W5 — god-function 分割(高リスク・要 test 網)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R5.1 | `_process_mqtt` 分割(~240L) | `brain_mqtt.py:78-317` | `_enrich_z2m_zone`/`_feed_schedule_learner`/`_detect_wake_up`/`_record_event_store`/`_maybe_trigger_cycle` へ抽出 | core-loop |
| R5.2 | `cognitive_cycle` 分割(~470L) | `brain_cognitive.py:129-602` | `_run_preflight`/`_maybe_rule_only_path`/`_build_user_content`/`_run_react_loop`/`_record_llm_cycle` へ抽出 | core-loop |
| R5.3 | `_get_physical_context` 分割(~257L) | `world_model/context_builder.py:52-309`(+ digital ~161L / user ~135L) | zone/home/weather/biometric sub-builder へ分割 | world-model |
| R5.4 | `RuleEngine.evaluate` 抽出(~490L) | `rule_engine.py:193-684` | 残存 inline(environment: CO2/temp/humidity/pressure/soil/voc/pm25/light/posture, PC: gpu/disk/cpu/mem/proc, screen_time)を `rules/environment.py`・`rules/pc.py` mixin へ。`evaluate` は集約のみに | rules-automation |
| R5.5 | `_update_biometric_state` table-driven(~165L) | `world_model/user_updates.py:121-285` | metric→handler の表駆動化(prev/set/last_update/bridge_connected/record_history/threshold の反復除去) | world-model |
| R5.6 | (任意・余力)readability | `device_dispatcher.py:72-204`(`parse_mqtt` vendor split)・`character_loader.py:273-382`(`_dict_to_config` field-driven) | 読みやすさ向上。リスク低だが優先度低、時間が余れば | llm-tools |

### W6 — namespace 脱結合(最高 blast radius・最後)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R6.1 | world_model mixin 直 import 化 | `brain/src/world_model/*.py`(mqtt_router/physical_updates/digital_updates/user_updates/presence/context_builder ~7file) | facade 経由(`_world_model.time`=stdlib!/`_world_model.logger`/定数/再 export dataclass)を直 import へ。準循環 import 解消 | world-model |
| R6.2 | rules mixin 直 import 化 | `brain/src/rules/*.py`(8 domain + W5 新設 environment.py/pc.py) | `import rule_engine as _rule_engine` 経由の `_rule_engine.datetime`/logger/threshold を直 import へ。R3.6 の `RuleThresholds` 統一を前提 | rules-automation |

### W7 — backend(中リスク・挙動変更)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R7.1 | shared-key 認証実装 | `backend/auth.py:30-31`(`verify_api_key`)・`main.py:132-159`(`_auth`)・`env.example` | mobile(`verify_mobile_device`)同様の最小 shared-key 検証を実装。`BACKEND_API_KEY` env 追加(未設定時の挙動を doc 明記)。`_auth` 命名を実体に合わせる。**test 追加**(鍵あり/なし) | backend |
| R7.2 | ALTER TABLE migration 是正 | `backend/main.py:27-78`(lifespan) | bare `except Exception: pass` を narrow + logging へ。手製 migration の制約を doc 明記(Alembic 導入は **後続**=対象外) | backend |
| R7.3 | chat.py raw SQL → ORM | `backend/routers/chat.py` | raw `text()` を ORM へ(または性能理由を doc 明記)。最悪の broad `except` を narrow 化 | backend |

### W8 — perception / voice(P2 軽量)

| # | row | 対象 file:symbol | 推奨変更 | 出所 |
|---|---|---|---|---|
| R8.1 | perception `_run_vlm_cycle` 抽出(~87L) | `perception/src/main.py:204-291` | tier 選択 / analyze / publish / model_swap を helper 分割。**main.py の class 化全面書換は対象外** | perception |
| R8.2 | voice provider-specific hook 移設 | `voice/src/main.py:75-140`(`_voisona_health_loop`/`_get_voisona_provider`) | VoiSona 固有 health hook を provider class(ABC+factory)へ移設 | voice |

## scope-out(本パスでやらない)

- **bridge 7個**(obsidian/gas/ha/switchbot/tapo/weather/news)— 監査でコード所見ゼロ。
- **biometric-bridge / knowledge-bridge** — deferred deep-audit(疲労式・RRF/embedding 行精査)のみ=「読む」作業。
- **annotator/ ・ voice_capsule/** の行レベル精査(EventClassifier/RulePromoter/ShoppingClassifier/CapsuleBuilder)。
- **perception/voice の main.py 全面 class 化**(R8 は局所抽出のみ)。
- **sanitizer SOMS legacy**(`swarm_hub`/`pump`/`run_pump`)除去 — `send_device_command` 廃止と同期すべき=本パスで廃止しないため後続。
- **frontend(TS)・mobile-android(Kotlin)**。
- **Alembic 等 migration framework 導入**(R7.2 は bare except 是正 + doc のみ)。

## 検証ゲート

- **per-row**: `make lint` クリーン & `make test-quick` グリーン(≥1257 passed)& `git diff --stat` が当該 row scope のみ。
- **終端**: [`LEDGER.md`](LEDGER.md) 全 row `done <sha>` & lint+test-quick グリーン & `git log --oneline` が row 毎 commit & `git status --short` 空 & W7 で追加した auth test グリーン。
- **regression 即停止**: baseline で pass していた test が fail したら、それ以上進めず停止・報告。

## /goal 停止条件(/clear 後に貼る)

```
/goal Refactor pass docs/refactor/2026-05-25 is complete: every row in docs/refactor/2026-05-25/LEDGER.md shows status "done <sha>" (no "pending"/"wip"); after `source .venv/bin/activate`, `make lint` printed clean and `make test-quick` printed all tests passing with zero failures (>=1257 passed, matching baseline) in this session; `git log --oneline` shows one refactor commit per done row on branch refactor/upstream-port; and `git status --short` is empty. Follow docs/refactor/2026-05-25/PLAN.md: each turn, read LEDGER.md, take the FIRST pending row, apply ONLY that change, run `source .venv/bin/activate && make lint && make test-quick`, show `git diff --stat`, commit, and flip the row to "done <sha>". Stop and report immediately if make test-quick regresses any test that passed at baseline. Otherwise stop after 50 turns.
```
