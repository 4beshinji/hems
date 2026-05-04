# Wiring Gap 03 — Biometric Enhancement

> **CLOSED 2026-05-03**: 全項目が [`wiring-gap-06-data-flow-consolidation.md`](wiring-gap-06-data-flow-consolidation.md) に統合・解消済み (Wave 1 で steps dedup + stale 段階ラベル、Wave 3 で history deque + trend rules + trend tools、Wave 4 で HRV fatigue 計算式 + fatigue→schedule_learner / stress→VLM)。

Biometric bridge は HR / SpO2 / sleep / activity / steps / stress / fatigue / HRV / body_temp / respiratory_rate を publish。Brain 側に単発閾値 rule はあるが、**トレンド活用と LLM への能動露出が無い**。steps は二重 publish。

対象: `services/biometric-bridge/src/`, `services/brain/src/world_model/`, `services/brain/src/rule_engine.py`, `services/brain/src/tool_registry.py`

## 現状 (file:line)

| 項目 | 場所 | 状況 |
|---|---|---|
| HR/SpO2 threshold rules | `rule_engine.py:820-900` 付近 | ✅ 単発 alert |
| HRV low / body_temp high / resp_rate high | `rule_engine.py:918, 936, 954` | ✅ rule あり |
| `_get_user_context` の bio 出力 | `world_model/world_model.py:1928-1933` | ❌ **"recently updated" でないと出ない** |
| fatigue 単発 alert | `rule_engine.py:846` + 照明調整 `rule_engine.py:974` | ✅ 単発 |
| sleep quality alert | `rule_engine.py:862` | ✅ 翌朝 1 回のみ |
| トレンド保持 | なし | ❌ **過去比較不可** |
| トレンド参照 tool | なし | ❌ `get_biometrics / get_sleep_summary` は現在値のみ |
| steps 二重 publish | `biometric-bridge/main.py:128` (直接) + `:178` (activity 内埋込) | ⚠ 重複 |
| stress × HR 相関 rule | なし | ❌ |

## Wave 計画

### P0 — 現在値を常時露出 + 重複除去

1. **bio context を常時出力に変更**
   - `world_model.py:1928-1933` の "最近更新時のみ" ガードを外し、`last_seen` 秒数を必ず添える:
     - `< 600s`: `HR 72 (live)`
     - `< 3600s`: `HR 72 (10分前)`
     - `>= 3600s`: 古いので省略 or `HR: stale`
   - 対象フィールド: HR, HRV, SpO2, stress, fatigue, body_temp, resp_rate, steps_today, sleep_last_night
   - 出力は `_get_user_context` 内で 1 block にまとめ、上限 200 文字程度

2. **steps 二重 publish 削除**
   - `biometric-bridge/main.py:128` の `/steps` 単独 publish は残し、`:178` の activity payload から steps field を削除
   - Brain 側 `world_model.py:1323, 1327` のどちらか一方に統一 (`/steps` を真とする)
   - テスト: Gadgetbridge 形式 webhook で steps 値が二重加算されない

### P1 — トレンド保持とトレンド Rule / Tool

3. **Rolling window storage**
   - `world_model/data_classes.py` の `BiometricState` (or 同等) に `history: dict[metric, deque[(ts, value)]]` 追加
   - maxlen: HR は 24h × 60sample/h 相当で 1440、fatigue/sleep は 14 日分
   - メモリ圧迫回避のため、stress/fatigue など低頻度メトリクスのみ長期保持

4. **Trend rules** (`rule_engine.py`)
   - `_evaluate_fatigue_streak()`: fatigue >= 70 が 3 日連続 → "休息を推奨" + knowledge 書き込み (HEMS/learnings/)
   - `_evaluate_sleep_decline()`: 直近 7 日の sleep_quality 平均が前 7 日比で -15% → 朝 briefing 追加
   - `_evaluate_stress_hr_coupling()`: 15 分 window で stress>70 かつ HR baseline +20% → 環境静音提案
   - いずれも cooldown 必須（例: streak rule は 1 日 1 回）

5. **新規 LLM tool 2 本**
   - `get_biometric_trend(metric: str, window_hours: int = 24) -> {avg, min, max, trend}` — 傾向値を返す
   - `get_sleep_history(days: int = 7) -> [{date, duration, quality, phases}]`
   - read-only, tool_registry に登録

### P2 — 行動連結

6. **Fatigue → schedule_learner 反映**
   - 高疲労日は `schedule_learner` の wake prediction に `fatigue_offset` を渡し、目覚ましを 15min 遅らせる
7. **Stress spike → perception VLM 要求**
   - stress 急上昇 (5min で +30) → `hems/perception/vlm/request` publish で居室状況を把握 (クロスドメイン trigger)
8. **HRV を疲労スコアの 4 要素目に組み込み**
   - 現行 fatigue_score = HR 30% + sleep 40% + stress 30% → HRV を混ぜ (HR 20 + HRV 15 + sleep 35 + stress 30)
   - `biometric-bridge/src/data_processor.py` の fatigue 計算式を拡張

## Acceptance Criteria

- [ ] P0: `docker logs -f hems-brain` で LLM context に `HR 72 (2分前), fatigue 45 (10分前), sleep last night 6h32m` が毎サイクル出る
- [ ] P0: Gadgetbridge webhook を一度叩くと steps が activity と steps で二重加算されない
- [ ] P1: `get_biometric_trend("fatigue", 72)` で 3 日分の avg/min/max/trend が返る
- [ ] P1: fatigue 70+ を 3 日 mock injection → streak rule が 1 回だけ発火
- [ ] P1: sleep quality を徐々に下げる 14 日分の mock → decline rule が発火

## Risks

- **Memory footprint**: HR を 1440 点保持 × 数週間で数 MB。問題ないが restart で揮発するため、後日 SQLite 永続化も検討 (P2 以降)
- **False trend**: サンプル数が少ない初期は trend 判定が不安定 → 最低 N サンプル (HR=30, fatigue=3日) を条件に含める
- **Privacy**: knowledge 書き出し (HEMS/learnings/) に生理データが残るため、writer 側でマスク（具体値 → 相対表現 "高疲労"）する

## 実装順序

P0 (1, 2) で常時露出 + bug fix → P1 (3-5) でトレンド基盤 → P2 (6-8) でクロスドメイン。P0 だけで LLM が「今の体調」を常に把握できるようになる（これが最大の不足）。
