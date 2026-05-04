# 朝ブリーフィング — ブロッカー監査とリファクタ計画

2026-05-03 監査。`wake_up` イベント駆動の朝ブリーフィングパイプライン (BootLoad pre-synth → SunriseAlarm → EventAutomation → morning_greeting / news_briefing / weather_report → speak) のブロッカーと技術的負債を、コード突合のうえで列挙する。

対象: `services/brain/src/{main.py, event_automation.py, boot_load_manager.py, sunrise_alarm.py, schedule_learner.py, persona_rewriter.py, world_model/world_model.py, tool_executor.py}`, `services/news-bridge/src/main.py`.

---

## 0. 結論

> **2026-05-03 更新**: Wave 1 + 追加発見の P0 (`get_wake_time` の翌日固定) を実装済み。`schedule_learner.get_wake_time` は次回起床 (本日/翌日いずれか先) を返すよう修正、EventAutomation を常時初期化、scheduled wake_up fallback を `cognitive_cycle` に追加、weather_report に音声フォールバック、BootLoad は briefing 生成成功時点で READY (audio は best-effort 部分採用)、camera 検出窓を env 化。`tests/test_schedule_learner.py` を新ロジックに合わせて更新 (22 pass)。
>
> **2026-05-03 (Wave 2 完了)**: BootLoad cache を `BOOT_LOAD_CACHE_DIR/{date}.json` に永続化 (起動時復元 + 別日 GC + reset 時削除)、SunriseAlarm を DeviceDispatcher 経由 (registry 未登録時は直接 MQTT publish にフォールバック)、paho `info.rc` の検証 + 1 回 retry、PersonaRewriter ゲートを `tool_executor._handle_speak` に集約 (`_run_rule_actions` の二重 rewrite バグも解消)。スモークテストで全パス確認、ログフォーマットを loguru の `{}` 形式に統一。
>
> **2026-05-03 (Wave 3 完了)**: news_briefing が cache 経過時間 > `NEWS_REFRESH_STALE_HOURS` で `/api/news/refresh` を発火 (BootLoad-friendly な暗黙排他)、`ScheduleLearner.get_wake_confidence` 導入で `BootLoadManager.should_start` の窓を `×{1.0, 1.5, 2.0}` 動的化 (履歴浅い時期に取りこぼさない)、3 統合テストファイル (`test_boot_load.py`/`test_sunrise_alarm.py`/`test_event_automation.py`) + 確信度テスト追加で計 67 件 / 全 pass。Wave 1〜3 全完了。

**致命的ブロッカーは1件 (P0-1)、信頼性に関わる中位課題が4件、軽微な技術的負債が複数。** 正常系 (biometric + news bridge + ha/switchbot 全部入り) はおおむね動くが、

- **NEWS_BRIDGE_URL 未設定 = 朝ブリーフィング全停止** (silent)
- **biometric / camera どちらも無いと wake_up が永久に発火しない** (時間ベースの fallback trigger 不在)
- **boot-load が途中失敗すると IDLE に戻り**、wake_up 時には text TTS にフォールバック (これは想定動作だが、partial cache の再利用がない)
- **weather_report は last_update==0 で silent skip** (DEBUG ログのみ)

特に P0-1 は `.env.example` の `NEWS_BRIDGE_URL` がコメントアウトされている (= 起動しただけでは不通) ため、デフォルト構成で機能しない。

---

## 1. 検証済みの実装状況

### 1.1 wake_up トリガ (main.py:369-396)

実装ソース:
- **biometric sleep end**: `hems/personal/biometrics/{provider}/sleep` の `sleep_end_ts > 0` (`main.py:373-378`)
- **camera 人物検出 (5:00-10:00 のみ)**: `office/{zone}/camera/{cam}/status` の `person_count > 0` (`main.py:387-392`)

両者ともに `self.event_automation.trigger("wake_up")` を `asyncio.run_coroutine_threadsafe` で投入。`if self.event_automation:` ガードあり (line 371) のため None 時は静かに drop。

**ブロッカー**: scheduled fallback (時刻ベース) なし。biometric も camera も無い構成では wake_up が発火しない。

### 1.2 EventAutomation 初期化ゲート (main.py:1538-1549)

```python
if NEWS_ENABLED:                             # NEWS_BRIDGE_URL 未設定 → False
    self.event_automation = EventAutomation(...)
    self.event_automation.set_session(session)
    logger.info(f"News integration enabled (bridge={NEWS_BRIDGE_URL})")
else:
    logger.info("News integration disabled (NEWS_BRIDGE_URL not set)")
```

**問題**: `NEWS_ENABLED` で gate しているが、`EventAutomation` は `morning_greeting` / `weather_report` / `arrival` / `departure` / `scheduled` も担当する。`NEWS_BRIDGE_URL` が空だとこれら全てが silent に無効化される。

**影響**: `env.example` の現状 `# NEWS_BRIDGE_URL=http://news-bridge:8000` (コメントアウト) で起動した場合、朝ブリーフィングは丸ごと不動。INFO ログ "News integration disabled" のみ。

### 1.3 BootLoadManager (boot_load_manager.py)

- `should_start()`: `schedule_learner.get_wake_time()` が必要。`HA / biometric / switchbot` のどれかが必要。45min 窓 (BOOT_LOAD_WINDOW_SEC) 内で1日1回。
- `_run()`: news 取得 → schedule 生成 → heavy LLM ブリーフィング → TTS pre-synth → mobile capsule。例外時は `IDLE` に rollback (`is_complete=False` のまま)。
- `is_ready` プロパティ: `READY` かつ `is_complete=True` でのみ True。

**動作**:
- 部分成功時の partial cache 採用なし: news_chunks は埋まったが TTS が落ちた場合、briefing_chunks は使えるはずだが `is_complete=False` なので `event_automation.boot_load_manager.is_ready` が False → wake_up 時には TTS at-wake-time path。
- 永続化なし (in-memory のみ): brain restart で全消失。
- 6:00 wake / 5:30 boot-load 開始の場合、heavy LLM 生成 + N チャンク TTS で 30s〜数分かかるため、wake_up が間に合わずに来た場合 `is_complete=False` → 通常 path 落ち。これは設計通りだが、観測ログは debug レベル。

### 1.4 SunriseAlarm (sunrise_alarm.py)

`SUNRISE_ALARM_DEVICE` env で gate。Z2M 経由で `zigbee2mqtt/{device}/set` に直接 publish。`should_start` も schedule_learner に依存。

**技術的負債**:
- `device_ref` は `zigbee.` プレフィックスを strip して Z2M friendly name 想定。Device Registry の `vendor_ref` 規約とずれている (Device Registry では `zigbee.{friendly_name}` で管理)。
- MQTT publish 結果の確認なし。Z2M が落ちていても気付かない。
- `wake_up` 検出時の `stop()` は良い実装 (`main.py:399-400`)。

### 1.5 アクション実装 (event_automation.py)

| アクション | 実装位置 | データソース | フォールバック |
|---|---|---|---|
| morning_greeting | 235-294 | LLM 生成 (世界観 context 流し込み) | LLM 失敗時 hardcoded greeting (line 281-294) |
| news_briefing | 180-233 | REST `news-bridge/api/news/latest` → `world_model.news_state.daily_chunks` | NEWS_BRIDGE_URL 未設定時 silent skip |
| weather_report | 394-434 | `world_model.physical.weather` | **`last_update==0` で silent skip** ← 問題 |

**boot_load 経路の優先**: `event_automation.py:94-101` で `boot_load_manager.is_ready` なら cache 再生 + `boot_load_used=True` set → 同名 action は skip (line 114)。

### 1.6 check_scheduled (main.py:1678-1683)

`check_scheduled()` は cognitive_cycle 末尾で呼ばれている (確認済み)。「呼ばれていない」とした初期監査は誤り。

### 1.7 PersonaRewriter ゲート (main.py:521-537, tool_executor.py:368-444)

`tool_executor._handle_speak()` 内で `persona_rewriter.rewrite()` 呼び出し。低電力モード/VLM swap 中は skip (`main.py:525-530` の rewrite_active 条件)。wake_up は通常時刻なので影響軽微だが、event_automation 経路 (action 実行) では PersonaRewriter ゲートを通らずに `tool_executor.execute("speak")` を直叩きしているため、ここの整合は別途確認要。

### 1.8 news-bridge 日次サマリ (news-bridge/src/main.py:104-129)

`NEWS_DAILY_HOUR=7 / NEWS_DAILY_MINUTE=30` 固定。startup 時にも 1 回生成。wake_up 時刻と decouple されているため:
- 6:00 起床 → 既に startup 時点のサマリを使う (前夜 ~9 時間古い可能性)
- 8:00 起床 → 7:30 の最新サマリを使う (OK)
- 7:00 起床 → BootLoad が 6:15 に開始 → news-bridge `/api/news/refresh` を強制呼出 (boot_load_manager `_fetch_news`) で同期取れる

→ BootLoad 経路では実用上問題ないが、BootLoad 不可な構成 (HA/switchbot/biometric なし) では古いサマリが流れる。

---

## 2. ブロッカーと技術的負債

### P0 — 致命的

#### P0-1. EventAutomation が NEWS_BRIDGE_URL に gated されている
- 位置: `main.py:1538-1549`
- 影響: `.env` で `NEWS_BRIDGE_URL` を設定しないと morning_greeting / weather_report / arrival / departure / scheduled すべて発動しない
- 期待: EventAutomation は常時初期化、`news_briefing` action だけ NEWS_ENABLED チェックで skip
- 工数: 15min

### P1 — 信頼性

#### P1-1. wake_up の時間ベース fallback trigger 不在
- 位置: `main.py:369-396`
- 影響: biometric も camera も無い構成 (HA や switchbot のみ等) で wake_up が永久に発火しない。BootLoad が READY になっても再生されない
- 期待: cognitive_cycle 内で `schedule_learner.get_wake_time()` ± 既定 (例: 5min) を超えた瞬間に wake_up を 1 回発火 (1日1回ガード)
- 工数: 1-2h

#### P1-2. weather_report の silent skip
- 位置: `event_automation.py:397-399`
- 影響: weather-bridge 起動直後など `last_update==0` の状態で起床すると、briefing から天気が抜け、ログも DEBUG のみ
- 期待: WARNING ログ + 「天気情報はまだ準備できていません」音声フォールバック (1-2チャンク程度に抑える)
- 工数: 30min

#### P1-3. BootLoad の partial cache 不採用
- 位置: `boot_load_manager.py:171-213`
- 影響: TTS pre-synth が 1チャンクでも失敗すると `is_complete=False` のまま → wake_up 時に boot_load 不採用 → TTS at wake time にフォールバック (体感数秒〜数十秒の遅延)
- 期待: news / briefing 生成成功時点で `is_complete=True` を立てる。`audio_urls` が partial の場合は audio 入手済みチャンクは VoiceEvent 注入、未合成チャンクは speak tool 経由で TTS at wake time。`event_automation.py:310-330` 側にも mixed mode 対応必要
- 工数: 2-3h

#### P1-4. BootLoad cache の永続化なし
- 位置: `boot_load_manager.py` (in-memory only)
- 影響: brain restart (deploy / OOM / crash) で cache 消失。再生成に間に合わない時間で起床すると沈黙
- 期待: `/app/data/boot_load_cache_{date}.json` に briefing_chunks + audio_urls を保存。restart 時 `should_start` 前に load
- 工数: 2h

### P2 — 中位

#### P2-1. SunriseAlarm の vendor_ref 命名ずれ
- 位置: `sunrise_alarm.py` (`zigbee.` strip 処理)
- 影響: Device Registry 経由 (`device_dispatcher.dispatch`) ではなく直接 MQTT publish しているので、Device Registry に未登録のデバイス参照でもとりあえず動いてしまう ↔ Registry 上での状態追跡から外れる
- 期待: `device_dispatcher.dispatch(vendor="zigbee", action="set_brightness", ...)` 経由にして Registry を経由
- 工数: 1-2h

#### P2-2. SunriseAlarm の MQTT publish 失敗が観測不能
- 位置: `sunrise_alarm.py:_ramp()`
- 影響: Z2M 落ち / device 反応無しを検知できない
- 期待: publish 後 `zigbee2mqtt/{device}` の retain 値が想定通り変化したかを 5s 以内に確認、変化なしなら WARNING + retry 1回
- 工数: 2h

#### P2-3. camera wake_up の時刻窓 (5-10am) ハードコード
- 位置: `main.py:387` (`if 5 <= hour < 10`)
- 影響: 二度寝・遅起き (10:01 以降) で wake_up が永久に発火しない構成あり
- 期待: env (`WAKE_DETECT_HOUR_START=5`, `WAKE_DETECT_HOUR_END=11`) もしくは ScheduleLearner の予測時刻 ± 4h
- 工数: 30min

#### P2-4. EventAutomation 経路での PersonaRewriter 抜け
- 位置: `event_automation.py:_action_morning_greeting` 等
- 影響: `tool_executor.execute("speak", ...)` を呼ぶので tool_executor 内 PersonaRewriter は適用されるが、`_run_rule_actions` の rewrite_active gate (`main.py:525-530`) を通らないので低電力時の挙動が `_run_rule_actions` 経路と非対称
- 期待: tool_executor 一箇所に gate を統一 (`main.py:521-537` の rewrite_active 条件を tool_executor 内に持って行く)
- 工数: 1h

### P3 — 軽微

#### P3-1. news-bridge daily 時刻が wake と decouple
- 位置: `news-bridge/src/main.py:104-129`
- 影響: BootLoad 不在構成 (HA/switchbot/biometric なし) で前夜の startup サマリが流れる
- 期待: brain → news-bridge の `/api/news/refresh` を wake_up trigger 直後に呼ぶ (ただし BootLoad 経路と二重で呼ばないよう排他制御)
- 工数: 1h

#### P3-2. BootLoad 窓 (45min) が一律
- 位置: `boot_load_manager.py:110-132`
- 影響: ScheduleLearner 履歴が浅い時期 (運用初期 2 週間以内) は予測のばらつきが大きく、45min 窓では取り逃す可能性
- 期待: schedule_learner.get_wake_time_confidence() を返すようにし、低信頼時は 90min 窓に拡大
- 工数: 2-3h (ScheduleLearner 側の確信度導出 + window 適応)

#### P3-3. BootLoad / SunriseAlarm のテストカバレッジ
- 位置: `tests/` 以下に該当テスト無し
- 影響: 今回の P0/P1 修正のリグレッションを補足できない
- 期待: BootLoadManager の状態遷移 + EventAutomation の boot_load_used 分岐の単体テスト
- 工数: 3-4h

---

## 3. リファクタ計画 (Wave)

優先度と互換性で 3 Wave に分割。Wave 1 単独で「デフォルト構成で朝ブリーフィングが鳴る」状態を達成する。

### Wave 1 — 朝ブリーフィングの最低保証 (P0 + 重要 P1)

目的: `.env` 最低限 (HA or biometric or switchbot のいずれか) で朝ブリーフィングが必ず鳴る。

| # | 項目 | ファイル | 工数 |
|---|---|---|---|
| 1.0 | **追加発見**: `schedule_learner.get_wake_time()` が常に翌日を返す (BootLoad/SunriseAlarm の `should_start` が永久に False) → 次回起床 (今日 or 翌日) を返すよう修正 ✅ | `schedule_learner.py:154-211`, `tests/test_schedule_learner.py` | 1h |
| 1.1 | EventAutomation 初期化を NEWS_ENABLED から外す。news_briefing action 内で NEWS_BRIDGE_URL gate ✅ | `main.py:1538-1549`, `event_automation.py:180-233` | 30m |
| 1.2 | wake_up scheduled trigger を cognitive_cycle に追加 (predicted wake_time 通過後 4h 以内・1日1回) ✅ | `main.py:cognitive_cycle`, `_scheduled_wake_fired_date` 追加 | 1h |
| 1.3 | weather_report の WARNING + テキストフォールバック ✅ | `event_automation.py:394-434` | 20m |
| 1.4 | BootLoad partial cache 採用: briefing 完成時点で `is_complete=True`、`_execute_boot_load_briefing` を mixed mode (audio injected / fallback speak()) に統一 ✅ | `boot_load_manager.py:_run`, `event_automation.py:_execute_boot_load_briefing` | 1h |
| 1.6 | 追加: camera wake_up 時刻窓を `WAKE_DETECT_HOUR_START / END` で env 化 (本来 Wave 2 だが軽微なため Wave 1 で実施) ✅ | `main.py:75-82, 387`, `env.example` | 15m |
| 1.5 | 単体テスト: EventAutomation の boot_load_used 分岐 + scheduled trigger | `tests/brain/test_event_automation.py` (新規) | 2h |

検証コマンド:
```bash
# news-bridge を落として朝ブリーフィングが鳴るかドライラン
NEWS_BRIDGE_URL="" docker compose up -d brain
mosquitto_pub -t hems/personal/biometrics/gadgetbridge/sleep \
  -m '{"sleep_end_ts": '$(date +%s)'}'
docker logs hems-brain | grep -E "wake_up|EventAutomation|morning_greeting"
# expected: morning_greeting + weather_report が走り、news_briefing は SKIP ログのみ
```

### Wave 2 — 信頼性 (P1-4 + P2)

目的: 再起動 / 中間障害に対する耐性。**2026-05-03 完了 (2.4 は W1 で先行)**。

| # | 項目 | ファイル | 工数 |
|---|---|---|---|
| 2.1 | BootLoad cache 永続化 (`BOOT_LOAD_CACHE_DIR/{date}.json`)、 起動時復元 + 別日 GC ✅ | `boot_load_manager.py:_persist_cache/_restore_from_disk/_gc_old_cache_files`, `env.example` | 2h |
| 2.2 | SunriseAlarm を `DeviceDispatcher` 経由に統一 (registry 未登録時は直接 MQTT publish にフォールバック) ✅ | `sunrise_alarm.py:_async_publish`, `main.py:614` | 2h |
| 2.3 | SunriseAlarm の publish 結果検証: paho の `info.rc` をチェックし non-zero なら 1s 後に 1 回 retry、失敗時 ERROR ✅ | `sunrise_alarm.py:_direct_publish` | 1h |
| 2.4 | camera wake_up 時刻窓を `WAKE_DETECT_HOUR_START/END` で env 化 ✅ (W1で実施) | `main.py:77-79, 388-396`, `env.example` | – |
| 2.5 | PersonaRewriter gate 一元化: `tool_executor._handle_speak` 内で low_power + VLM swap を判定。`_run_rule_actions` の二重 rewrite バグも解消 (`_skip_persona_rewrite=True` 内部 flag で opt-out) ✅ | `tool_executor.py:_handle_speak`, `main.py:_run_rule_actions` | 1h |

### Wave 3 — 品質向上 (P3)

**2026-05-03 完了**。

| # | 項目 | ファイル | 工数 |
|---|---|---|---|
| 3.1 | news_briefing で `daily_timestamp` 経過 > `NEWS_REFRESH_STALE_HOURS` (default 2h) のとき `/api/news/refresh` を呼ぶ。BootLoad pre-synth 直後は cache が新鮮なので自然に skip される (排他不要) ✅ | `event_automation.py:_action_news_briefing`, `env.example` | 1h |
| 3.2 | `ScheduleLearner.get_wake_confidence()` を追加 (high/medium/low: 履歴週数 + stdev で判定)。`BootLoadManager.should_start` が `BOOT_LOAD_WINDOW_SEC × {1.0, 1.5, 2.0}` で動的可変 ✅ | `schedule_learner.py:get_wake_confidence`, `boot_load_manager.py:_CONFIDENCE_MULTIPLIER` | 1.5h |
| 3.3 | 統合テスト 3 ファイル (`test_boot_load.py` 14件 / `test_sunrise_alarm.py` 9件 / `test_event_automation.py` 9件) + 確信度テスト 4件追加 ✅ | `tests/test_boot_load.py`, `tests/test_sunrise_alarm.py`, `tests/test_event_automation.py`, `tests/test_schedule_learner.py` | 3h |

---

## 4. 依存関係と並行性

```
Wave 1: 1.1 → 1.2, 1.3, 1.4 (並行) → 1.5
Wave 2: 2.1 (独立) | 2.2 → 2.3 | 2.4 (独立) | 2.5 (独立)
Wave 3: 3.1 (Wave 1.4 依存) | 3.2 (独立) | 3.3 (Wave 1, 2 依存)
```

Wave 1 完了で `.env` 設定不備による silent failure は解消。Wave 2 完了で運用中障害への耐性が立つ。Wave 3 は long-tail。

---

## 5. ドキュメント更新

完了時に同期するファイル:
- `docs/IMPLEMENTATION_MAP.md` — wake_up trigger 列に scheduled fallback、BootLoad cache 永続化を追記
- `CLAUDE.md` — 「### Brain Service」の Subsystems 配線で BootLoad / SunriseAlarm の前提条件 (HA/biometric/switchbot のいずれか) を明示
- `env.example` — `NEWS_BRIDGE_URL` のコメント解除推奨を注記、`WAKE_DETECT_HOUR_*` を追加

## 6. 既知の非対象

- AmbientSpeaker (5min 間隔の発話) は朝ブリーフィングと独立。本計画では触らない。
- TimelineGenerator (EDF + free-window) は内部状態のみで音声出力なし。本計画では触らない。
- AckLearner / mobile voice capsule は別系統 (P0 / P1 plan: `velvety-chasing-pebble`) で進行中。
