# 監査: brain-llm-tools-character — 2026-05-25

## スコープ
- 対象 path(すべて `services/brain/src/`):
  - LLM: `llm_client.py`(270)・`llm_router.py`(69)・`mcp_bridge.py`(62)
  - tool 基盤: `tool_executor.py`(112)・`tool_registry.py`(186)・`tool_dispatch.py`(60)・`tool_http.py`(6)・
    `tool_handlers_*.py`(9 ファイル, ~1,700)・`tool_schemas/`(10 ファイル)
  - character: `character_loader.py`(706)・`persona_rewriter.py`(211)
  - device: `device_registry.py`(319)・`device_dispatcher.py`(896)
  - 周辺: `annotator/`(6 ファイル)・`voice_capsule/`(7 ファイル)
  - 計 ~8,000+ LOC
- **監査深度**: tool registry↔dispatch 整合・LLM 基盤・character 2-stage・device dispatch・sanitizer 照合は
  精読/機械検証。`tool_handlers_*` は registry 経由で網羅確認、`tool_schemas` / `annotator` / `voice_capsule` は
  構造スキャン(find-replace 事故・TODO・session 生成の有無)止まり。後者の行レベル精査は後続パスへ。
- 参照 canonical doc: `services/brain/CLAUDE.md`、`docs/IMPLEMENTATION_MAP.md` §3

## doc 乖離(本パスで修正適用済)

| # | doc claim | code reality | 修正先 doc | 状態 |
|---|---|---|---|---|
| 1 | §3 表が tool を 49 件のみ掲載 | 実際は **58 ツール**(`get_tools()` 全 flag 有効時)。未掲載 9 件: `gas_query_free_slots`/`gas_query_sheet`/`list_note_tags`/`get_recent_knowledge_changes`/`get_biometric_trend`/`get_sleep_history`/`list_cameras`/`get_vlm_status`/`get_activity_history`(全て `tool_dispatch.TOOL_HANDLERS` + schema に存在) | IMPLEMENTATION_MAP §3.2 + §3 intro | ✅ 9 件追記 + 総数明記 |

機械検証(§3.5 を実行):`schema_count 58 / handler_count 58 / schema_only [] / handler_only []` — **registry↔dispatch は完全一致**(整合性 OK)。

### unit 1 の cross-check 項目を解決
unit 1(sanitizer)で「許可リストに canonical 未掲載ツールがある」と flag した 9 件は、**全て tool_registry に実在**することを確認(`list_note_tags`/`gas_query_sheet` 等は IN schema)。よって sanitizer の問題ではなく **§3 doc の不完全**が真因。本パスで §3 を補完して解消。

## 命名所見(refactor-ready)

| 優先度 | current → proposed | file:line | 理由 |
|---|---|---|---|
| P2 | `get_active_tasks` の無引数特例を解消 | tool_executor.py:104-105 | 1 ツールだけ `handler()`、他は `handler(arguments)` の分岐。ハンドラ署名を統一すれば特例不要 |

## スコープ所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P1 | ~~`AutomationEngine._llm_review` 戻り値型バグ~~ → **実装済み**。`automation_engine.py:296` で `response.content` を使用し、LLMResponse オブジェクトを正しく扱う | automation_engine.py:296 ↔ llm_client.py:33 | — |
| P2 | ~~`_ALLOWED_ACTIONS`(actuator 許可アクション)が sanitizer と device_dispatcher で二重定義~~ → **実装済み**。`devices/actions.py:10` の `DEVICE_ALLOWED_ACTIONS` を単一 SoT とし、`device_control_validator.py:27` が import、`sanitizer.py:365` が `validate_device_control` に委譲 | sanitizer.py:365 / device_control_validator.py:27 / devices/actions.py:10 | — |
| P2 | `annotator/`(6)・`voice_capsule/`(7)は構造スキャンのみ(行レベル未精査) | annotator/ , voice_capsule/ | 後続パスで EventClassifier/RulePromoter/ShoppingClassifier/CapsuleBuilder を精読 |

## 可読性所見(refactor-ready)

| 優先度 | 問題 | file:line | 推奨 |
|---|---|---|---|
| P2 | ~~`PersonaRewriter.rewrite` と `rewrite_long` が ~80% 重複~~ → **実装済み**。両メソッドは `persona_rewriter.py:79` の `_rewrite_impl(...)` を共用 | persona_rewriter.py:45,70,79 | — |
| P2 | `parse_mqtt` ~130 行(vendor 検出分岐) | device_dispatcher.py:72-204 | vendor 別 parser へ分割可(現状でも可読、優先度低) |
| P2 | `_dict_to_config` ~110 行の手動マッピング | character_loader.py:273-382 | dataclass フィールド駆動化の余地(ただし inheritance 解決と絡むため慎重に) |

## 後続リファクタ推奨(優先度順サマリ)

- **P1**:
  1. ~~`AutomationEngine._llm_review` の戻り値型バグ修正(`response.content` 化)~~ → **実装済み**(`automation_engine.py:296`)。
- **P2**:
  - ~~`_ALLOWED_ACTIONS` の二重定義を 1 SoT に統合(sanitizer ↔ device_dispatcher)~~ → **実装済み**(`devices/actions.py:10` SoT、`device_control_validator.py:27`、`sanitizer.py:365`)。
  - ~~`PersonaRewriter` の rewrite/rewrite_long 共通化~~ → **実装済み**(`persona_rewriter.py:79` `_rewrite_impl`)。
  - tool_executor のハンドラ署名統一(`get_active_tasks` 特例解消)。
  - `annotator/` `voice_capsule/` の行レベル精査(本パス未到達)。
- **P0**: registry↔dispatch は 58=58 で整合。挙動ブロッカー無し(`_llm_review` は llm_review モード限定の機能不全で P1)。

## 確認できた canonical の正確性(乖離なし)
- §3.5 整合検証は現状でも pass(58↔58)。
- character 2-stage 分離(Stage 1 raw=character 注入なし、Stage 2 PersonaRewriter 事後変換)は `system_prompt.py`(unit 1)+ `persona_rewriter.py` で実装一致。
- §3.1 always-on / §3.3 device registry / §3.4 chat-only allowlist は実装と一致。
