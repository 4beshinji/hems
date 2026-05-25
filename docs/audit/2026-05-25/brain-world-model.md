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

未修正(コメント内 find-replace 事故。コードは .py のため本パスでは記録のみ):
- リファクタの `time.time()` → `_world_model.time.time()` 機械置換が**コメント/docstring 内の "time" まで誤置換**:
  - `digital_updates.py:100` `# Update screen _world_model.time tracking ...`
  - `digital_updates.py:105` `"""Track daily screen _world_model.time based on PC activity."""`
  - `digital_updates.py:116` `# Increment by elapsed _world_model.time since last update ...`
  - `context_builder.py:600` `# Screen _world_model.time`
  - 機能影響なし(コメントのみ)だが明確な誤り。後続コードパスで一括修正。

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | `task_type: list = None` → `list \| None = None` | task_scheduling/priority.py:24 | 型注釈と default の不一致 |
| P2 | `generate_for_today` → `generate_week`(または docstring 修正) | timeline/generator.py:314 | 名は "today" だが実際は today+6 日(1週間)を生成・POST |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | **namespace 結合 / 準循環 import**: 全 6 mixin が `from . import world_model as _world_model` し、`_world_model.time`(stdlib!)・`_world_model.logger`・閾値定数・再 export dataclass を facade 経由で参照。facade は ~30 シンボルを `# noqa: F401` で再 export し、末尾(L151-156)で mixin を import = 準循環 | world_model/*.py 全般(例 mqtt_router.py:14,24,39) | 共有シンボル(`time`/`logger`/`Event`/定数)は各 mixin で直接 import。dataclass は `data_classes` から直接。facade の re-export 依存を解消 |
| P1 | `_get_physical_context` が ~257 行の god-method(zone ループ + smart home + 在室 + VLM banner + trend)。`_get_digital_context` ~161行、`_get_user_context` ~135行も長大 | context_builder.py:52-309 / 310-471 / 472-607 | zone/home/weather/biometric 等の sub-builder へ分割 |
| P2 | ShoppingState が world_model 上 dead(DigitalSpace field + property accessor のみ、reducer 無し・context 未参照) | data_classes.py:708,749 / world_model.py:276-281 | reducer を足して live 化するか、world_model から除去し backend DB SoT を明示 |
| P2 | news 取込(digital 領域)と weather 取込(physical 領域)が `user_updates.py` に同居 — ファイル名と領域不一致 | user_updates.py:25,67 | `_update_news_state`→digital_updates、`_update_weather_state`→physical_updates へ移動 |
| P2 | TimelineGenerator が ScheduleLearner の private `_wake_history`/`_departure_history`/`_arrival_history` を `getattr` で直叩き | timeline/generator.py:82-84,98-99 | ScheduleLearner に public median/history API を設ける |
| P2 | dead param `auth_headers`(未保存・未使用)+ dead const `HEMS_HOME_LOCATION_KEYWORDS`(定義のみ、`_is_home_location` は別リテラル使用) | timeline/generator.py:52,21 | 削除 |
| P2 | `TaskQueueManager.process_queue` が毎サイクル新規 `aiohttp.ClientSession` を 2 回生成(共有 `Brain._session` 未利用) | task_scheduling/queue_manager.py:31,60 | 共有 session を DI |
| P2 | `should_dispatch` が `is_anyone_home()`(多源 presence)でなく生 camera `count > 0` を使用 → カメラ offline 時 PC/HR が在宅でもタスク dispatch されない | task_scheduling/decision.py:13 | `world_model.is_anyone_home()` を使用 |
| P2 | `TaskQueueManager.add_task` は log のみ(実 queue は backend `/tasks/queue` を poll)。呼ばれてはいる(tool_handlers_core.py:23)が機能は no-op | task_scheduling/queue_manager.py:17-23 | 意図を docstring 明記 or 廃止 |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | コメント内 find-replace 事故 4 件(上記 doc 乖離欄に詳細) | digital_updates.py:100,105,116 / context_builder.py:600 | "time" に戻す |
| P2 | `_update_biometric_state` が ~165 行の反復 metric チェーン(各 metric で prev/set/last_update/bridge_connected/record_history/threshold が同型反復) | user_updates.py:121-285 | metric→handler のテーブル駆動化 |
| P2 | EventWriter の INSERT が events/decisions/world_events で IS_POSTGRES 分岐をほぼ同型に 3 重コピー(~130行)+ `tp` prefix を 6 メソッドで反復 | event_store/writer.py:333-460 ほか | `_bulk_insert(conn, table, cols, rows, jsonb_cols)` helper 抽出 + `tp` を定数化 |
| P2 | `_update_sensor` の channel→env field if/elif(8 分岐)は名前一致のため `setattr` + 精度マップ化可能。`prev = getattr(env, ch, None) if hasattr(env, ch) else None` の `if hasattr` は冗長(getattr default で足る) | physical_updates.py:20-35,18 | setattr 化 / 冗長 guard 除去 |
| P2 | `float(prev_bpm) if prev_bpm else None` は prev=0 を None 扱い(初回 threshold 判定が "crossing" 扱いに) | user_updates.py:152,162,209 ほか | `prev_bpm if prev_bpm is not None else None` |
| P2 | local import 散在(`import time` / `import aiohttp` / `from datetime import datetime` / `import statistics`) | priority.py:30 / queue_manager.py:29 / digital_updates.py:107,319 / generator.py:77 | module 先頭へ集約 |
| P2 | TimelineGenerator docstring "Stateless per-call"(L50)だが instance state(world_model/session/travel_matrix)を保持 — 矛盾 | timeline/generator.py:50 | docstring 修正 |

## 後続リファクタ推奨(優先度順サマリ)

- **P1**:
  1. world_model mixin の **namespace 結合解消**(`_world_model.time`/`logger`/定数/dataclass の facade 経由参照を直接 import へ)。準循環 import を断ち、抽出を正規化。最重要アーキテクチャ負債。
  2. `context_builder` の 3 大ビルダー(特に `_get_physical_context` 257行)を sub-builder へ分割。
  3. コメント内 `_world_model.time` find-replace 事故 4 件を "time" に戻す。
- **P2**:
  - ShoppingState の live 化 or 除去、news/weather reducer の領域別ファイルへの再配置。
  - `_update_biometric_state` / EventWriter INSERT のテーブル駆動化・helper 抽出で重複削減。
  - TimelineGenerator の dead param/const 削除 + ScheduleLearner private 越境の public API 化。
  - TaskQueueManager の共有 session 利用、`should_dispatch` の `is_anyone_home()` 統一(presence 整合)。
- **P0**: 挙動ブロッカー無し。ただし `should_dispatch` の presence 不整合は「カメラ無し構成でタスク dispatch されない」実害があり P2 上位。
