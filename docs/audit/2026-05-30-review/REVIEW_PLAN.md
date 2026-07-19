# REVIEW_PLAN — HEMS de-bloat レビュー 2026-05-30(30 kickoff prompts)

使い方: 各セッションの `kickoff` code-block を **新規 Claude セッション**へそのまま paste する。対象 dir で
auto-load される `CLAUDE.md` が共有コンテキストを補う。成果は `notes/REVIEW-<id>.md` に出力し、`LEDGER.md`
の該当行を更新する。レンズ/到達点/出力規約は全セッション共通(各 kickoff に折り込み済み)。方法論の全文は
[`README.md`](README.md) を参照。

凡例: 各 kickoff の `# レンズ`・`# 到達点`・`# 出力` は共通テンプレ。`# 対象`・`# 重点`・`# baseline` が
セッション固有。実装は **別 worktree/ブランチ**で行い、`git diff` を親が独立検証してからマージする。

---

## 1. brain-core-loop(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 1/30「brain-core-loop」。
主目的は Coding Agent で肥大化したコードの de-bloat。

# 先に読む(共有コンテキスト)
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-core-loop.md(前回監査 baseline)
- docs/IMPLEMENTATION_MAP.md §2(startup 配線)
- 共有依存(読むだけ): brain_constants.py / world_model/ / llm_client.py

# 対象(これだけを精読。すべて services/brain/src/)
main.py, brain_cognitive.py, brain_startup.py, brain_loops.py, brain_runtime.py,
brain_constants.py, brain_utils.py, llm_client.py, llm_router.py

# レンズ(主軸=de-bloat, 従=フル監査)
主) 1 dead-code 2 duplication 3 god-function/over-long 4 over-engineering 5 bad-knowhow
従) 6 correctness 7 security 8 doc 乖離(2026-05-25 是正済は検証のみ)
# 重点
- god-function: cognitive_cycle(~470行)/ _process_mqtt(~240行) の抽出単位を refactor-ready で
- dead code: _build_character_section(~70行, 前回 dead 指摘)が今も未参照か grep 確認 → 削除候補
- llm_router(69行)が llm_client へ畳めるか、provider 別 tool-call 整形の cognitive↔chat 重複
- 5-iter 終了制御 / consecutive-error 復帰 / boot_load client state 漏れ(correctness)
# baseline
前回 P1(god-function 2 件)/ stale comment(low_power_mode.py:115 が main.py 参照)が生きているか検証。

# 到達点(ハイブリッド)
- 低リスク(挙動不変: dead-code 削除/未使用 import 整理/明白な重複統合/stale comment 除去)→ 別 worktree で実装 →
  make lint + 該当 pytest(tests/ services/brain/tests/ の関連)緑 → git diff 提示。
- 構造変更(god-function 分割・抽象作り直し)→ 実装せず提案。削減見込み LOC を付す。

# 出力
docs/audit/2026-05-30-review/notes/REVIEW-brain-core-loop.md に P0/P1/P2 + file:line(実装済=✅削減LOC, 提案=💡)。
docs/audit/2026-05-30-review/LEDGER.md の 1 行目を更新(status / P0-P2 件数 / 削減LOC)。
スコープ外への波及は notes 末尾「Cross-cutting」に記録(直さない)。
```

---

## 2. brain-world-model(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 2/30「brain-world-model」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-world-model.md(baseline)
- docs/IMPLEMENTATION_MAP.md §4.3/§4.6(reducer / routing)
- 共有依存(読むだけ): brain_constants.py

# 対象(services/brain/src/world_model/ 全 11 ファイル)
world_model.py, data_classes.py, sensor_fusion.py, context_builder.py, physical_updates.py,
digital_updates.py, user_updates.py, mqtt_router.py, sensor_validation.py, presence.py, __init__.py(+ models は data_classes)

# レンズ / 到達点 / 出力 — 共通(セッション1と同形。notes=REVIEW-brain-world-model.md, LEDGER 2 行目)
# 重点
- god-method: context_builder._get_physical_context(~257行)の分割案
- bad-knowhow: mixin の namespace 結合(_world_model.time / logger / 定数を facade 経由参照する準循環)を列挙
- dead: ShoppingState dead state(前回指摘)が今も未populate か、find-replace 事故コメント(_world_model.time)4 件
- correctness: 並行 MQTT 書込の locking 欠如・staleness 判定・context token 膨張
# baseline
前回 P1(namespace 結合 / god-method)の生存確認。doc 乖離は是正済 → 検証のみ。
```

---

## 3. brain-rules-automation(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 3/30「brain-rules-automation」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-rules-automation.md(baseline)
- docs/IMPLEMENTATION_MAP.md §6/§7(rules / automation)
- 共有依存(読むだけ): world_model/ / llm_client.py

# 対象(services/brain/src/)
rule_engine.py, automation_engine.py, schedule_learner.py, efficacy.py, event_automation.py
+ rules/ 全 9: biometric.py, gas.py, home.py, perception.py, services.py, shopping.py, weather.py, zigbee.py, config.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-rules-automation.md, LEDGER 3 行目)
# 重点
- god-method: RuleEngine.evaluate(~490行)の environment/PC rule 抽出案
- correctness(P1 候補): AutomationEngine._llm_review が llm_client.chat の戻り(LLMResponse)を str 扱い
  → AttributeError で llm_review automation が無音 skip(前回 P1)。生存確認 + 修正案
- dead: efficacy.py(67行)が未配線か grep で実証 → dead なら削除候補
- bad-knowhow: rules mixin の namespace 結合(_rule_engine.X)・cooldown が memory-only(再起動で消える)
# baseline
前回 P1 3 件(namespace 結合 / god-method / _llm_review 型バグ)の生存確認。
```

---

## 4. brain-tool-surface(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 4/30「brain-tool-surface」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-llm-tools-character.md(baseline)
- docs/IMPLEMENTATION_MAP.md §3(tool registry↔dispatch)
- 注: tests/test_tool_registry.py が schema↔handler 完全一致を機械検証済(2026-05-30 時点 15 passed)

# 対象(services/brain/src/)
tool_executor.py, tool_dispatch.py, tool_registry.py, sanitizer.py, brain_chat_server.py, tool_http.py
+ tool_schemas/ 全 9: base.py, biometric.py, core.py, device.py, external.py, home.py, pc.py, perception.py, switchbot.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-tool-surface.md, LEDGER 4 行目)
# 重点
- security: blind-mode の既定許可(新規 tool が default で許可=unsafe default)、chat allowlist drift、
  sanitizer の text injection filter の穴、device allowlist が動的(Device Registry)でなくハードコードか
- dead/dup: sanitizer の SOMS legacy(swarm_hub / pump)が send_device_command 廃止と同期して除去できるか、
  _ALLOWED_ACTIONS の sanitizer↔dispatcher 二重定義
- bad-knowhow: tool_http.py(6行)の存在意義、未使用 schema フィールド
# baseline
前回 registry↔dispatch は 58=58 一致確認済 → 今回は回帰確認 + de-bloat に集中。
```

---

## 5. brain-tool-handlers-devices(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 5/30「brain-tool-handlers-devices」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-llm-tools-character.md(baseline。device_dispatcher は前回 unit4 へ繰延)
- docs/IMPLEMENTATION_MAP.md §3(handlers)
- 共有依存(読むだけ): world_model/ / device_registry_client(backend HTTP)

# 対象(services/brain/src/)
tool_handlers_core.py, tool_handlers_world.py, tool_handlers_device.py, tool_handlers_home.py,
tool_handlers_pc.py, tool_handlers_biometric.py, tool_handlers_perception.py, tool_handlers_switchbot.py,
tool_handlers_external.py, device_dispatcher.py(901行), device_registry.py, scene_executor.py,
mcp_bridge.py, sunrise_alarm.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-tool-handlers-devices.md, LEDGER 5 行目)
# 重点
- god-file: device_dispatcher.py(901行)の vendor 別 dispatch 分割案、dispatch fallthrough(未知 device が silent fail か)
- correctness: scene 原子性(部分失敗時のロールバック無し)、_ha_rainbow の task 追跡漏れ(overlapping animation)、actuator safety bound
- dead/dup: mcp_bridge.py(62行, legacy MCP)が現役か、handler 間のコピペ整形
# baseline
device_dispatcher は前回未精査(unit4 繰延)→ 今回が初回精読。
```

---

## 6. brain-persona-voice(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 6/30「brain-persona-voice」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-llm-tools-character.md(baseline。voice_capsule は前回構造スキャンのみ)
- 共有依存(読むだけ): llm_client.py / character 設定(config/character.yaml)

# 対象(services/brain/src/)
character_loader.py(706行), persona_rewriter.py, system_prompt.py(453行), ambient_speaker.py, motion_retriever.py
+ voice_capsule/ 全 7: ack_learner.py, builder.py, clip_planner.py, generic_bank.py, persist.py, transcript_writer.py, __init__.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-persona-voice.md, LEDGER 6 行目)
# 重点
- voice_capsule/ を今回初めて行レベル精読(前回構造のみ)→ dead/dup/over-engineering を重点的に
- god-file: character_loader.py(706行)/ system_prompt.py(453行)の分割案
- security: system_prompt 組み立て時の prompt injection 面(character YAML / world state 由来テキスト)
- correctness: YAML 継承の循環検出が 1 段のみか、2-stage(raw→rewrite)の状態漏れ、capsule builder の OOM
```

---

## 7. brain-event-store-data(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 7/30「brain-event-store-data」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-world-model.md(baseline。brain_mqtt routing 部)
- docs/IMPLEMENTATION_MAP.md §4(MQTT)/§5(event store)
- 共有依存(読むだけ): world_model/mqtt_router.py / dashboard_client の backend HTTP

# 対象(services/brain/src/)
brain_mqtt.py, dashboard_client.py(758行)
+ event_store/ 全 5: aggregator.py, database.py, models.py, writer.py, __init__.py
+ annotator/ 全 6: cache.py, event_classifier.py, rule_promoter.py, rules.py, shopping_classifier.py, __init__.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-event-store-data.md, LEDGER 7 行目)
# 重点
- correctness: 730d retention が実際に実装/起動されているか(cleanup job の有無を grep で確認)、
  write batch ドロップ時の dead-letter 有無、SQLite↔PG schema 差(event_store schema は PG 専用か)
- annotator/ を今回精読 → classifier cache の TTL/汚染、shopping dedup 欠如
- dead/dup: dashboard_client.py(758行)の重複 HTTP 整形、annotator/rules.py の使用状況
# baseline
前回 event_store は §5 で doc 是正済 → 実装の retention 検証に集中。
```

---

## 8. brain-scheduling-power(group: brain)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 8/30「brain-scheduling-power」。主目的は de-bloat。

# 先に読む
- services/brain/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/brain-core-loop.md(baseline。boot_load / low_power 部)
- 共有依存(読むだけ): brain_constants.py / world_model/

# 対象(services/brain/src/)
task_reminder.py, boot_load_manager.py(537行), low_power_mode.py
+ timeline/ 全 6: edf_scheduler.py, free_window.py, generator.py, models.py, travel_config.py, __init__.py
+ task_scheduling/ 全 4: decision.py, priority.py, queue_manager.py, __init__.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-brain-scheduling-power.md, LEDGER 8 行目)
# 重点
- correctness: power-mode 遷移時に suppressed tool が復帰するか、timeline regen debounce race(5s 内多重トリガ)、
  reminder spam(get_active_tasks 失敗時も発火)、_daily_maintenance が再起動で 2 回走る
- EDF scheduler の正当性(services/brain/tests/timeline/ に既存テストあり → 併読)
- dead/dup: task_scheduling/(134行)の薄さ、boot_load_manager の god-method 候補
```

---

## 9. backend-routers(group: backend)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 9/30「backend-routers」。主目的は de-bloat。

# 先に読む
- services/backend/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/backend.md(baseline)
- docs/IMPLEMENTATION_MAP.md §8(REST endpoints)

# 対象(services/backend/routers/ 全 27 + __init__.py)
automations, biometric, brain, bridge_status, character, chat, classifier_cache, device_actions, devices,
frequent_places, gas, home, knowledge, mobile, news, pc, perception, scenes, services, shopping, tasks,
timeline, timeseries, users, voice_events, weather, zones

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-backend-routers.md, LEDGER 9 行目)
# 重点
- security: 全 router が verify_api_key dep を持つか(前回 P1: verify_api_key が no-op で実質無認証。mobile のみ実認証)
- dead/dup: router 間のコピペ CRUD ボイラープレート → 共通化候補(削減 LOC 大)、未使用 endpoint
- correctness: /devices/heartbeat の untrusted device_id 自動登録、device_actions の sanitizer 範囲(pulse/brightness/color temp)
- chat router の sliding window(last 20)と frontend の不整合
# baseline
前回 backend P1(verify_api_key no-op)の生存確認。doc 乖離(§8 4 endpoint)は是正済 → 検証のみ。
```

---

## 10. backend-persistence(group: backend)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 10/30「backend-persistence」。主目的は de-bloat。

# 先に読む
- services/backend/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/backend.md(baseline)

# 対象(services/backend/)
main.py, database.py, models.py, schemas.py, auth.py, hmac_util.py + audio/(config + mp3 util)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-backend-persistence.md, LEDGER 10 行目)
# 重点
- bad-knowhow(P2, 前回指摘): lifespan の手製 ALTER TABLE マイグレーション(例外握り潰し、additive only)
- security: auth.py verify_api_key の no-op、hmac_util の replay 防止、secret 既定値
- correctness: SQLite↔PG 互換(TZDateTime, JSONB, BigInteger)、FK cascade / unique 制約 / index
- dead/dup: schemas.py の未使用 Pydantic モデル、wallet 形状フィールド不在の確認(SOMS 禁止項: balance/credits/xp/multiplier/demurrage)
```

---

## 11. frontend-avatar(group: frontend)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 11/30「frontend-avatar」。主目的は de-bloat。
(frontend は CLAUDE.md auto-load 無し。node_modules は読まない)

# 先に読む
- CLAUDE.md(root)の Frontend / 3D Avatar 節、docs/avatar-setup.md

# 対象(services/frontend/src/)
components/vrm/ 全 14 + hooks/use-avatar-mode.ts + lib/avatar-type.ts

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-frontend-avatar.md, LEDGER 11 行目)
# 重点
- correctness: VRM model lifecycle の cleanup 漏れ(memory leak)、animation loop と AudioQueue の同期、
  Kalidokit pose→bone マッピング、2D↔3D mode 切替時の state 永続
- dead/dup: 未使用 three.js import、コメントアウトされた旧 avatar 実装、motion registry の重複
- 到達点: 低リスク = 未使用 import / dead component 削除 → pnpm tsc + pnpm build 緑 → git diff。構造変更は提案。
```

---

## 12. frontend-dashboard(group: frontend)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 12/30「frontend-dashboard」。主目的は de-bloat。

# 先に読む
- CLAUDE.md(root)の Frontend 節

# 対象(services/frontend/src/)
app/ 全 5 ページ(dashboard, devices, digital, mobile, user)
+ components/ 13 subdir: automations, brain, dashboard, devices, digital, layout, physical, psd, scenes, shared, tasks, ui, user
(vrm は #11、lib/api は #13。最大スコープ ~7k LOC ≈ 全体の de-bloat 効果が最も高い)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-frontend-dashboard.md, LEDGER 12 行目)
# 重点
- dead/dup: 未使用 component / prop / コピペされた card・list・form(Coding Agent 肥大化の本丸。削減 LOC 大)
- over-engineering: 過剰な抽象 wrapper、1 箇所しか使わない汎用 hook
- correctness: optimistic update と backend truth の整合、WS/SSE 再接続時の取りこぼし、timeline 大量データの memory
- 到達点: 低リスク = dead component / 未使用 import 削除 → pnpm tsc + build 緑 → git diff。大きな再構成は提案のみ。
```

---

## 13. frontend-data-layer(group: frontend)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 13/30「frontend-data-layer」。主目的は de-bloat。

# 先に読む
- CLAUDE.md(root)の Frontend / STT 節

# 対象(services/frontend/src/)
lib/api/ 全 15 + lib/(api-client 等 10) + hooks/(avatar 除く) + audio/(STT 連携)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-frontend-data-layer.md, LEDGER 13 行目)
# 重点
- dup: 15 の api モジュール間で fetch + auth header + error handling のボイラープレートが重複 → 共通化候補(削減 LOC 大)
- correctness: Bearer token refresh / logout 時の pending request、STT mode(PTT/VAD/OFF)の Silero VAD ONNX lifecycle、
  server STT 不在時の Web Speech API fallback、theme hook の hydration mismatch
- dead: 未使用 api ラッパ / 型定義
- 到達点: 低リスク = 重複 fetch ラッパ統合 + dead 削除 → pnpm tsc + build 緑 → git diff。
```

---

## 14. voice(group: service)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 14/30「voice」。主目的は de-bloat。

# 先に読む
- services/voice/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/voice.md(baseline。前回クリーン判定)

# 対象(services/voice/src/)
main.py, models.py, provider_factory.py, tts_provider.py, speech_generator.py, text_processor.py
+ providers/: voisona.py, voicevox.py, espeak.py, edge_tts_provider.py, aivoice.py, fallback.py

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-voice.md, LEDGER 14 行目)
# 重点
- 前回 P0/P1 無し・クリーン判定 → 今回は de-bloat に純化: provider 5 種間のコピペ、未使用 fallback 分岐、
  over-engineering(1 実装しか通らない抽象)、subprocess / audio handling の例外握り潰し
- doc: 前回 aivoice 追記済 → 検証のみ
```

---

## 15. perception(group: service)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 15/30「perception」。主目的は de-bloat。
⚠️ このサービスは未コミットの作業ツリー変更 + 新規 tests/ がある。最初に `git status` と
   `git diff -- services/perception/` を確認し、レビューが既存変更前提か作業中かを判断すること。

# 先に読む
- services/perception/CLAUDE.md(auto-load)
- docs/audit/2026-05-25/perception.md(baseline。前回「最もクリーンなユニットの一つ」)
- services/perception/NOTICE(RTMO ライセンス attribution)

# 対象(services/perception/src/)
main.py, detector.py, config.py, activity_tracker.py, camera_manager.py, mqtt_publisher.py,
vlm_scheduler.py, vlm_analyzer.py + tests/(新規)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-perception.md, LEDGER 15 行目)
# 重点
- 未コミット変更の妥当性(detector/activity_tracker/vlm_scheduler/config/main が M)を de-bloat 観点で確認
- correctness: VLM model swap 時の brain LLM eviction(~10-30s)、camera 切断 retry、activity classifier の pose noise 感度
- dead/dup: vlm_scheduler の状態機械の複雑さ、未使用 camera source 分岐
- privacy: カメラ frame の取り扱い
```

---

## 16. stt(group: service)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 16/30「stt」。主目的は de-bloat。
(stt は CLAUDE.md auto-load 無し。前回は voice.md に同梱で 3 provider 一致のみ確認 → 今回が初の単独精読)

# 先に読む
- docs/audit/2026-05-25/voice.md(baseline の stt 言及部)

# 対象(services/stt/src/)
main.py, provider_factory.py, models.py, stt_provider.py, audio_utils.py, query_cleaner.py
+ providers/: whisper, sherpa_onnx, qwen3_asr

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-stt.md, LEDGER 16 行目)
# 重点
- correctness: ffmpeg subprocess の stdout/stderr capture とエラー伝播、GPU device 自動検出(CUDA/ROCm/CPU)分岐、
  query_cleaner の Ollama rewrite 不在時の regex fallback、multipart form の WebM 変換
- dead/dup: provider 3 種間のコピペ、未使用 compute_type 分岐、over-engineering
```

---

## 17. bridge-smarthome(group: bridge)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 17/30「bridge-smarthome」。主目的は de-bloat。

# 先に読む
- docs/CLAUDE-bridges.md(HA / SwitchBot / Tapo 節)
- docs/audit/2026-05-25/{ha-bridge,switchbot-bridge,tapo-bridge}.md(baseline。前回 P0/P1 無し・構造健全)

# 対象(top-level service dir)
services/ha-bridge/, services/switchbot-bridge/, services/tapo-bridge/

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bridge-smarthome.md, LEDGER 17 行目)
# 重点
- 前回は契約 grep + 構造スキャンのみ(行レベルは後続)→ 今回行レベル精読で de-bloat
- dup: 3 bridge 間の mqtt_publisher / device_mapper / API client のコピペ → 共通化候補
- security: HA token / SwitchBot HMAC 署名 / Tapo LAN creds の取り扱い、secret 既定値
- doc: switchbot device state は hems/home/*(HA 互換)— 前回 §4.0 訂正済、検証のみ
```

---

## 18. bridge-ingestion(group: bridge)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 18/30「bridge-ingestion」。主目的は de-bloat。

# 先に読む
- docs/CLAUDE-bridges.md(knowledge / biometric 節)
- docs/audit/2026-05-25/{knowledge-bridge,biometric-bridge}.md(baseline。RRF/embedding は前回未到達)

# 対象(top-level service dir)
services/knowledge-bridge/(17 files), services/biometric-bridge/(10 files)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bridge-ingestion.md, LEDGER 18 行目)
# 重点
- 前回未到達の内部を今回精読: knowledge の RRF / embedding / chunking、document loader 各形式の例外処理
- security/privacy: biometric は PII。Xiaomi/CMF creds、ローカル保存限定か、dedup(step 二重計上防止)
- dead/dup: loader 各形式のコピペ、未使用 embedding model 分岐、provider 間重複
```

---

## 19. bridge-external-data(group: bridge)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 19/30「bridge-external-data」。主目的は de-bloat。

# 先に読む
- docs/CLAUDE-bridges.md(weather / news 節)
- docs/audit/2026-05-25/{weather-bridge,news-bridge}.md(baseline。前回「最もクリーン・doc 乖離なし」)

# 対象(top-level service dir)
services/weather-bridge/(JMA + OWM), services/news-bridge/(RSS + Ollama summarizer)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bridge-external-data.md, LEDGER 19 行目)
# 重点
- 前回最もクリーン判定 → 今回は純 de-bloat: provider 抽象の過剰さ、RSS dedup の有無、
  OWM API key 不在時の graceful degrade、summarizer(Ollama)不在時の skip
- dead: 未使用 polling 分岐、XML/JSON 正規化のコピペ
```

---

## 20. bridge-personal(group: bridge)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 20/30「bridge-personal」。主目的は de-bloat。

# 先に読む
- docs/CLAUDE-bridges.md(GAS / Obsidian 節)
- docs/audit/2026-05-25/{gas-bridge,obsidian-bridge}.md(baseline)

# 対象(top-level service dir)
services/gas-bridge/, services/obsidian-bridge/

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bridge-personal.md, LEDGER 20 行目)
# 重点
- security: GAS の OAuth token 取り扱い / scope、Gmail read-only 境界、Obsidian vault path / lock
- correctness: Obsidian 双方向 sync の conflict、GAS rate limit、token refresh
- dead/dup: poller のコピペ、未使用 GAS サブ API(sheets/drive は world_model 流入のみで consumer 無し=前回 orphan 指摘)
```

---

## 21. bnd-mqtt-contract(group: boundary)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 21/30「bnd-mqtt-contract」(横断契約)。主目的は契約の健全性 + de-bloat。

# 先に読む
- docs/IMPLEMENTATION_MAP.md §4(MQTT topic tree / publishers / routing)
- docs/CLAUDE-bridges.md

# 対象(全サービス横断、grep ベース)
全 publish() を grep: services/*/src/mqtt_publisher.py 他、backend routers/shopping.py 等。
subscriber: services/brain/src/world_model/mqtt_router.py + brain main.py on_connect。

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bnd-mqtt-contract.md, LEDGER 21 行目)
# 重点
- publisher→subscriber マップを作る。prefix: office/, hems/pc/, hems/services/, hems/home/, hems/personal/*,
  hems/gas/*, hems/{weather,news,shopping}, hems/perception/vlm/*, hems/{tapo,switchbot}, zigbee2mqtt/, hems/<svc>/bridge/status, hems/brain/*
- dead(orphan topic): published-but-never-consumed(前回指摘 hems/services/{name}/event, hems/gas/sheets,drive 等)、
  逆(subscribed-but-never-published)、prefix typo、retain/QoS 誤り
- 注: switchbot device state は hems/home/*(HA 互換)で root CLAUDE.md の hems/switchbot/* は誤解を招く — 検証
# 到達点
契約マップ自体が成果物。dead topic の publisher 側コード削除は低リスク実装候補(該当サービスの publish 呼び出し)。
```

---

## 22. bnd-http-rest(group: boundary)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 22/30「bnd-http-rest」(横断契約)。主目的は契約整合 + de-bloat。

# 先に読む
- docs/IMPLEMENTATION_MAP.md §8(REST)、services/backend/CLAUDE.md

# 対象
frontend services/frontend/src/lib/api/*.ts(15)↔ backend services/backend/routers/*.py(27)
↔ brain device_registry_client / task queue → backend /devices/heartbeat 等、brain_chat_server.py。

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bnd-http-rest.md, LEDGER 22 行目)
# 重点
- 契約 drift: frontend TS 型 vs backend Pydantic schema の不一致、未使用 endpoint(どちらか一方にしかない)
- security: BACKEND_API_KEY auth の一貫性(全 router か)、CORS(ALLOWED_ORIGINS)、error 形式の統一
- device control proxy: frontend → backend /devices/{id}/control → brain → device_dispatcher の経路整合
- dead: frontend に呼び出し元の無い api ラッパ、backend に consumer の無い endpoint(削減候補)
```

---

## 23. bnd-tool-integrity(group: boundary)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 23/30「bnd-tool-integrity」(横断契約)。

# 先に読む
- docs/IMPLEMENTATION_MAP.md §3、services/brain/CLAUDE.md
- 既知: tests/test_tool_registry.py + tests/test_tool_wiring.py が parity を機械検証(2026-05-30: 15 passed)

# 対象
services/brain/src/tool_schemas/(9)↔ tool_dispatch.py(TOOL_HANDLERS)↔ tool_executor.py ↔ tool_handlers_*(9)。

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bnd-tool-integrity.md, LEDGER 23 行目)
# 重点
- まず該当テストを再実行(PYTHONPATH=services/brain/src:services/backend .venv/bin/python -m pytest tests/test_tool_registry.py tests/test_tool_wiring.py)
  → 緑なら parity は維持されている前提で de-bloat に集中
- validate_tool_call の coverage 漏れ、query_tool_names の rate-limit bypass の妥当性、orphan tool(schema あり handler 無し/逆)
- dead: どこからも呼ばれない schema フィールド、未使用 feature flag 分岐
# 注: 前回 58=58 一致確認済。新規バグ狩りより回帰確認が主。
```

---

## 24. bnd-config-env(group: boundary)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 24/30「bnd-config-env」(横断契約)。主目的は整合 + dead 設定削除。

# 先に読む
- env.example、infra/docker-compose.yml、CLAUDE.md の Service Ports / profiles 表

# 対象
env.example ↔ 各サービス config.py / os.getenv ↔ infra/docker-compose*.yml(environment / profiles / HEMS_PORT_*)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bnd-config-env.md, LEDGER 24 行目)
# 重点
- 検証手順: env.example の key 集合と `grep -rn 'os.getenv\|os.environ' services/` の key 集合を diff
- dead: env.example に在るが未使用(declared-but-unused)→ 削除候補。コードで使うが env.example 未記載
  (前回 orphan: AUTOMATION_ENGINE_ENABLED 未記載)→ 追記候補
- port/profile 不一致、secret 既定値、openclaw/localcraw が ../../localcraw(repo 外)である旨の整合
```

---

## 25. bnd-data-schema(group: boundary)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 25/30「bnd-data-schema」(横断契約)。

# 先に読む
- services/backend/CLAUDE.md、docs/IMPLEMENTATION_MAP.md §5

# 対象
backend models.py(Task/User/VoiceEvent/SystemStats/ShoppingItem/PurchaseHistory/Device)
+ brain event_store/models.py(raw_events/llm_decisions/hourly_aggregates)
+ brain stores(schedule_store/scene_store/timeline_store/task_store 相当)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-bnd-data-schema.md, LEDGER 25 行目)
# 重点
- SQLite↔PG 互換(schema 名前空間 / JSONB / TZDateTime)、730d retention の実装有無(#7 と相互参照)
- SOMS 禁止項: wallet 形状フィールド(balance/credits/xp/multiplier/demurrage/funding_pool)が混入していないか grep で確証
- dead: 未使用カラム、未populate な state(ShoppingState)、SOMS drift
```

---

## 26. periphery-character-auth(group: periphery)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 26/30「periphery-character-auth」。主目的は dead-code 削除 + injection 面。

# 対象
validate_character.py(top-level), config/characters/*.yaml(11 個), config/character.yaml.example
+ 上位 hems/ ディレクトリ(hems/validate_character.py, hems/bridge_auth.py, hems/services/brain/src/character_loader.py, hems/config/)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-periphery-character-auth.md, LEDGER 26 行目)
# 重点(第一タスク = hems/ の dead duplicate 確証 → 削除)
- hems/ は別途検証で `import hems`/`from hems` 参照ゼロ(dead duplicate 疑い)。本セッションで
  `grep -rn 'import hems\|from hems' --include='*.py' .`(./hems 自身を除外)で再確認 → ゼロなら `git rm -r hems/` → make lint + pytest 緑。
  ※ hems/validate_character.py は top-level 版より古い(voisona ロジック欠落)。canonical は top-level。
- doc 乖離: CLAUDE.md は character テンプレート 6 個と記すが実体 11 個 → CLAUDE.md / docs を訂正(doc のみ)
- security: validate_character.py が YAML 由来の LLM injection を弾けるか、bridge_auth(no-op stub)の扱い
# 到達点
hems/ 削除は低リスク実装(挙動不変)。テンプレ数の doc 訂正も低リスク。validate ロジック強化は提案。
```

---

## 27. periphery-infra-build(group: periphery)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 27/30「periphery-infra-build」。主目的は build 健全性 + dead 設定削除。

# 対象
infra/docker-compose.yml(+ .gpu.yml / .edge-mock.yml), 全 Dockerfile(各 service + infra/base),
Makefile, pyproject.toml, requirements*.txt, infra/scripts/gpu_setup.py(+他 util), .hadolint.yaml
+ テスト戦略: tests/ 直下の conftest, tests/security/(4), tests/integration/(1), pytest marker / coverage 設定

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-periphery-infra-build.md, LEDGER 27 行目)
# 重点
- supply-chain: requirements ピン留め、Dockerfile の base 共有(hems-base:py3.11)整合、hadolint 警告
- dead: 未使用 profile / service 定義、空 dir(services/brain/src/data/ は実在する空 dir → 削除検討)、
  data-bridge(README のみ scaffold)の扱い
- test 戦略: marker(not integration/e2e/benchmark)、conftest fixture の重複、coverage 閾値
- 正式ゲート確認: `make lint` と `PYTHONPATH=services/brain/src:services/backend pytest tests/ services/brain/tests/ -m "not integration and not e2e and not benchmark"`
```

---

## 28. infra-runtime-fixtures(group: periphery)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 28/30「infra-runtime-fixtures」。主目的は de-bloat。
(プランの旧 29 セッションから漏れていたライブコード。無主だった infra/ の実行 py)

# 対象
infra/mock_llm/main.py(OpenAI 互換 mock FastAPI, brain がローカルテストで使用),
infra/virtual_edge/src/(device.py, main.py, swarm_hub.py, swarm_leaf.py, swarm_transport.py — MQTT device simulator),
infra/eval/(eval_models.py, eval_report.py — LLM eval harness)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-infra-runtime-fixtures.md, LEDGER 28 行目)
# 重点
- これらは fixture/harness だが実行コード。dead(誰も使わない eval/sim 分岐)、mock_llm の API 契約が
  本物の LLM client と整合しているか(テストの信頼性に直結)、virtual_edge の swarm_* が SOMS legacy の残骸でないか
- dup: swarm_transport / swarm_leaf のコピペ、mock 応答生成の重複
```

---

## 29. periphery-edge-firmware(group: periphery)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 29/30「periphery-edge-firmware」。主目的は dead/scaffold 判定 + de-bloat。
(組込ファーム。Python/MicroPython + C/ino。コア services とは別系統 — 別スキル領域として扱う)

# 対象(edge/)
edge/lib/(drivers 7, swarm 7, 他 3), edge/office/(sensor-02, sensor-node, unified-node),
edge/swarm/(hub-node, leaf-espnow, leaf-uart), edge/test-edge/camera-node, edge/tools/(17)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-periphery-edge-firmware.md, LEDGER 29 行目)
# 重点
- これらが現役配備か、実験/scaffold の残骸か(MQTT topic prefix office/ を使う edge が perception と整合するか)
- dead: 重複した driver、test-edge の使い捨てコード、tools/ の一度きりスクリプト
- 安全側: 実機ファームは挙動検証が困難 → 低リスク実装は「明白な dead ファイル削除」に限定、ロジック変更は提案のみ
```

---

## 30. periphery-mobile-kotlin(group: periphery)

```
あなたは HEMS のコードレビュー担当。クリーンセッション 30/30「periphery-mobile-kotlin」。主目的は重複プロジェクト判定 + dead 削除。
(Android/Kotlin。Python/TS コアと別トラック)

# 対象
services/mobile-android/(49 追跡ファイル, 32 .kt), apps/healthconnect-companion/(8 .kt)

# レンズ / 到達点 / 出力 — 共通(notes=REVIEW-periphery-mobile-kotlin.md, LEDGER 30 行目)
# 重点(第一タスク = 2 プロジェクトの関係判定)
- mobile-android と healthconnect-companion が並存。どちらが現役/意図された版か、片方が dead duplicate か判定。
  backend の /mobile router(tests/test_backend_mobile_router.py)とどちらが繋がるかで現役を特定。
- dead: 使われない Activity/ViewModel、Gradle の死んだ依存、build 生成物の誤追跡(.gradle/ build/ が git 管理下でないか)
- 到達点: 現役判定は調査成果。dead project 確定なら削除は提案(影響大のため親承認必須)。
```

---

## 全セッション共通の正式ゲート(低リスク実装時)

```bash
make lint
PYTHONPATH=services/brain/src:services/backend .venv/bin/python -m pytest tests/ services/brain/tests/ \
  -v --tb=short -m "not integration and not e2e and not benchmark"
# frontend セッションは pnpm tsc + pnpm build(services/frontend/)
```

サンドボックス内広域 pytest は aiosqlite ハングの恐れがあり**参考値**。正式判定は通常環境の結果のみ採用
(前回 baseline: `1257 passed, 2 skipped, 19 deselected`)。各セッションは自スコープの関連テストに絞って緑を確認する。
