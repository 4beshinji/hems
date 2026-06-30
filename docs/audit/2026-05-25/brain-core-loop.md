# 監査: brain-core-loop — 2026-05-25

## スコープ
- 対象 path(すべて `services/brain/src/`):
  `main.py`(143)・`brain_startup.py`(242)・`brain_runtime.py`(77)・
  `brain_constants.py`(140)・`brain_mqtt.py`(335)・`brain_cognitive.py`(696)・
  `brain_chat_server.py`(287)・`brain_loops.py`(204)・
  `sanitizer.py`(500)・`system_prompt.py`(529)・
  `low_power_mode.py`(259, PowerModeManager)・`boot_load_manager.py`(537, BootLoadManager)
  — 計 ~3,949 LOC
- entry point: `main.py` `Brain.run()` → `_connect_mqtt_client` → `_start_event_store` →
  `_wire_runtime_components` → `_finish_bootstrap` → `_run_cognitive_loop`(`brain_runtime.py`)
- 参照 canonical doc: `services/brain/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md` §2

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | 「Subsystems wired in `main.py`」/「main.py の `Brain.__init__` および async startup で初期化」 | always-on コアは `main.py:55-107`(`__init__`)、async 配線は `brain_startup.py:79-162`(`_wire_runtime_components`)に 2 分割 | IMPLEMENTATION_MAP §2 intro + §2.1 / brain/CLAUDE.md L17 | ✅ 修正済 |
| 2 | TimelineGenerator 起動条件「GAS_ENABLED 時」 | `brain_startup.py:157` で **無条件 instantiate**(GAS gate 無し。L177 の GAS_ENABLED はログ専用) | IMPLEMENTATION_MAP §2 表 / brain/CLAUDE.md L23 | ✅ 修正済 |
| 3 | EventAutomation 起動条件「NEWS / GAS 有効時」 | `brain_startup.py:149` で **無条件 instantiate**。コード自身 `_log_integrations` L168 が "event automation still active" とログ | IMPLEMENTATION_MAP §2 表 / brain/CLAUDE.md L24 | ✅ 修正済 |
| 4 | PersonaRewriter 起動条件「`PERSONA_REWRITE_ENABLED=true`」 | `brain_startup.py:84` で **無条件 instantiate**。env は `persona_rewriter.py:36,106` で rewrite 動作のみ gate | IMPLEMENTATION_MAP §2 表 / brain/CLAUDE.md L29 | ✅ 修正済 |
| 5 | §2.1 Verification が `main.py` のみ grep | startup 配線分は `brain_startup.py` に在り main.py grep では出ない | IMPLEMENTATION_MAP §2.1 | ✅ 修正済(両ファイル grep に) |

未修正(コード側 stale コメント。コード無改変方針のため finding 留め):
- `low_power_mode.py:115` `return 25  # matches MIN_CYCLE_INTERVAL in main.py` — 実体は `brain_constants.py:49`。リファクタで移動したが comment が main.py のまま。

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | `_summarize_action` → `summarize_action` | brain_constants.py:79 | 先頭 `_` は module-private を示唆するが cognitive / chat / runtime の 3 モジュールから import される共有関数 |
| P2 | `_wake_up_fired` → `wake_up_fired` | brain_mqtt.py:158 | ローカル変数に privacy 用 `_` は誤誘導 |
| P2 | `_vmap` / `_gpu` → `vmap` / `gpu` | brain_cognitive.py:375,429 | 同上(関数ローカルの leading `_`) |
| P2 | `import json as _json` 削除 | brain_mqtt.py:331 | module 先頭 L2 で `json` 既 import。ローカル再 import + alias 不要 |
| P2 | `split_for_speak as _split_for_speak` → alias 撤去 | boot_load_manager.py:29 | public 関数を private 名へ alias する不整合 |
| P2 | `now: float = None` → `now: float \| None = None` | boot_load_manager.py:124 | 型注釈不正(PowerModeManager は正しく `\| None`) |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~`_process_mqtt` が ~240 行の god-function~~ → **実装済み** | brain_mqtt.py:80-105 | `_process_mqtt` を thin orchestrator 化し、S0–S9b の責務を個別メソッド(`_enrich_payload`、`_trigger_motion_event`、`_feed_shopping_classifier`、`_trigger_timeline_on_event`、`_mark_intervention`、`_feed_schedule_learner_*`、`_detect_wake_up`、`_record_to_event_store`、`_collect_feedback`、`_update_device_registry`、`_maybe_trigger_cycle`)へ分割 |
| P1 | ~~`cognitive_cycle` が ~470 行の god-method~~ → **実装済み** | brain_cognitive.py:163-198 | `cognitive_cycle` を 5 フェーズ(`_run_preflight`、`_run_fallback_guards`、`_build_cycle_context`、`_run_react_loop`、`_postprocess_cycle`)へ分割 |
| P1 | ~~dead code: `_build_character_section`~~ → **実装済み** | system_prompt.py | 関数削除済み。`build_system_message`/`build_chat_system_message` は character 注入を Stage 2(PersonaRewriter)へ移譲済 |
| P1 | ~~provider 別 tool_call block + tool message 整形の重複~~ → **実装済み** | brain_utils.py:84-121 | `format_tool_call_blocks` / `format_tool_result_msg` を `brain_utils.py` へ共有抽出。`brain_cognitive.py` と `brain_chat_server.py` が双方 import |
| P2 | `event_classifier` が startup でのみ生成され `Brain.__init__` に事前宣言が無い(兄弟の shopping_classifier / _rule_promoter は None 宣言あり) | brain_startup.py:94 vs main.py:84-98 | `__init__` に `self.event_classifier = None` を追加し宣言を統一 |
| P2 | `_bridge_state_cache` / `_bridge_disconnect_history` / `_bridge_outage_alert_sent` を `hasattr` 遅延初期化 | brain_loops.py:56-59 | `Brain.__init__` で宣言し discoverability 向上 |
| P2 | `_run_batch` が他オブジェクトの private `event_automation._execute_action` を直叩き | brain_cognitive.py:47 | EventAutomation に public メソッドを設けて越境 private 呼出を解消 |
| P2 | SOMS legacy 残骸(`allowed_devices=["light_01","pump_01","window_01"]` / `swarm_hub` prefix / `set_temperature`/`run_pump`/`pump_duration` safety_limits)が deprecated `send_device_command` に紐づく | sanitizer.py:82-86,238,251-271 | `send_device_command` 廃止時に一括除去 |
| P2 | sanitizer 読み取り許可リストに canonical/registry 未掲載のツール名(`list_note_tags`/`get_recent_knowledge_changes`/`get_biometric_trend`/`get_sleep_history`/`list_cameras`/`get_vlm_status`/`get_activity_history`/`gas_query_free_slots`/`gas_query_sheet`) | sanitizer.py:124-177 | **unit 4(tools)で要 cross-check** — 未文書化ツールか stale allowlist かを確定 |
| P2 | `AUTOMATION_ENGINE_ENABLED`(default true)が env.example / §9 未記載 | brain_startup.py:229 | §9 + env.example へ追記(SUMMARY/env unit で処理) |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | `if inferred is not None` が常時真の dead-guard(`inferred` は L118 で 0 初期化、None になる経路無し)。結果 schedule_learner 有効時は **全 MQTT msg** で reconcile_presence + update_occupancy が走る | brain_mqtt.py:143(init L118) | `inferred = None` 初期化に変える(presence 関連 msg のみ発火)か guard を撤去して意図を明示 |
| P2 | ~~guard 番号が "Guard 0 / 1 / 2 / 4"(Guard 3 欠番)~~ → **実装済み** | brain_cognitive.py:541-597 | 連番 0–3 に振り直し済 |
| P2 | ~~system_prompt「## 行動原則」が 1,2,4,5(項目 3 欠番)~~ → **実装済み** | system_prompt.py:37-42 | 連番 1–4 に修正済 |
| P2 | ~~`_summarize_action` が ~60 行 if/elif チェーン~~ → **実装済み** | brain_constants.py:117-186 | `_ACTION_SUMMARIZERS` dict ディスパッチ表化済。tapo/knowledge/device-registry tool も対応 |
| P2 | 連続する `if OPENCLAW_ENABLED:` ブロック重複 | brain_mqtt.py:301-304 / brain_cognitive.py:303-310 | 1 ブロックに統合 |
| P2 | `except (json.JSONDecodeError, Exception)` 冗長(後者が前者を内包) | brain_loops.py:126 | `except Exception` のみに |
| P2 | ~~magic number 散在~~ → **実装済み** | brain_constants.py:85-91 | `RECENT_EVENT_WINDOW_SEC`、`RECENT_ACTION_WINDOW_SEC`、`GPU_FRESHNESS_SEC`、`ACTION_HISTORY_RETENTION_SEC`、`SECONDS_PER_DAY` 等として定数化済 |
| P2 | 各 aiohttp ハンドラで `from aiohttp import web as aio_web` をローカル import(7 箇所) | brain_chat_server.py:25,31,70,90,117,137 | module 先頭へ集約(brain_startup.py は既に module-level) |
| P2 | hardcoded `25` が `MIN_CYCLE_INTERVAL` 重複 + stale コメント | low_power_mode.py:115 | `brain_constants.MIN_CYCLE_INTERVAL` を import |
| P2 | `cognitive_cycle` 内の `_last_cycle_summary` 構築(trigger/cycle_tool_calls)が `_record_rule_cycle_summary` と重複ロジック | brain_cognitive.py:560-579 vs 624-646 | snapshot 構築を 1 helper に統合 |

## 後続リファクタ推奨(優先度順サマリ)

- **P1**(最優先・高 ROI): **2026-06-30 時点で全項目実装済み**。
  1. ~~`cognitive_cycle` と `_process_mqtt` の god-function 分割~~ → `brain_cognitive.py`/`brain_mqtt.py` で完了。
  2. ~~dead code `_build_character_section` 削除~~ → 削除済。
  3. ~~provider 別 tool-call 整形の重複を共有 util へ抽出~~ → `brain_utils.py` `format_tool_call_blocks` / `format_tool_result_msg` で完了。
- **P2**(命名・整理): **以下は未実装**。ただし挙動ブロッカーではない。
  - `event_classifier` の `Brain.__init__` 事前宣言統一。
  - `_bridge_state_cache` / `_bridge_disconnect_history` / `_bridge_outage_alert_sent` の `hasattr` 遅延初期化を `__init__` 宣言化。
  - `_run_batch` が `event_automation._execute_action` private メソッドを直叩き → public メソッド化。
  - sanitizer の SOMS legacy(`allowed_devices`/`swarm_hub`/`set_temperature`/`run_pump`/`pump_duration`)は `send_device_command` 廃止時に一括除去。
  - sanitizer 読み取り許可リストの canonical/registry 未掲載ツール cross-check。
  - `if inferred is not None` dead-guard の是正(`inferred = None` 初期化 or guard 撤去)。
  - 連続する `if OPENCLAW_ENABLED:` ブロックの統合。
  - `brain_loops.py:126` `except (json.JSONDecodeError, Exception)` の簡潔化。
  - `brain_chat_server.py` aiohttp ハンドラのローカル `from aiohttp import web as aio_web` を module 先頭へ集約。
  - `low_power_mode.py:115` の hardcoded `25` を `brain_constants.MIN_CYCLE_INTERVAL` に置換 + stale コメント修正。
  - `cognitive_cycle` 内 `_last_cycle_summary` 構築の `_record_rule_cycle_summary` との重複統合。
  - ~~magic number 定数化~~ → **実装済み**。
  - ~~guard 番号 / プロンプト番号の連番修正~~ → **実装済み**。
  - ~~`_summarize_action` dict ディスパッチ表化~~ → **実装済み**。
  - ~~`AUTOMATION_ENGINE_ENABLED` を env.example/§9 へ追記~~ → **実装済み**。
- **P0**: 本 unit に挙動ブロッカーは無し(監査のみパス)。
