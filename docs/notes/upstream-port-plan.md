# Upstream port → HEMS — progress (SoT for multi-session work)

> **Historical notice (2026-05-24)**: この文書は upstream port 作業時点の進捗記録。現行構成の SoT ではない。
> `localcraw` などの旧名称は現在の OpenClaw PC bridge legacy alias として扱う。

兄弟リポ `Office_as_AI_ToyBox`(SOMS upstream)/ `business-ops`(同系フォーク)の大規模リファクタを
hems に取り込む多セッション作業。ブランチ `refactor/upstream-port`(`hardening/p0-impl` から分岐)。
詳細計画は `~/.claude/plans/spicy-tumbling-river.md`。`go next`/`続行` 時はまず本ファイルの進捗を読む。

採用範囲: **consent-gate(#9)を除く全候補 + ollama→llama.cpp 全面移行**(複数インスタンス・VLM も移行・ollama 完全除去)。

## 進捗チェックリスト

- [x] **Wave 1** — 独立・低リスク brain ローカル(commit 済)
  - [x] 1A #3 sensor validation(`world_model/sensor_validation.py` + update_from_mqtt 2 経路 + event-store 経路)
  - [x] 1B #1 NORMAL polling gate(`low_power_mode.py` NORMAL_CYCLE/HEARTBEAT_INTERVAL + main.py run ループ heartbeat gate)
  - [x] 1C #6 loguru cleanup(low_power_mode / device_registry / character_loader / world_model)
- [x] **Wave 2** — world_model / llm_client(commit 済)
  - [x] 2A #2 freshness/degraded-op gate(`is_blind`/`ENV_STALE_SEC`/`ZONE_BLIND_SEC`/`MAX_FUSION_AGE_SEC`/blind guard/stale 表示/system_prompt 鮮度警告)
  - [x] 2B #4 LLM cost/token metering(`LLMResponse.usage`→event_store columns + writer + aggregator rollup)
- [~] **Wave 3** — ollama→llama.cpp 全面移行 → **見送り / 当面 ollama 継続**(2026-05-22 決定)
  - 理由: 実機は **RX 6900 XT / gfx1030 / 16GB VRAM**。llama.cpp は常駐ロードのため chat/VLM/embeddings の
    3 インスタンス + perception(YOLO)+ STT を 16GB に同居させると OOM 必至。ollama のオンデマンド
    load/unload(swap)が単一 16GB GPU + 複数モデルに最適で、hems 既存の `vlm_model_swap_active`
    (VLM heavy-swap 中は brain rule-based)設計とも整合する。
  - #8 enable_thinking:False は **不要**(ollama+gemma 経路では gemma が `<think>` を出さず、hems は既に
    ollama `think=False` デフォルト。boot_load のみ think=True)。
  - chat モデルは現行 `gemma4:e4b-it-q8_0` 維持。ROCm/Dockerfile/compose の llama.cpp 化はすべて N/A。
  - 将来 24GB+ GPU か llama-swap 導入時に再検討(plan の Wave 3 / `~/.claude/plans/spicy-tumbling-river.md` 参照)。
- [x] **Wave 4** — #7 efficacy loop(commit 済)
  - efficacy.py(metric 導出 + comfort-band verdict)、`intervention_efficacy` スキーマ(SQLite+PG, region_id 無し)、
    writer(created/completed buffer + flush, fetch_pending/compute_post_value/record_verdict は dual-backend)、
    tool_executor の baseline capture、main.py の完了フック(`hems/task/completed/{id}`)+ `_efficacy_eval_loop` +
    cognitive cycle への verdict 注入。
  - **dashboard endpoint(/sensors/intervention-efficacy)は未実装(deferred)**: hems では event_store は brain 側 DB で
    backend と分離。表示面はクロスサービス配線(brain chat server endpoint or backend が brain DB を読む)が要るため
    別途。測定ループ + LLM 注入の機能コアは完了。
  - dual-backend 適応: SOMS は PG 専用(now()/interval/`data->>`/regex)。hems は SQLite 既定なので
    fetch_pending は Python 側で window 経過判定、compute_post_value は `json_extract` + `typeof` で SQLite 対応。
- [x] **Wave 5** — #5 main.py mixin 分割(commit 済)
  - main.py 1961→430 行。`brain_constants.py`(定数 + `_summarize_action`)+ `MqttSyncMixin`(brain_mqtt)+
    `CognitiveCycleMixin`(brain_cognitive)+ `ChatServerMixin`(brain_chat_server)+ `BackgroundLoopsMixin`(brain_loops)。
    `class Brain(...4 mixins)` は `__init__`/`run`/`_TASK_ALERT_KEYWORDS` のみ保持。entrypoint(`__main__`)維持。
  - **挙動不変**を独立検証: ruff(F821 undefined-name)全 6 ファイル clean、28 メソッドが各 1 回だけ存在、
    cognitive_cycle/_process_mqtt の body が byte 一致(差分は移動したセクション区切りコメント 1 つのみ)、
    full suite parity(1198 passed)。`_summarize_action` は main へ re-export(test_vlm の importlib 経路維持)。
  - sonnet-implementer に機械抽出を委譲 → diff/ruff/suite を親で再検証(memory ルール)。
- [ ] **Wave 6** — #10 OAuth broker for gas-bridge(任意・最後)

## 設計メモ / hems 固有の逸脱

- **1A event-store 経路**: hems は SOMS と違い world-model 更新が `world_model.update_from_mqtt` に分離 → 検証を
  (1) update_from_mqtt の ANALOG 分岐、(2) zigbee 直経路 `_update_zigbee_state`、(3) main.py `_process_mqtt` の
  event-store record_sensor 経路、の 3 箇所に挿入。event-store 経路は SOMS が全チャネル非数値 drop するのに対し、
  hems は **ANALOG チャネルのみ検証**(door/presence 等の state telemetry を失わないため)。
- **1A test**: event-store 経路(main.py)の統合テストは Brain インスタンスが重く、mixin 分割前なので **Wave 5 に延期**。
  現状は検証関数 + world-model 2 経路 + レジストリ網羅をカバー(`tests/test_sensor_validation.py`)。
- **1B**: hems は pydantic config.py を持たず env-var モジュール定数パターン → `low_power_mode.py` に定数追加。
  NORMAL_CYCLE_INTERVAL 30→180。イベントは `_cycle_triggered` で即時処理されるので poll floor 延長は idle 専用。
  main.py の dead constant `CYCLE_INTERVAL=30`/`MIN_CYCLE_INTERVAL=25` は未使用のまま残置(参照ゼロ)。
- **2A**: hems は freshness を `EnvironmentState.last_update` + `channel_last_seen` で管理(SOMS は ZoneState.last_update +
  environment.timestamps)。`is_blind` は `last_update==0` も blind 扱い。**blind guard の suppress 対象**は SOMS の 2 ツール
  (create_task/send_device_command)を hems の広いツール面に適応し `BLIND_SUPPRESSED_TOOLS`(create_task + 全 device 制御
  + scene + zigbee_permit_join)に拡張。control_browser/run_pc_command 等 PC/digital 系は鮮度非依存なので非対象。
  SOMS の **stale-alert-text suppression(高温/CO2 アラート抑止)は未移植**(stale note + blind guard で縮退運転は達成済、deferred)。
- **2B**: `LLMResponse.usage` は provider 差(openai usage / ollama prompt_eval_count+eval_count / anthropic input/output_tokens)を
  `{prompt_tokens, completion_tokens}` に正規化。gpu_util は localcraw の PC GPU(`pc_state.gpu.usage_percent`、600s 鮮度)から
  best-effort サンプル。**E5(実 power probe nvidia/rocm-smi)は deferred** → `gpu_power_w` は nullable のまま。
  ※ ollama usage 捕捉は Wave 3 の llama.cpp 移行で `_chat_ollama` ごと撤去予定(暫定)。

## 既知の無関係 failure(本作業のスコープ外)

- `tests/test_backend_mobile_router.py::TestVoiceCapsule::test_admin_play_log_list` — **pre-existing**。
  play-log の `since_days=30` ウィンドウに対しフィクスチャの `played_at=2026-04-20` が今日(2026-05-22)から
  32 日前で範囲外 → 空リストで落ちる日付相対バグ。全 Wave 1 変更を stash しても同様に落ちる(確認済)。backend 側課題。
