# リファクタ進捗 ledger — 2026-05-25

監査所見([`docs/audit/2026-05-25/`](../../audit/2026-05-25/SUMMARY.md))の実コード反映。参照 doc・手順は
[`PLAN.md`](PLAN.md)。**1 row = 1 commit**。先頭 `pending` row を 1 つ処理 → lint+test-quick グリーンを
surface → commit → 当該行を `done <sha>` に更新。baseline: lint clean / **1257 passed, 2 skipped, 19 deselected**。

> 再入(/clear 後): `cd /home/sin/code/claude/hems` → `git log --oneline -8` → 本表の先頭 `pending` row →
> 出所 unit doc Read → `source .venv/bin/activate` → [`PLAN.md`](PLAN.md) per-row 手順。

| Wave | # | row(変更) | 対象 file:symbol | 出所 unit | status | commit |
|---|---|---|---|---|---|---|
| W0 | R0.1 | `_llm_review` LLMResponse→`.content`(+回帰test) | `automation_engine.py:293-294` | rules-automation/llm-tools | done | 2a77241 |
| W0 | R0.2 | `should_dispatch` presence→`is_anyone_home()` | `task_scheduling/decision.py:13` | world-model | done | b47c432 |
| W0 | R0.3 | falsy-zero `prev_bpm is not None` | `world_model/user_updates.py:152,162,209…` | world-model | done | 153ba93 |
| W0 | R0.4 | dead guard `if inferred is not None` 常真 | `brain_mqtt.py:143`(init`:118`) | core-loop | done | 0b1811e |
| W1 | R1.1 | dead code `_build_character_section`+未使用 `character` 削除 | `system_prompt.py:458-529` | core-loop | done | 185eb03 |
| W1 | R1.2 | find-replace 事故 `_world_model.time`(コメント4) | `world_model/digital_updates.py:100,105,116`・`context_builder.py:600` | world-model | done | d25e497 |
| W1 | R1.3 | ~~dead state 除去~~→**live 化**(snapshot reducer。ユーザー決定) | `shopping.py`・`digital_updates.py`・`mqtt_router.py` | world-model | done | ac35b9e |
| W1 | R1.4 | timeline dead param/const 削除 | `timeline/generator.py:52,21` | world-model | done | 02bde4b |
| W2 | R2.1 | rename `_summarize_action`→`summarize_action`(+caller) | `brain_constants.py:79` | core-loop | done | 68115ab |
| W2 | R2.2 | rename local `_wake_up_fired`/`_vmap`/`_gpu` | `brain_mqtt.py:158`・`brain_cognitive.py:375,429` | core-loop | done | ba32766 |
| W2 | R2.3 | `split_for_speak` alias 撤去 | `boot_load_manager.py:29`・`event_automation.py:16` | core-loop/rules-automation | done | 2460594 |
| W2 | R2.4 | 型注釈 `=None` 引数を Optional 明示 | `boot_load_manager.py:124`・`task_scheduling/priority.py:24` | core-loop/world-model | done | 25ed450 |
| W2 | R2.5 | magic number 定数化(`[:67]`/`25`/時間定数) | `event_automation.py:318`・`low_power_mode.py:115`・cognitive/loops/mqtt | core-loop/rules-automation | done | 644219d |
| W2 | R2.6 | rename `generate_for_today`→`generate_week`+docstring | `timeline/generator.py:314` | world-model | done | 6dbd100 |
| W2 | R2.7 | 雑多整理(dup import/except/採番/hoist/`__init__`宣言) | `brain_mqtt.py:331`・`brain_loops.py:126,56-59`・`brain_cognitive.py:449-487`・`system_prompt.py:39-42`・`brain_chat_server.py`・`brain_startup.py:94` | core-loop | done | 0661720 |
| W2 | R2.8 | facade stdlib 直 import + docstring 修正 | `rules/biometric.py:227`・`timeline/generator.py:50` | rules-automation/world-model | done | 9461b53 |
| W2 | R2.9 | env.example に `AUTOMATION_ENGINE_ENABLED` 追記 | `env.example` | SUMMARY | done | 0dd5569 |
| W3 | R3.1 | `_ALLOWED_ACTIONS` 単一 SoT(dispatcher→sanitizer import) | `device_dispatcher.py:808`・`sanitizer.py:385` | llm-tools | done | 1dd119b |
| W3 | R3.2 | provider tool-call 整形共通化(cognitive↔chat) | `brain_cognitive.py:496-543`・`brain_chat_server.py:207-245` | core-loop | done | 8a5cf71 |
| W3 | R3.3 | PersonaRewriter `_rewrite_impl` 抽出 | `persona_rewriter.py:35-157` | llm-tools | done | 45c9c2a |
| W3 | R3.4 | EventWriter `_bulk_insert` helper+`tp` 定数 | `event_store/writer.py:333-460` | world-model | done | 149d742 |
| W3 | R3.5 | snapshot 構築 helper 統合 | `brain_cognitive.py:560-579,624-646` | core-loop | done | a7647b0 |
| W3 | R3.6 | threshold を RuleThresholds 単一ソース化 | `rule_engine.py:17`・`rules/config.py` | rules-automation | deferred | ユーザー決定 2026-05-25(R6.2 密結合・依存方向の設計判断) |
| W3 | R3.7 | `_summarize_action` dict 化 + `OPENCLAW_ENABLED` 重複統合 | `brain_constants.py:79-140`・`brain_mqtt.py:301`/`brain_cognitive.py:303` | core-loop | done | 85a9c70 |
| W3 | R3.8 | reducer setattr 化 + speak dict helper | `physical_updates.py:20-35`・`event_automation.py:256-518` | world-model/rules-automation | done | cf963eb |
| W4 | R4.1 | 共有 aiohttp session(queue/scene/speech) | `task_scheduling/queue_manager.py:31,60`・`scene_executor.py:41-58`・`voice/speech_generator.py:78` | world-model/rules-automation/voice | done | 83bf149 |
| W4 | R4.2 | ScheduleLearner public history API | `timeline/generator.py:82-99` | world-model | done | 2ed2bc3 |
| W4 | R4.3 | event_automation public method(`_run_batch` 経路) | `brain_cognitive.py:47` | core-loop | done | 16ca0fa |
| W4 | R4.4 | `add_task` no-op 明示/deprecate | `task_scheduling/queue_manager.py:17-23` | world-model | done | 4ce3091 |
| W5 | R5.1 | `_process_mqtt` 分割(~240L) | `brain_mqtt.py:78-317` | core-loop | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W5 | R5.2 | `cognitive_cycle` 分割(~470L) | `brain_cognitive.py:129-602` | core-loop | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W5 | R5.3 | `_get_physical_context` 分割(~257L) | `world_model/context_builder.py:52-309` | world-model | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W5 | R5.4 | `RuleEngine.evaluate` env+PC を mixin 抽出(~490L) | `rule_engine.py:193-684`→`rules/environment.py`・`rules/pc.py` | rules-automation | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W5 | R5.5 | `_update_biometric_state` table-driven(~165L) | `world_model/user_updates.py:121-285` | world-model | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W5 | R5.6 | (任意)`parse_mqtt`/`_dict_to_config` readability | `device_dispatcher.py:72-204`・`character_loader.py:273-382` | llm-tools | deferred | ユーザー決定 2026-05-25(高 blast-radius tail) |
| W6 | R6.1 | world_model mixin 直 import 化(facade 脱結合) | `world_model/*.py`(~7file) | world-model | deferred | ユーザー決定 2026-05-25(高 blast-radius tail・R3.6 前提) |
| W6 | R6.2 | rules mixin 直 import 化(`_rule_engine.X` 脱結合) | `rules/*.py`(8+新設2) | rules-automation | deferred | ユーザー決定 2026-05-25(高 blast-radius tail・R3.6 前提) |
| W7 | R7.1 | shared-key 認証実装+`_auth` 明確化+env+test | `backend/auth.py:30-31`・`main.py:132-159`・`env.example` | backend | done | 404c569 |
| W7 | R7.2 | ALTER TABLE migration bare except→narrow+logging+doc | `backend/main.py:27-78` | backend | done | cd47442 |
| W7 | R7.3 | chat.py raw `text()`→ORM(+narrow except) | `backend/routers/chat.py` | backend | done | 866432e(既に全 ORM・意図明記) |
| W8 | R8.1 | perception `_run_vlm_cycle` helper 抽出 | `perception/src/main.py:204-291` | perception | done | 6e85a70 |
| W8 | R8.2 | voice VoiSona hook を provider class へ | `voice/src/main.py:75-140` | voice | done | 7da0623 |

**残 pending: 0(非 deferred は全完了)。** done 33、deferred 9(R3.6 + W5 全 6 + W6 全 2)。baseline は reducer/auth test 追加で **1269 passed**。
メタ監査 follow-up(`BACKEND_API_KEY` 全 call-site 配線 + auth-wiring 回帰 test 追加)後の完走結果は **1283 passed, 2 skipped, 19 deselected**(`make test-quick`、65s、lint clean)。詳細は [`META_AUDIT_REPORT.md`](META_AUDIT_REPORT.md)。

> **本セッション完了**: 非 deferred 33 行すべて `done <sha>`。deferred 9 行(R3.6 threshold 一本化 /
> R5.1–5.6 god-function 分割 / R6.1–6.2 namespace 脱結合)は高 blast-radius な tail としてユーザー決定で
> 別セッションに繰延。lint clean / test-quick 1269 passed(baseline 1257 から reducer+auth test 12件増)。

> **deferred(ユーザー決定 2026-05-25)**: R3.6(threshold 一本化)・R5.1–5.6(god-function 分割)・
> R6.1/R6.2(namespace 脱結合)は高 blast-radius な tail のため別セッションで腰を据えて対応する。
> R3.6 は依存方向の設計判断を含み R6.2 と密結合。本セッションは残る中リスク行(R3.7/R3.8/W4/W7/W8)を消化する。 全行 `done <sha>` + lint+test-quick グリーン + row 毎 commit で本パス完了。
