# 監査: perception — 2026-05-25

## スコープ
- 対象 path(`services/perception/src/`):
  `main.py`(524)・`config.py`(46)・`camera_manager.py`(236)・`detector.py`(94)・
  `activity_tracker.py`(205)・`vlm_analyzer.py`(294)・`vlm_scheduler.py`(208)・`mqtt_publisher.py`(49)
  — 計 ~1,656 LOC
- entry point: `main.py`(FastAPI + `_processing_loop` / `_vlm_processing_loop` + lifespan)
- 参照 canonical doc: `services/perception/CLAUDE.md`

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality (file:line) | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | perception/CLAUDE.md「Brain tools: `get_perception_status`, `describe_scene`」(2 件) | 実際は 7 ツール: + `list_scene_objects`/`get_scene_timeline`/`list_cameras`/`get_vlm_status`/`get_activity_history`(unit 4 schema dump + tool_handlers_perception.py で確認) | services/perception/CLAUDE.md | ✅ 7 件に修正 |

検証 OK(乖離なし):
- publish topic: `office/{zone}/camera/{cam_id}/status`(main.py:135)・`office/{zone}/activity/{cam_id}`(main.py:152)・`hems/perception/vlm/{zone}`(263)・`hems/perception/vlm/status`(304, retain)・`hems/perception/vlm/model_swap`(221,280)— canonical と完全一致。
- model_swap は heavy tier load/unload で publish(strategy B 用)— canonical の記述通り。
- privacy(RAM-only / person class only)・camera 種別(mcp/stream)も実装と整合。

## 命名所見(refactor-ready)
- 特筆なし。クラス名(VLMAnalyzer/VLMScheduler/Detector/ActivityTracker)・メソッド名は明快。

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | `main.py` がモジュールレベル関数 + グローバル状態(`vlm_analyzer`/`mqtt_pub` 等)で構成。loop/endpoint/lifespan が 1 ファイル 524 行に同居 | main.py | クラス化 or loop/endpoint 分離で見通し改善(優先度低・現状可読) |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | `_run_vlm_cycle`(~87 行)に tier 選択・analyze・publish・model_swap が集約 | main.py:204-291 | 補助関数へ小分け(優先度低) |

## 後続リファクタ推奨(優先度順サマリ)
- **P2**: main.py のグローバル状態 + 524 行を軽く整理(クラス化 / loop 分離)。`_run_vlm_cycle` の分割。
- **P0/P1**: 無し。モジュール分割(detector/activity_tracker/vlm_analyzer/vlm_scheduler/camera_manager)は良好で、各クラスの責務が明確。find-replace 事故・dead code・命名問題は検出されず。**最もクリーンなユニットの一つ**。
