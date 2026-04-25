# Wiring Gap 01 — GAS Feature Expansion

GAS bridge (Calendar / Tasks / Gmail / Sheets / Drive) の publish は揃っているが、LLM 判断に届いているのは Calendar upcoming と Tasks overdue 程度。Sheets / Drive / Gmail recent / free slot 時刻・会議前行動などがブラインドスポットになっている。

対象: `services/gas-bridge/`, `services/brain/src/world_model/`, `services/brain/src/rule_engine.py`, `services/brain/src/tool_registry.py`, `services/brain/src/main.py`

## 現状 (file:line)

| Topic | Publish 側 | Brain での扱い | ギャップ |
|---|---|---|---|
| `hems/gas/calendar/upcoming` | `gas-bridge/src/data_poller.py` | `world_model.py:910` 付近で `gs.upcoming` 格納。`_get_digital_context` (line 1787-1794) で LLM に表示 | OK (基本) / **MTG 前準備 rule なし** |
| `hems/gas/calendar/free_slots` | 同上 | `world_model.py:907-908` で `gs.free_slots` 格納。`_get_digital_context` (1807) で **2h+ の個数のみ**表示 | **時刻が LLM に届かない** |
| `hems/gas/tasks/all`, `/due_today` | 同上 | `rule_engine.py:517-530` で overdue 単発 alert | **24h 以上滞留の escalation なし** |
| `hems/gas/gmail/summary` | 同上 | `_get_digital_context` に unread 件数のみ | 個別メールの重要度判断不可 |
| `hems/gas/gmail/recent` | 同上 | WorldModel 格納 **のみ**、context 非登場、tool なし | **LLM から完全不可視** |
| `hems/gas/sheets/{name}` | 同上 | `world_model.py:960` 格納。`rule_engine.py:610` に "threshold monitoring" コメントだけで実装無 | **Dead code / LLM 不可視** |
| `hems/gas/drive/recent` | 同上 | `world_model.py:971` 格納。`rule_engine.py:590` の weekly 通知のみ | **LLM 不可視** |
| GAS 由来の task 作成 | Brain → backend | `event_store` に GAS `cause` を残さない | **因果追跡不能** |

## Wave 計画

### P0 — 既存データの露出 (差分: 小、効果: 大)

1. **Free slot の時刻露出**
   - `world_model/world_model.py:1807` 付近の serializer を "count" → "count + 先頭 3 スロットの HH:MM-HH:MM" に変更
   - 確認: `LLM activity log` に `free: 09:00-11:00, 13:30-15:00` 等が載る

2. **Gmail recent の要約を context に追加**
   - `_get_digital_context` (`world_model/world_model.py:1743-1848`) に `gmail.recent` の `[sender] subject` を最大 5 件列挙
   - 個人情報量の上限: subject は 60 文字で切る

3. **Sheets / Drive 表層化**
   - 各 source の "最終更新時刻 + 行数" を context に 1 行ずつ追加（full content ではなく health indicator）
   - full content は tool 経由で後段 P1 で取る

4. **GAS イベントの event_store 記録**
   - `event_store/writer.py` に `record_world_event` を拡張した `record_gas_event(topic, subject_ref, payload_digest)` を追加
   - `main.py:306` の GAS topic 分岐で呼び出し
   - task 作成時の `llm_decisions` 行に `cause_event_id` を持たせ、"なぜ作られたか" を辿れる

### P1 — 行動連鎖 Rule + LLM Tool

5. **Meeting prep rule**
   - `rule_engine.py` に `_evaluate_meeting_prep()` 追加
   - 条件: 次の `gs.upcoming` event が 30min 以内 → `speak("もうすぐ打ち合わせです")` + 静音推奨 + HA 照明調整 (brightness=70%)
   - cooldown: 同一 event id につき 1 回

6. **Overdue escalation**
   - `rule_engine.py:517` の既存 rule を拡張:
     - 初回発火: 情報 speak
     - 24h 経過して残存: priority 昇格 + 朝 briefing に織り込む
     - 72h 経過: 強制削除候補として提示

7. **新規 LLM tool 3 本** (`tool_registry.py` に登録、handler は `tool_executor.py` か GAS bridge proxy)
   - `gas_query_free_slots(date_range_hours: int) -> list[{start, end, duration_min}]`
   - `gas_query_gmail(query: str, max: int = 5) -> list[thread_digest]` — subject/sender/snippet だけ返す
   - `gas_query_sheet(sheet_name: str, max_rows: int = 20) -> rows`
   - Safety: すべて read-only。書き込み系は今回追加しない

### P2 — 後続

8. **Drive 新規 file → 自動 knowledge ingest**
   - drive_recent で検知した `.md / .pdf` を `knowledge-bridge` に forward する導線（別 PR）
9. **Sheets 閾値監視 rule**
   - `rule_engine.py:610` のスタブを完成。`config/gas_sheet_watchers.yaml` で `sheet_name / col / threshold / action` を宣言的に設定
10. **Gmail 重要度スコア**
    - 差出人 + subject の LLM 軽評価で urgent 判定 → speak

## Acceptance Criteria

- [ ] P0: `docker logs -f hems-brain` で LLM context 内に `free_slots / gmail_recent / sheets / drive` が観測可能
- [ ] P0: `llm_decisions` 行を SQLite で開き `cause_event_id` に GAS topic 由来の FK が入っている
- [ ] P1: 次のカレンダー予定を 25 分前に手動挿入 → 30 分前 rule が 1 回だけ発火する
- [ ] P1: `gas_query_free_slots(24)` を LLM が ReAct で選べる（tool_registry に並ぶ）
- [ ] 既存 GAS 呼び出し数が P0 で増えない (quota ~1100 calls/day ターゲット維持)

## Risks

- **LLM context 肥大**: P0 で Gmail recent 5 件 + sheets/drive 列挙すると prompt が膨らむ。`_get_digital_context` の文字数上限を維持するため、各 section に `max_chars` を設定する
- **GAS quota**: P2 の Drive forward 以外は polling cadence を変えないので安全。20,000/day の内 1,100 消費 → 十分余裕
- **event_store 肥大**: GAS event 記録はサンプリング（同一 payload digest なら 5min 以内はスキップ）でレート制御

## 実装順序

P0 の 4 項目 → 動作確認 → P1 の 3 項目 → P2。P0 だけでも現状の "半分 cargo cult" 状態は解消する。
