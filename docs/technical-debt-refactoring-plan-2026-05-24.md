# Technical Debt Refactoring Plan — 2026-05-24

Source: `docs/technical-debt-audit-2026-05-24.md`

## Goal

Brain 分割後の互換性を先に固定し、その後にレビュー可能な単位で残タスクを片付ける。現時点の主リスクは「巨大モジュール」ではなく、schema / dispatch / handler / chat allowlist / URL alias / reducer が分割前と同じ契約を保っていることを証明しきれていない点である。

## Execution Rules

- 追加リファクタより先に回帰テストを入れる。
- 1 PR / 1 commit は、できるだけ同一責務・同一検証コマンドに閉じる。
- `localcraw` は機械削除しない。`OPENCLAW_BRIDGE_URL` を canonical、`LOCALCRAW_BRIDGE_URL` を legacy alias として扱う。
- 広域 pytest は環境依存の hang 履歴があるため、証跡として使う場合は実行環境、timeout、完全な command、結果を記録する。
  release 判定の canonical gate は通常環境での `make lint` と full non-integration pytest とする。
- 既存の未追跡 Brain 分割ファイルは、検証単位ごとに追跡対象へ入れる。

## Phase 1 — Wiring Safety Net

Status: complete

1. `get_chat_tools(...)` 回帰
   - `get_chat_tools(...)` が存在しない tool 名を allowlist に持たないことを検証する。
   - chat に mutating/action tool が混入しないことを検証する。
   - 対象: `services/brain/src/tool_registry.py`, `tests/test_tool_registry.py`
   - 実装済み: `CHAT_ALLOWED_TOOL_NAMES`, `tests/test_tool_registry.py`

2. `ToolExecutor.execute()` handler 到達
   - `TOOL_HANDLERS` の handler 名が `ToolExecutor` 実体に存在することを検証する。
   - 副作用の小さい read-only handler は、必要に応じて `execute()` 経由で smoke する。
   - 対象: `services/brain/src/tool_dispatch.py`, `services/brain/src/tool_executor.py`, `tests/test_tool_executor_*.py`
   - 実装済み: `tests/test_tool_wiring.py`

3. OpenClaw URL alias
   - `OPENCLAW_BRIDGE_URL` が `LOCALCRAW_BRIDGE_URL` より優先されることを検証する。
   - `OPENCLAW_BRIDGE_URL` 未設定時に `LOCALCRAW_BRIDGE_URL` が fallback されることを検証する。
   - `brain_constants.py` と `tool_executor.py` の両方を対象にする。
   - 実装済み: `tests/test_tool_wiring.py`

Verification:

```bash
PYTHONPATH=services/brain/src:services/backend .venv/bin/python -m pytest \
  tests/test_tool_registry.py \
  tests/test_tool_wiring.py \
  tests/test_tool_executor_pc.py \
  tests/test_tool_executor_services.py \
  -v --tb=short
```

## Phase 2 — Track Split Modules By Review Unit

Status: complete

1. `tool_schemas/` extraction
   - `tool_registry.py` facade と schema module 群を単独単位にする。
   - Verification: `tests/test_tool_registry.py`
   - Review unit:
     - `services/brain/src/tool_registry.py`
     - `services/brain/src/tool_schemas/`
     - `tests/test_tool_registry.py`
     - `tests/test_tool_wiring.py`

2. `tool_handlers_*` extraction
   - `tool_executor.py` facade、handler mixin、`tool_dispatch.py` を単独単位にする。
   - Verification: `tests/test_tool_executor_pc.py`, `tests/test_tool_executor_services.py`, handler 到達テスト。
   - Review unit:
     - `services/brain/src/tool_executor.py`
     - `services/brain/src/tool_dispatch.py`
     - `services/brain/src/tool_handlers_*.py`
     - `services/brain/src/tool_http.py`
     - `tests/test_tool_executor_pc.py`
     - `tests/test_tool_executor_services.py`
     - `tests/test_tool_wiring.py`

3. `world_model` extraction
   - MQTT routing、physical / digital / user updates、context builder、presence を単独単位にする。
   - Verification: `tests/test_world_model_domains.py`, `tests/test_world_model_services.py`, sensor/freshness 系テスト。
   - 実装済み:
     - `tests/test_world_model_domains.py::test_world_model_exposes_split_mixin_methods`
     - `tests/test_world_model_domains.py` の `news_state` / `shopping_state` / `weather` legacy accessor getter/setter/mutation coverage。
     - `tests/test_world_model_mqtt_routing.py` の weather/news/personal knowledge/tapo/task_report routing matrix。
     - `tests/test_world_model_presence.py` の camera / presence sensor / recent motion / PC / biometric 由来 presence reconciliation。
     - `tests/test_world_model_occupancy_context.py::test_inferred_presence_appears_in_user_context`
   - Review unit:
     - `services/brain/src/world_model/world_model.py`
     - `services/brain/src/world_model/context_builder.py`
     - `services/brain/src/world_model/digital_updates.py`
     - `services/brain/src/world_model/mqtt_router.py`
     - `services/brain/src/world_model/physical_updates.py`
     - `services/brain/src/world_model/presence.py`
     - `services/brain/src/world_model/user_updates.py`
     - `tests/test_world_model_domains.py`
     - `tests/test_world_model_mqtt_routing.py`
     - `tests/test_world_model_presence.py`
     - `tests/test_world_model_occupancy_context.py`

4. `rules/` extraction
   - domain rule mixin 群と `rule_engine.py` facade を単独単位にする。
   - Verification: `tests/test_rule_engine_*.py`, `tests/test_wiring_gap_06.py`
   - 実装済み:
     - `tests/test_rule_engine_facade.py::test_rule_engine_exposes_all_domain_mixin_methods`
     - `tests/test_rule_engine_facade.py::test_mixin_rules_share_facade_cooldown_store`
     - `tests/test_rule_engine_facade.py::test_refresh_devices_populates_cache_and_respects_ttl`
     - `tests/test_rule_engine_sustained.py` の VOC / low pressure / low light / high light / heavy process sustained tracker coverage。
     - `tests/test_rule_engine_services.py` の low battery / low LQI / stale device / disabled device / per-device cooldown coverage。
     - `tests/test_rule_engine_thresholds.py` の facade env threshold reload coverage。
     - `tests/test_rule_engine_critical.py` の critical CO2 / temperature / moisture / SpO2 / sleep HR coverage。
   - Review unit:
     - `services/brain/src/rule_engine.py`
     - `services/brain/src/rules/`
     - `tests/test_rule_engine_facade.py`
     - `tests/test_rule_engine_services.py`
     - `tests/test_rule_engine_thresholds.py`
     - `tests/test_rule_engine_sustained.py`
     - `tests/test_rule_engine_critical.py`

## Phase 3 — Remaining Facade Responsibilities

Status: complete

1. `rule_engine.py` threshold constants
   - domain 別 config へ段階的に移動する。
   - 互換 import が必要な定数は一時的に facade から re-export する。
   - 実装済み: `services/brain/src/rules/config.py` に `RuleThresholds` / `load_rule_thresholds()` を追加し、
     `rule_engine.py` から従来の定数名を re-export。

2. `rule_engine.py` orchestration
   - cooldown、sustained-condition、device cache、GPU fallback 判定を shared runtime と domain rule のどちらに置くか決める。
   - 先にテストで共有状態の期待値を固定する。
   - 決定: orchestration state (`_cooldowns`, sustained-condition trackers, `_device_cache`, GPU fallback) は
     当面 facade に残す。domain mixin は facade-owned state を読む形を維持する。
   - 実装済み: facade/mixin wiring、shared cooldown、device cache TTL、sustained tracker、critical-only tests を追加。
   - 修正済み: heavy process tracker は top-process payload が空になった場合も stale entry を GC する。

3. `world_model.py` compatibility accessors
   - 残す accessor、移行対象 accessor、削除候補 accessor を棚卸しする。
   - 削除は別段階に回す。
   - 決定: 既存 call sites の互換性を優先し、`zones`, `pc_state`, `services_state`, `knowledge_state`,
     `gas_state`, `home_devices`, `biometric_state`, `news_state`, `shopping_state`, `weather` は維持する。
   - 実装済み: getter/setter/mutation coverage と split mixin surface sentinel を `tests/test_world_model_domains.py` に追加。

## Phase 4 — Docs And Repository Hygiene

Status: complete

1. historical docs notice
   - `SECURITY_AUDIT.md`、古い wiring / pitch / plan docs の冒頭に historical notice を追加する。
   - 本文の大規模修正は避ける。
   - 実装済み:
     - `SECURITY_AUDIT.md`
     - `docs/wiring-gap-05-orphan-cleanup-and-underused-data.md`
     - `docs/pitch-notebooklm.txt`
     - `docs/pitch-diagrams.mmd`
     - `docs/notes/upstream-port-plan.md`

2. OpenClaw/localcraw docs
   - active docs で canonical / alias 方針を固定する。
   - `OPENCLAW_BRIDGE_URL`: canonical
   - `LOCALCRAW_BRIDGE_URL`: legacy alias
   - compose service key `localcraw-bridge`: compatibility name
   - 実装済み: `docs/IMPLEMENTATION_MAP.md`, `docs/CLAUDE-bridges.md`, `env.example`, `infra/docker-compose.yml` の現行記述を確認。

3. `infra/eval` tracked artifacts
   - 履歴として保持するか、再生成物として `git rm --cached` するか決める。
   - どちらの場合も README または docs に方針を残す。
   - 実装済み: 履歴として保持する方針を `infra/eval/README.md` に明記。

## Full Verification Gate

通常環境で実行する正式 gate:

```bash
make lint
PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"
```
