# Wiring Gap 04 — Sensor Utilization

> **CLOSED 2026-05-03**: 全項目が [`wiring-gap-06-data-flow-consolidation.md`](wiring-gap-06-data-flow-consolidation.md) に統合・解消済み (Wave 1 で weather alerts rule + EventAutomation action + frontend banner、Wave 4 で long-term sensor history)。

環境センサーの多くは `sensor_fusion.py` で受信・融合まで出来ているが、LLM context にも rule にも現れない「死蔵 channel」になっている。特に soil_moisture / VOC / native PM2.5 / pressure 絶対値 / illuminance は rule ゼロ。weather alerts は subscriber 不在。shopping MQTT は event_store に残らない。

対象: `services/brain/src/world_model/`, `services/brain/src/rule_engine.py`, `services/brain/src/event_store/writer.py`, `services/brain/src/main.py`, `services/weather-bridge/` (subscriber側は brain)

## 現状 (file:line)

| Channel / Topic | 収集 | rule | context 露出 | tool |
|---|---|---|---|---|
| `soil_moisture` | `sensor_fusion.py:29` 登録・fusion | ❌ | ❌ | ❌ |
| `voc` | `world_model.py:533` 格納 | ❌ | ❌ | ❌ |
| `pm25` (native) | `sensor_fusion.py:31` | HA binary のみ `rule_engine.py:1243` | ❌ | ❌ |
| `pressure` | `world_model.py:528` | 急降下のみ `rule_engine.py:271-280` | ❌ (zone context に出ない) | ❌ |
| `light / illuminance` | fusion OK | 無し (circadian 用途のみ) | ❌ | ❌ |
| `hems/weather/alerts` | weather-bridge publish | brain subscriber 無 | ❌ | ❌ |
| `hems/shopping/{added,updated,purchased}` | Backend publish | `main.py:302` で `added` のみ classifier に渡す | ❌ | 既存 shopping tool |
| event_store `record_sensor` | `event_store/writer.py:39` | `office/{zone}/sensor/...` のみ対応 | — | — |

## Wave 計画

### P0 — 既存 channel の文脈露出と欠損 subscriber 追加

1. **Zone sensor context 拡張**
   - `world_model/world_model.py:_get_physical_context` (line 1591-1741) の zone セクションに、該当 zone の `latest fused sensor` を 1 行追加:
     ```
     [living_room] temp 23.4C, hum 45%, pressure 1013hPa, voc 120, pm25 8, light 450lx, soil(balcony) 32%
     ```
   - 欠測 channel はスキップ。channel 並びは重要度順 (temp, hum, pressure, voc, pm25, light, soil)
   - 行幅は 140 文字で truncate

2. **Weather alerts subscribe**
   - `world_model.py:489` 付近の topic routing に `hems/weather/alerts` handler 追加
   - `WeatherState.alerts` に格納、`_get_physical_context` の weather 行に severity 含めて記載
   - 台風・大雨 alerts を LLM が見えるようになる

3. **Shopping / GAS 用 event 記録**
   - `event_store/writer.py` に `record_world_event(source_type, topic, payload_digest, subject_ref)` を追加 (既存 `record_sensor` の一般化)
   - `main.py` の mqtt 受信で `hems/shopping/*`, `hems/gas/*`, `hems/weather/alerts`, `hems/news/urgent` を `record_world_event` 行に流す
   - 重複抑制: 同一 payload_digest は 5min cooldown

### P1 — 使い道のある rule を追加

4. **soil_moisture 水やり rule**
   - `rule_engine.py` に `_evaluate_soil_moisture()`:
     - `< 25%` で 6h 以内に speak/task がなければ task 作成 "植物に水やり"
     - `tapo` プロファイル有効なら pulse (duration_s=45) で自動給水後 speak ("給水しました")
     - `HEMS_ENABLE_AUTO_WATER` env で自動 toggle (デフォ off)

5. **VOC 換気 rule**
   - VOC > 500 (TVOC index) で 2min 継続 → `speak("換気をおすすめします")` + HA に換気扇 scene があれば execute
   - cooldown 30min

6. **PM2.5 native rule**
   - `pm25 > 35 µg/m³` → speak + (設定されていれば) 空気清浄機 ON (`control_actuator` 経由)
   - 既存 HA binary_sensor rule と重複発火しないよう dedupe key を統一

7. **Pressure 絶対値 & 持続変化 rule**
   - 現行の急降下 rule に加え、`< 1000 hPa` が 3h 継続 → 低気圧頭痛注意 speak (1 日 1 回)
   - `> 1025 hPa` かつ気温差大 → 指標として記録のみ (action 無し)

8. **Illuminance 異常 rule**
   - 夜間 (22:00-05:00) を除く時間帯に `light < 20 lx` が 10min → センサー故障 or 停電疑い task 作成
   - 日中に `light > 50000 lx` 連続 → カーテン自動制御 (既に HA rule があれば dedupe)

### P1 — 新規 tool

9. **`get_sensor_history(zone, channel, hours)`**
   - `event_store` から該当 channel の最近値を返す read-only tool
   - LLM が "さっきまで VOC 高かった？" を自問できるようにする
10. **`list_active_sensors(zone?)` tool**
    - 現時点で data が来ている channel 一覧を返す (device registry 経由で自動整備)
    - 開発者デバッグ兼、LLM が "このセンサーは観測可能か" を判断するため

### P2 — センサー故障と長期観測

11. **Stale sensor 検知**
    - 各 channel に `last_seen`。`> 30min` で stale flag を立て、context で `temp: stale` 表示
    - 連続 4h stale で task "{zone} {channel} センサー確認" を 1 日 1 回作成
12. **長期傾向ダッシュボード**
    - `aggregator.py` の hourly_aggregates に VOC / PM2.5 / pressure を追加（既に temp/hum はありそう）
    - 月次 trend を knowledge/learnings/ に週 1 回ダンプ

## Acceptance Criteria

- [ ] P0: `docker logs -f hems-brain` で各 zone が 1 行に fused sensor summary を出している
- [ ] P0: `sqlite3 event_store.db "select * from world_events where source_type='shopping' limit 5"` で shopping イベントが残っている
- [ ] P0: weather alert mock を mqtt publish → LLM context の weather 行に severity 付きで反映
- [ ] P1: VOC mock spike 1000 を 3min 流す → 換気 speak が 1 回だけ発火
- [ ] P1: soil_moisture < 25% を 10min 流す → 水やり task 作成 (auto_water off のとき speak のみ)
- [ ] P1: `get_sensor_history("living_room", "pressure", 24)` が数十点返る

## Risks

- **Sensor が無い環境での false negative**: 各 rule はチャンネルが空の zone では `continue` する。false positive を避けるため、rule 条件は `value is not None` を明示
- **Pulse auto-water の安全性**: Tapo pulse は既に duration_s ≤ 600 の guardrail あり (CLAUDE.md 記載)。水ポンプ用途は 45s を上限に追加制限
- **Event store 肥大**: world_events は shopping/gas/weather/news を入れると rows 増加。cooldown 5min + TTL 90 日で制御
- **Context 文字数**: P0 で zone ごと 1 行増える → 4 zone で 4-600 文字増。`_get_physical_context` 全体の length_cap に収まる範囲で truncate

## 実装順序

P0 (1-3) で「全センサーが LLM から見える」状態を作る → P1 rule (4-8) で死蔵 channel を判断に接続 → P1 tool (9-10) → P2 長期観測。P0 だけでも現状の「60-70% しか判断に使われていない」状態は 90%+ に押し上がる。
