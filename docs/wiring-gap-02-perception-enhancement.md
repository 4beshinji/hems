# Wiring Gap 02 — Perception / VLM Enhancement

Perception service は YOLO 検出 + VLM 解説 を publish しているが、VLM のシーン情報は "最終更新から 300 秒以内" の時だけ LLM に届く。Routine scan は 30min 間隔、event-boosted でも 1-5min → **大半の時間 LLM は VLM を見られない**。scene objects は格納されるが anomaly 以外は context から除外される。

対象: `services/perception/src/`, `services/brain/src/world_model/`, `services/brain/src/rule_engine.py`, `services/brain/src/tool_registry.py`

## 現状 (file:line)

| 項目 | 場所 | ギャップ |
|---|---|---|
| VLM result 受信 | `world_model/world_model.py:489, 1001-1036` | ✅ OK |
| `occupancy.vlm_last_update` 更新 | `world_model.py:1036` | ✅ OK |
| Context 露出 gate | `world_model.py:1653` — `now - vlm_last_update < 300` | ❌ **300s 外は消える** |
| Scene objects list 格納 | `world_model.py:1033` | ✅ 格納のみ |
| Scene objects の LLM 露出 | なし | ❌ **anomaly のみ** |
| Anomaly rule | `rule_engine.py:1040` 付近 | ❌ **一回発火で沈黙** |
| `describe_scene` tool | `tool_registry.py` | ✅ on-demand OK |
| `list_scene_objects` tool | なし | ❌ **履歴参照手段なし** |
| VLM model swap coord | `world_model.py:1055-1062`, brain fallback to rule-based | ✅ OK |

## Wave 計画

### P0 — VLM 記憶の延命

1. **Freshness gate を段階化**
   - `world_model.py:1653` を単一 300s 閾値から 3 段階へ:
     - `< 300s`: そのまま表示（fresh）
     - `< 1800s`: prefix `約N分前の観測` を付けて表示（aged）
     - `>= 1800s`: 要約 (zone名と人数のみ) か非表示。対象 zone が現在 occupancy=true の場合のみ要約を残す
   - これにより "30min 前の VLM 観測" も LLM に届く

2. **Scene objects を summary 行で露出**
   - `_get_physical_context` の zone 出力に 1 行追加:
     `objects: [desk, monitor, person_sitting]` のように最大 6 トークン
   - objects 数が多い場合は頻出上位で truncate
   - anomaly と同じ source から引ける (`world_model.py:1033`)

### P1 — 自律的な再評価と履歴

3. **Anomaly re-evaluation rule**
   - `rule_engine.py:1040` の既存 rule を拡張:
     - 初回: immediate alert
     - 5min 経過で anomaly が解消していなければ escalate (speak + task)
     - 30min 経過で zone 状態を VLM 再要求 (heavy モデル trigger)
   - `vlm_request` topic publish (`hems/perception/vlm/request`) で perception 側に再スキャンさせる

4. **Scene history buffer**
   - `world_model/data_classes.py` の `ZoneOccupancy` に `vlm_history: deque[SceneSnapshot]` 追加 (maxlen=10)
   - 古い snapshot は 1h 後に drop
   - LLM から時系列変化を参照可能に

5. **新規 LLM tool**
   - `list_scene_objects(zone: str, since_minutes: int = 60)` → history から objects をユニオン
   - `get_scene_timeline(zone: str)` → `[(t, description), ...]` 最大 10 件
   - `describe_scene` は既存を据え置き (on-demand VLM 呼び出しコスト高)

### P2 — 活動レベルと姿勢の活用

6. **Posture / activity を WorldModel 出力に**
   - `activity_tracker.py` が publish する posture (standing/sitting/lying) + activity level (0.0-1.0) は
     `office/{zone}/activity/{cam_id}` で流れ `world_model.py` で受信済み。
   - `_get_user_context` に `posture=sitting (85min streak)` を出力。座り過ぎ判断の material に使う
7. **Sedentary rule の integ 強化**
   - 既存の sedentary rule を、posture=sitting が 90min 連続かつ activity<0.1 のときのみ発火に限定し、
     false positive を減らす
8. **Model swap 中の LLM fallback 体感**
   - 既存の `vlm_model_swap_active` を `_get_physical_context` の heading に 1 行出し、
     LLM に "現在 rule-based mode" を明示 (説明責任)

## Acceptance Criteria

- [ ] P0: VLM 観測後 10 分経過しても LLM context に `約10分前の観測: 人なし` 等が残る
- [ ] P0: `objects: [...]` が zone ごとに出る
- [ ] P1: VLM anomaly 発火後、5 分解消しないと 2 回目 speak が出る (手動 inject でテスト)
- [ ] P1: `list_scene_objects(living_room, 60)` が過去 1h の履歴から返る
- [ ] P2: `posture=sitting` が LLM context の user section に出現

## Risks

- **Prompt 肥大**: scene history 10 スナップショットをそのまま書くと膨らむ。context 出力時は最新 3 件まで + objects のみ要約
- **VLM 再要求ループ**: anomaly 再評価 rule が過剰に `vlm_request` を publish すると GPU 負荷増。re-request は 30min cooldown 必須
- **Stale object の false hint**: 古い objects 情報で LLM が "人がいる" と誤認する恐れ → `約Nm前` prefix を必ず付ける

## 実装順序

P0 (1, 2) を先行 → P1 (3-5) で tool + history → P2 (6-8) で posture 連携。P0 だけでも VLM の "見える時間帯" が実質 6 倍（300s → 1800s）に伸びる。
