# Technical Debt Audit — 2026-05-24 Re-audit

対象: HEMS monorepo 全体。初回監査の再確認として、現在のワークツリー、Brain 分割後の配線、active docs / historical docs の混在、追跡済み評価成果物を中心に見直した。

## Summary

初回監査は浅く、現状とズレている。特に「Brain 周辺の巨大モジュールが最大リスク」という主張は、すでに分割リファクタが大きく進んだ現在の実態を表していない。

今回の主リスクは、巨大ファイルそのものではなく、分割後の配線互換性と大規模差分の検証負荷である。`tool_executor.py` / `tool_registry.py` / `world_model.py` は facade + domain module 構成へ移行済みで、`rule_engine.py` も domain 別 mixin に切り出されている。一方で、新規 `rules/`、`tool_schemas/`、`tool_handlers_*`、`world_model/*_updates.py`、`context_builder.py` などが未追跡で、既存の追跡済みファイルにも広範な変更が残っている。いま優先すべきは追加分割ではなく、schema / dispatch / handler / chat allowlist / reducer / bridge URL alias の回帰を固めること。

## Audit Basis

- `git status --short`: 多数の追跡済み変更に加え、Brain 分割後の新規ファイル群が未追跡。
- Brain facade 行数:
  - `services/brain/src/tool_executor.py`: 112 行
  - `services/brain/src/tool_registry.py`: 191 行
  - `services/brain/src/world_model/world_model.py`: 359 行
  - `services/brain/src/rule_engine.py`: 870 行
- `tests/test_tool_registry.py` に、全 feature flag 有効時の `get_tools(...)` schema 名と `TOOL_HANDLERS` の完全一致テストあり。
- active docs / compose / env example では `OPENCLAW_BRIDGE_URL` が canonical、`LOCALCRAW_BRIDGE_URL` は legacy alias。
- 通常環境での広域 pytest 結果: `1202 passed, 19 deselected`。

## Findings

### P0 — Green 判定は通常環境の結果だけを正式採用する

サンドボックス内の広域 pytest は信頼できる監査結果として扱わない。過去確認では `aiosqlite.connect()` 周辺でハングし得るため、完走しても参考値に留める。

正式な品質ゲートとして記録するのは、通常環境で実行された以下の結果。

```bash
make lint
PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"
```

広域 pytest は通常環境で `1202 passed, 19 deselected`。この監査では、サンドボックスでの広域 pytest 実行結果は採用しない。

### P1 — Brain 分割後の配線互換性

Brain の技術的負債は「巨大モジュールをこれから分割する」段階から、「分割後に同じ振る舞いを保てているかを証明する」段階へ移った。

- `tool_executor.py` は 112 行の facade になり、実処理は `tool_handlers_core.py`、`tool_handlers_pc.py`、`tool_handlers_home.py`、`tool_handlers_external.py` などへ移動済み。
- `tool_registry.py` は 191 行になり、schema 定義は `tool_schemas/` 配下へ移動済み。
- `world_model.py` は 359 行の facade + mixin 構成になり、MQTT routing、physical / digital / user updates、context build、presence が分離済み。
- `rule_engine.py` は 870 行。`rules/biometric.py`、`rules/gas.py`、`rules/home.py`、`rules/perception.py`、`rules/services.py`、`rules/shopping.py`、`rules/weather.py`、`rules/zigbee.py` に domain rule が切り出されている。ただし閾値定数、GPU fallback 判定、device cache、cooldown orchestration はまだ facade 側に残る。

既存テストで `TOOL_HANDLERS` と全 feature flag 有効時の `get_tools(...)` は一致確認されている。ただし、それだけでは十分ではない。次の重点回帰が不足すると、schema は存在するが chat に出ない、handler は登録されているが実行時属性がない、URL alias が効かない、WorldModel reducer が旧 topic と新 topic の片方だけ壊れる、という種類の退行を見落とす。

重点回帰対象:

- `get_chat_tools(...)` の read-only allowlist と schema の整合。
- `ToolExecutor.execute()` から各 `tool_handlers_*` の実 handler へ到達できること。
- `OPENCLAW_BRIDGE_URL` canonical と `LOCALCRAW_BRIDGE_URL` legacy alias の両方。
- `world_model` mixin 化後の MQTT topic routing と state reducer。
- `rule_engine` mixin 化後の cooldown / sustained-condition / device cache の共有状態。

### P1 — 未追跡ファイルを含む大規模差分

今回のワークツリーは、既存ファイルの修正だけでなく、分割後の新規ファイル群が未追跡のまま残っている。これは設計上の問題というより、レビューとリリース管理上のリスクである。

主な未追跡 Brain ファイル:

- `services/brain/src/rules/`
- `services/brain/src/tool_schemas/`
- `services/brain/src/tool_dispatch.py`
- `services/brain/src/tool_handlers_*.py`
- `services/brain/src/tool_http.py`
- `services/brain/src/brain_runtime.py`
- `services/brain/src/brain_startup.py`
- `services/brain/src/world_model/context_builder.py`
- `services/brain/src/world_model/digital_updates.py`
- `services/brain/src/world_model/mqtt_router.py`
- `services/brain/src/world_model/physical_updates.py`
- `services/brain/src/world_model/presence.py`
- `services/brain/src/world_model/user_updates.py`

この状態では、局所的な green だけでは信頼しにくい。分割単位ごとに「旧 public API が残っているか」「import path が変わっていないか」「feature flag の組み合わせで schema / handler が一致するか」を確認してから追跡対象に入れる必要がある。

### P1 — OpenClaw / localcraw は削除対象ではなく互換 alias と historical docs の問題

`localcraw` は単純な残骸ではない。現在の active docs と compose では、OpenClaw が運用名、`localcraw` が互換名として残っている。

- canonical env: `OPENCLAW_BRIDGE_URL`
- legacy env alias: `LOCALCRAW_BRIDGE_URL`
- compose profile: `openclaw` が正、`localcraw` は互換 profile
- compose service key: `localcraw-bridge` が互換のため残存
- container / DNS alias: `hems-openclaw-bridge` / `openclaw-bridge`
- build context: 外部 legacy repo `../localcraw`

従って、`localcraw` を機械的に全削除するのは危険。active docs では canonical / alias を明記し、古い監査・計画ドキュメントには historical notice を付ける方針が正しい。

historical notice 対象:

- `SECURITY_AUDIT.md` の `services/openclaw-bridge` 参照。
- 古い wiring / pitch / plan docs の `localcraw-bridge` 前提。
- 既に閉じた前提を含む計画 docs。

### P2 — Active docs と historical docs の混在

`docs/IMPLEMENTATION_MAP.md` や `docs/CLAUDE-bridges.md` は現在の OpenClaw canonical / localcraw alias 方針を説明している。一方で、古い監査・計画・pitch 資料には当時の service 名や構成が残る。

対応方針:

- active docs は現在の構成を SoT として同期する。
- historical docs は本文を書き換えすぎず、冒頭に「当時の構成に基づく historical document」と明記する。
- active docs から historical docs へリンクする場合は、古い service 名や未実装前提を現行仕様と誤読しない注記を付ける。

### P2 — 追跡済み評価成果物

生成物・評価成果物が追跡済みのまま残っている。ベンチマーク履歴として保持する判断もあり得るが、再生成物として扱うなら untrack と ignore 方針を決める必要がある。

追跡済み:

- `infra/eval/eval.log`
- `infra/eval/results/_progress.json`
- `infra/eval/results/*.jsonl`

## Recommended Next Steps

1. Brain 分割差分を追跡対象に入れる前に、schema / handler / chat allowlist / URL alias / reducer の重点回帰を追加または確認する。
2. 分割後の public API 互換を `tests/test_tool_registry.py` だけに依存せず、`ToolExecutor.execute()` 経由の実行テストでも押さえる。
3. `rule_engine.py` に残る閾値定数と orchestration は、追加分割より先に「どの mixin が共有状態を読むか」を文書化する。
4. OpenClaw/localcraw は active docs で canonical / alias を維持し、historical docs には notice を付ける。
5. `infra/eval` の追跡済み成果物を、履歴として残すのか再生成物として外すのか決める。

## Verification Targets

通常環境で重点確認する対象:

```bash
PYTHONPATH=services/brain/src:services/backend .venv/bin/python -m pytest \
  tests/test_tool_registry.py \
  tests/test_tool_executor_pc.py \
  tests/test_tool_executor_services.py \
  tests/test_world_model_domains.py \
  tests/test_world_model_services.py \
  tests/test_rule_engine_biometric.py \
  tests/test_rule_engine_gas.py \
  tests/test_rule_engine_home.py \
  tests/test_rule_engine_occupancy.py \
  tests/test_rule_engine_pc.py \
  tests/test_rule_engine_perception.py \
  tests/test_rule_engine_zigbee.py \
  tests/test_wiring_gap_06.py \
  -v --tb=short
```

広域確認:

```bash
make lint
PYTHONPATH=services/brain/src:services/backend timeout 1800s .venv/bin/python -m pytest tests/ services/brain/tests/ -v --tb=short -m "not integration and not e2e and not benchmark"
```

サンドボックス内の pytest は、完走しても正式な green 判定には使わない。
