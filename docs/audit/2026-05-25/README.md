# サービス単位 実装監査 — 2026-05-25(進捗 ledger)

`refactor/upstream-port` ブランチの全 Python サービスを **命名 / スコープ / 可読性 / doc 乖離** の4軸で監査する。
本パスは **監査 + doc 乖離是正のみ**(コード無改変)。命名/スコープ/可読性の所見は per-service ファイルに
「後続リファクタが着手できる」粒度で記録する。

メタ計画: `~/.claude/plans/goal-root-clear-sparkling-coral.md`

## 中核原則

**1 ledger unit = 1 監査ファイル = 1 commit。** /clear 窓は複数の小 unit をまとめてよいが、出力ファイルと
commit は unit 単位で確定する。

## 再入プロトコル(/clear 後はこれで始める)

1. `cd /home/sin/code/claude/hems`
2. `git log --oneline -5` で最後の unit を確認
3. 本 ledger の status `pending` 先頭 unit を選ぶ
4. その service dir へ cd → 該当 canonical doc を Read
5. per-unit 手順を実行 → 該当行を `done <sha>` に更新 → commit → /clear 判断

## 進捗

| # | unit | 出力ファイル | status | commit |
|---|---|---|---|---|
| 1 | brain-core-loop | `brain-core-loop.md` | done | (このコミット) |
| 2 | brain-world-model | `brain-world-model.md` | done | (このコミット) |
| 3 | brain-rules-automation | `brain-rules-automation.md` | done | (このコミット) |
| 4 | brain-llm-tools-character | `brain-llm-tools-character.md` | done | (このコミット) |
| 5 | backend | `backend.md` | done | (このコミット) |
| 6 | perception | `perception.md` | done | (このコミット) |
| 7 | voice (incl. stt) | `voice.md` | done | (このコミット) |
| 8 | biometric-bridge | `biometric-bridge.md` | done | (このコミット) |
| 9 | knowledge-bridge | `knowledge-bridge.md` | done | (このコミット) |
| 10 | obsidian-bridge | `obsidian-bridge.md` | done | (このコミット) |
| 11 | gas-bridge | `gas-bridge.md` | done | (このコミット) |
| 12 | ha-bridge | `ha-bridge.md` | done | (このコミット) |
| 13 | switchbot-bridge | `switchbot-bridge.md` | done | (このコミット) |
| 14 | tapo-bridge | `tapo-bridge.md` | done | (このコミット) |
| 15 | weather-bridge | `weather-bridge.md` | done | (このコミット) |
| 16 | news-bridge | `news-bridge.md` | done | (このコミット) |
| — | SUMMARY + openclaw/data-bridge 調査 + docs/README index | `SUMMARY.md` | done | (このコミット) |

**特殊ケース(独立 unit にしない、SUMMARY で処理):**
- `openclaw` — service dir 無し(external "legacy localcraw" build context)。doc-divergence のみ確認。
- `data-bridge` — README のみの scaffold。監査スキップ(N/A)。

## 完了済 unit のサマリ

- **weather / news bridges**: 両者とも doc 乖離なし・最もクリーン(provider 抽象 + poller + summarizer の分割が明快、find-replace/TODO 無し)。topic/route/tool は canonical と完全一致。
- **W8 bridges (gas / ha / switchbot / tapo)**: いずれも P0/P1 無し・構造健全。doc 乖離: gas は Brain tools 行欠落(3 tools 追加)、ha は `get_entity_status` 欠落(+§8 ✗→✓)、tapo は `get_power_consumption` 欠落、**switchbot は device state が実は `hems/home/*`(HA 互換)なのに doc が `hems/switchbot/*` と誤記**(§SwitchBot + §4.0 修正)。
- **W7 bridges (biometric / knowledge / obsidian)**: いずれも P0/P1 無し・構造健全(plugin provider / loader / TF-IDF index)。doc 乖離は全て「extended tool 欠落」の同型: biometric +get_biometric_trend/get_sleep_history、knowledge +get_recent_knowledge_changes、obsidian +list_note_tags。各 CLAUDE-bridges.md 節を補完。topic/route/safety/writeback は canonical と一致。bridge は契約 grep 検証 + 構造スキャン中心(行レベル精査は後続)。
- **voice (incl. stt)**: P0/P1 無し。クリーン(TTS/STT とも ABC+factory plugin 構成)。doc 乖離 2 件: voice/CLAUDE.md に `aivoice` 欠落(TTS 4→5)、root CLAUDE.md の 5 番目が `style-bert-vits2`(ゴースト誤記)→ `aivoice` に訂正。STT 3 provider は一致。
- **perception**: P0/P1 無し。**最もクリーンなユニットの一つ**(detector/activity_tracker/vlm_analyzer/vlm_scheduler/camera_manager の責務分割が良好)。doc 乖離 1 件: perception/CLAUDE.md の brain tool が 2→7(list_scene_objects/get_scene_timeline/list_cameras/get_vlm_status/get_activity_history 欠落)を修正。MQTT topic は canonical と完全一致。
- **backend**: P0 ブロッカー無し。P1(security)= `verify_api_key` が no-op で全 main ルーターは実質無認証(LAN-trusted 設計だが `_auth` 装飾が誤認を招く。mobile は実認証あり)。P2 = lifespan の手製 ALTER TABLE マイグレーション(例外握り潰し)。doc 乖離 2 件(§8 の 4 endpoint がツール化済、backend/CLAUDE.md ShoppingState)を修正。root CLAUDE.md の models 列挙(6/23)は SUMMARY 向け。
- **brain-llm-tools-character**: P0 ブロッカー無し。registry↔dispatch は §3.5 で **58=58 完全一致**。doc 乖離は §3 表が 9 ツール未掲載(`gas_query_*`/`list_note_tags`/`get_biometric_trend`/`list_cameras` 等)→ 補完。unit 1 の sanitizer cross-check を解決(ツール実在、doc 不完全が真因)。P1 = `AutomationEngine._llm_review` の戻り値型バグ確証(LLMResponse を str 扱い → llm_review automation が無音 skip)。annotator/voice_capsule は構造スキャンのみ(行精査は後続)。
- **brain-rules-automation**: P0 ブロッカー無し。負債は (1) rules ミキシンの namespace 結合(`_rule_engine.X` 準循環、unit 2 と同型)、(2) `RuleEngine.evaluate` 490行 god-method(環境/PC rule の抽出積み残し)、(3) `AutomationEngine._llm_review` が llm_client.chat 戻りを str 扱い = 潜在バグ(unit 4 で署名照合)。doc 乖離 3 件(§7.3 weather_alert_announce 欠落、§6/§6.6 の rules/ 分割未反映)を修正。device_dispatcher は unit 4 へ繰延。
- **brain-world-model**: P0 ブロッカー無し。最大の負債は (1) world_model mixin の namespace 結合(`_world_model.time`/`logger`/定数を facade 経由参照する準循環 import)、(2) `context_builder` の 3 大ビルダー(`_get_physical_context` 257行)。doc 乖離 5 件(routing/reducer の mixin 分割未反映、ShoppingState dead state、pc/processes/top は実は統合済)を IMPLEMENTATION_MAP §4.3/§4.4/§4.6/§5/§5.1 で修正。コメント内 `_world_model.time` find-replace 事故 4 件は記録のみ(後続コードパス)。
- **brain-core-loop**: P0 ブロッカー無し。最大の負債は 2 大 god-function(`cognitive_cycle` ~470行 / `_process_mqtt` ~240行)と dead code `_build_character_section`(~70行)。doc 乖離 5 件(startup 配線の 2 段化 + Timeline/EventAutomation/PersonaRewriter の起動条件)を IMPLEMENTATION_MAP §2 + brain/CLAUDE.md で修正適用。sanitizer 許可リストの未文書化ツールは unit 4 で要 cross-check。
