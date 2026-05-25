# SUMMARY: サービス単位 実装監査 — 2026-05-25

`refactor/upstream-port` ブランチの全 Python サービス(Brain 4 分割 + backend + perception + voice/stt +
bridge 9 個)を **命名 / スコープ / 可読性 / doc 乖離** の 4 軸で監査。本パスは **監査 + doc 乖離是正のみ**
(コード無改変)。命名/スコープ/可読性の所見は各 `docs/audit/2026-05-25/{unit}.md` に refactor-ready 粒度で記録。

## 監査範囲・カバレッジ

- **全 16 unit + 終端 SUMMARY 完了**(ledger 全行 `done`)。
- 監査深度: Brain 4 unit + backend + perception + voice は **精読**(var/func レベル)。bridge 9 個は
  **契約 grep 検証(topic/route/tool/env)+ 構造スキャン**中心(行レベル精査は後続パス)。
  bridge で未到達: knowledge-bridge の RRF/embedding 内部、annotator/ ・ voice_capsule/(unit 4 で構造のみ)。

## 特殊ケース調査結果

- **openclaw**: in-repo source **無し**を確認。compose service `localcraw-bridge`(container `hems-openclaw-bridge`)が
  `context: ../../localcraw`(外部リポジトリ)から build。`CLAUDE-bridges.md §OpenClaw` はこの external build context を
  正しく記述済(乖離なし)。本パスで tools 2 件(`get_service_status`/`list_processes`)の欠落のみ補完。
- **data-bridge**: `README.md` のみの scaffold(`src/` 自体が存在しない)。監査スキップ(N/A)。root CLAUDE.md
  orphans 節に既記載で正確。

## P0 ロールアップ

**P0(挙動ブロッカー)は全 unit で 0 件。** 構造リファクタ後も機能は健全。最優先で対処価値が高い項目:

### P1(後続コードパスの最優先ターゲット)

| 出所 unit | 項目 | 影響 |
|---|---|---|
| brain-llm-tools-character / brain-rules-automation | `AutomationEngine._llm_review` が `LLMClient.chat` の戻り(`LLMResponse`)を **str 扱い** → AttributeError → 常に skip。**llm_review モードの automation が無音で発火しない** | 機能不全(mode=llm_review 限定) |
| brain-core-loop | god-function: `cognitive_cycle`(~470行)/ `_process_mqtt`(~240行) | 保守性・テスト困難 |
| brain-world-model / brain-rules-automation | **namespace 結合 / 準循環 import**(`_world_model.X` / `_rule_engine.X` で stdlib `time`/`datetime`・`logger`・定数・dataclass を facade 経由参照)。mixin 抽出の系統的副作用 | 脆弱な依存・認知負荷 |
| brain-world-model | `context_builder._get_physical_context`(~257行)god-method、`ShoppingState` dead state | 保守性 |
| brain-core-loop | dead code `_build_character_section`(~70行)、provider 別 tool-call 整形の cognitive↔chat 重複 | 削除/共通化候補 |
| backend | `verify_api_key` no-op で全 main ルーター実質無認証(LAN-trusted 設計だが `_auth` 装飾が誤認) | security 明確化要 |

### P2(命名・整理・重複)

- 誤誘導 leading `_`(`_summarize_action` 他)、find-replace 事故 4 件(`_world_model.time` がコメントに混入)、
  guard/プロンプトの欠番番号、magic number 散在。
- 閾値の多重ソース(world_model 定数 + RuleThresholds)、`_ALLOWED_ACTIONS` の sanitizer↔dispatcher 二重定義。
- 手製 ALTER TABLE マイグレーション(backend)、共有 session 未利用(scene_executor/queue_manager/speech_generator)、
  `should_dispatch` の presence 不整合(`is_anyone_home()` 不使用)。
- sanitizer の SOMS legacy(swarm_hub/pump)は `send_device_command` 廃止と同期して除去。

## doc 乖離是正サマリ(本パスで適用済)

| doc | 主な修正 |
|---|---|
| IMPLEMENTATION_MAP §2 | startup 配線の 2 段化(main.py `__init__` + brain_startup `_wire_runtime_components`)、Timeline/EventAutomation/PersonaRewriter は無条件 instantiate |
| IMPLEMENTATION_MAP §3 | 未掲載 9 ツール追記(58 ツール、schema↔handler 58==58 を §3.5 で機械検証) |
| IMPLEMENTATION_MAP §4.3/§4.4/§4.6/§5/§5.1 | reducer の mixin 分割反映、pc/processes/top は統合済(行削除)、ShoppingState 未populate、grep 先を mqtt_router/*_updates へ |
| IMPLEMENTATION_MAP §4.0 | SwitchBot device state は `hems/home/*`(HA 互換)へ publish |
| IMPLEMENTATION_MAP §7.3 | `weather_alert_announce` action 追記 |
| IMPLEMENTATION_MAP §8 | 5 endpoint をツール化済に更新(notes/tags・perception/cameras・vlm/status・knowledge/recent・ha device/{entity_id}) |
| services/brain/CLAUDE.md | subsystem 配線の 2 段化 + 起動条件 |
| services/backend/CLAUDE.md | ShoppingState 未populate |
| services/perception/CLAUDE.md | Brain tools 2→7 |
| services/voice/CLAUDE.md + CLAUDE.md | TTS provider `aivoice` 追記、`style-bert-vits2`(ゴースト)→ `aivoice` |
| docs/CLAUDE-bridges.md | 各 bridge の tool 補完(biometric/knowledge/obsidian/gas/ha/tapo/openclaw)、SwitchBot publish topic 訂正 |
| docs/README.md | Tier 4 index に `audit/2026-05-25/` 追加 |

## 未解決(後続)

- root `CLAUDE.md`: Database モデル列挙が 6/23(高レベル overview、要否判断)、MQTT prefix `hems/{tapo,switchbot}/*`
  は switchbot が hems/home/* な点で誤解を招く。
- `AUTOMATION_ENGINE_ENABLED` が `env.example` 未記載。
- bridge の行レベル精査(knowledge RRF / annotator / voice_capsule)。

## 最終検証
- 全 16 監査ファイル + SUMMARY が存在、ledger 全行 `done`。
- 各 unit commit で `git diff --stat` が `*.md` のみ(コード無改変)を確認済。`make lint` 各 unit クリーン。
