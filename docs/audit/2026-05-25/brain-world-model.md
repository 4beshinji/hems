# 監査: brain-world-model — 2026-05-25

## スコープ
- 対象 path(すべて `services/brain/src/`):
  - `world_model/`: `world_model.py`(357, facade)・`mqtt_router.py`(125)・`physical_updates.py`(381)・
    `digital_updates.py`(496)・`user_updates.py`(331)・`presence.py`(102)・`context_builder.py`(607)・
    `data_classes.py`(~760, 102 クラス)・`sensor_fusion.py`(277)・`sensor_validation.py`(87)
  - `event_store/`: `writer.py`(470)・`aggregator.py`(263)・`database.py`(278)・`models.py`(63)
  - `timeline/`: `generator.py`(323)・`edf_scheduler.py`(177)・`free_window.py`(64)・`models.py`(52)・`travel_config.py`(52)
  - `task_scheduling/`: `queue_manager.py`(65)・`priority.py`(35)・`decision.py`(18)
  - 計 ~5,457 LOC
- entry point: `WorldModel.update_from_mqtt`(`mqtt_router.py`)/ `get_llm_context`(`context_builder.py`)
- 参照 canonical doc: `services/brain/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md` §4.3 / §4.4 / §5

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §4.3 が `update_from_mqtt` と `_update_*` を `world_model.py` 内のように記載 | routing は `mqtt_router.py`(`MqttRouterMixin`)、reducer は `{physical,digital,user}_updates.py` mixin に分割。facade が合成 | IMPLEMENTATION_MAP §4.3 intro | ✅ 注記追加 |
| 2 | §4.4「`hems/pc/processes/top` は未統合・reducer 未実装の可能性」 | `digital_updates.py:74-83` で `pc.top_processes` に populate 済、かつ `context_builder.py:322-332` / `rule_engine.py:590` / `tool_handlers_pc.py:30,105` / `dashboard_client.py:194` で消費。完全に統合済 | IMPLEMENTATION_MAP §4.4 | ✅ 行削除 |
| 3 | §4.6 Verification が `world_model.py` を grep | routing は `mqtt_router.py` へ移動 | IMPLEMENTATION_MAP §4.6 | ✅ grep 先変更 |
| 4 | §5 ShoppingState「データソース: hems/shopping/* + backend DB」 | world_model 上は **reducer 皆無**で default のまま。`mqtt_router` に `hems/shopping` route 無し。shopping は `brain_mqtt._process_mqtt`→ShoppingClassifier + event_store 経由。`get_llm_context` も未参照(context_builder に shopping 0 件) | IMPLEMENTATION_MAP §5 | ✅ 注記修正 |
| 5 | §5.1 Verification が `world_model.py` の `_update_` を grep | `_update_*` は `{physical,digital,user}_updates.py` へ移動 | IMPLEMENTATION_MAP §5.1 | ✅ grep 先変更 |

~~未修正(コメント内 find-replace 事故。コードは .py のため本パスでは記録のみ)~~ → **実装済み**:
- ~~リファクタの `time.time()` → `_world_model.time.time()` 機械置換がコメント/docstring 内の "time" まで誤置換~~ → 修正済み:
  - `digital_updates.py:100` `# Update screen time tracking ...`
  - `digital_updates.py:105` `"""Track daily screen time based on PC activity."""`
  - `digital_updates.py:116` `# Increment by elapsed time since last update ...`
  - `context_builder.py:600` `# Screen time`

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | ~~`task_type: list = None` → `list \| None = None`~~ → **実装済み** | task_scheduling/priority.py:24 | `task_type: list \| None = None` に修正済み |
| P2 | ~~`generate_for_today` → `generate_week`(または docstring 修正)~~ → **実装済み** | timeline/generator.py:271,311 | `generate_for_today` を `generate_for_date`/`generate_week` に分割 |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~**namespace 結合 / 準循環 import**~~ → **実装済み**。world_model 各 mixin の `_world_model.time`/`logger`/定数 facade 経由参照を解消。facade の re-export 依存を断ち、準循環 import を解消 | world_model/*.py | — |
| P1 | ~~`_get_physical_context` が ~257 行の god-method~~ → **実装済み**。`_get_physical_context`/`_get_digital_context`/`_get_user_context` を zone/home/weather/biometric 等の sub-builder メソッドへ分割 | context_builder.py | — |
| P2 | ShoppingState が world_model 上 dead(DigitalSpace field + property accessor のみ、reducer 無し・context 未参照) | data_classes.py:708,749 / world_model.py:276-281 | reducer を足して live 化するか、world_model から除去し backend DB SoT を明示 |
| P2 | news 取込(digital 領域)と weather 取込(physical 領域)が `user_updates.py` に同居 — ファイル名と領域不一致 | user_updates.py:25,67 | `_update_news_state`→digital_updates、`_update_weather_state`→physical_updates へ移動 |
| P2 | ~~TimelineGenerator が ScheduleLearner の private history を `getattr` で直叩き~~ → **実装済み**。`timeline/generator.py:77-79,93-94` で `median_hour()`/`history_count()` public API を使用 | timeline/generator.py:77-79,93-94 | — |
| P2 | ~~dead param `auth_headers` + dead const `HEMS_HOME_LOCATION_KEYWORDS`~~ → **実装済み**。`timeline/generator.py` から削除; 必要時は `backend_auth_headers()` を使用 | timeline/generator.py | — |
| P2 | ~~`TaskQueueManager.process_queue` が毎サイクル新規 `aiohttp.ClientSession` を 2 回生成~~ → **実装済み**。共有 session を DI して使用 | task_scheduling/queue_manager.py:31,60 | — |
| P2 | ~~`should_dispatch` が生 camera `count > 0` を使用~~ → **実装済み**。`task_scheduling/decision.py:14` で `world_model.is_anyone_home()` を使用 | task_scheduling/decision.py:14 | — |
| P2 | ~~`TaskQueueManager.add_task` は log のみ~~ → **実装済み**。docstring で「log のみ(backend `/tasks/queue` を poll)」と明示 | task_scheduling/queue_manager.py:20-24 | — |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~コメント内 find-replace 事故 4 件~~ → **実装済み**(上記 doc 乖離欄参照) | digital_updates.py:100,105,116 / context_builder.py:600 | — |
| P2 | ~~`_update_biometric_state` が ~165 行の反復 metric チェーン~~ → **実装済み**。`user_updates.py:288` の `_BIOMETRIC_HANDLERS` テーブルで個別 helper にディスパッチ | user_updates.py:288,305,324 | — |
| P2 | EventWriter の INSERT が events/decisions/world_events で IS_POSTGRES 分岐をほぼ同型に 3 重コピー(~130行)+ `tp` prefix を 6 メソッドで反復 | event_store/writer.py:333-460 ほか | `_bulk_insert(conn, table, cols, rows, jsonb_cols)` helper 抽出 + `tp` を定数化 |
| P2 | ~~`_update_sensor` の channel→env field if/elif(8 分岐)~~ → **実装済み**。`physical_updates.py:21-22` の `_SENSOR_FIELDS`/`_CHANNEL_PRECISION` マップ + `setattr` を使用 | physical_updates.py:21-22,39-40 | — |
| P2 | ~~`float(prev_bpm) if prev_bpm else None`~~ → **実装済み**。`user_updates.py:141` で `float(prev_bpm) if prev_bpm is not None else None` に修正 | user_updates.py:141 | — |
| P2 | local import 散在(`import time` / `import aiohttp` / `from datetime import datetime` / `import statistics`) | priority.py:30 / queue_manager.py:29 / digital_updates.py:107,319 / generator.py:77 | module 先頭へ集約 |
| P2 | ~~TimelineGenerator docstring "Stateless per-call"~~ → **実装済み**。docstring を instance state 保持と一致するよう修正 | timeline/generator.py:50 | — |

## 後続リファクタ推奨(優先度順サマリ)

- **P1**:
  1. ~~world_model mixin の **namespace 結合解消**~~ → **実装済み**。
  2. ~~`context_builder` の 3 大ビルダーを sub-builder へ分割~~ → **実装済み**。
  3. ~~コメント内 `_world_model.time` find-replace 事故 4 件を "time" に戻す~~ → **実装済み**。
- **P2**:
  - ShoppingState の live 化 or 除去、news/weather reducer の領域別ファイルへの再配置。
  - ~~`_update_biometric_state` のテーブル駆動化~~ → **実装済み**(`user_updates.py:288` `_BIOMETRIC_HANDLERS`); EventWriter INSERT の helper 抽出は未対応。
  - ~~TimelineGenerator の dead param/const 削除 + ScheduleLearner private 越境の public API 化~~ → **実装済み**。
  - ~~TaskQueueManager の共有 session 利用、`should_dispatch` の `is_anyone_home()` 統一~~ → **実装済み**。
- **P0**: 挙動ブロッカー無し。`should_dispatch` の presence 不整合は解消済み。
