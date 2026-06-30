# Phase 2: 適応的閾値とドリフト検知

> 本計画は HEMS のルールエンジン閾値を、センサーデータのドリフトやユーザー/介入効果フィードバックに応じて適応的に更新するための詳細計画です。
> 前提調査: [adaptive-threshold-drift-detection.md](./adaptive-threshold-drift-detection.md)

---

## 1. 目的

- 固定閾値の陳腐化（threshold rot）を防ぎ、季節変動・生活リズム変化に追従する。
- 概念ドリフト（concept drift）を検知し、閾値の再較正トリガーとする。
- Phase 1 の feedback / intervention_efficacy を閾値更新に反映する。

---

## 2. スコープ

### 含む

- `River` ライブラリの導入
- `MetricDriftTracker` / `AdaptiveThresholdManager` 実装
- `RuleThresholds` の動的オフセット拡張
- 閾値変更提案の可視化・承認 UI
- `threshold_drift_log` / `threshold_adjustments` テーブル

### 含まない

- ルールの自動生成（Phase 3）
- 因果推論による効果検証（Phase 4）
- 天候/季節を完全に分離した予測モデル（Phase 4 サロゲートモデルで対応）

---

## 3. 前提条件

- Phase 1 の `agent_feedback` / `intervention_efficacy` が利用可能。
- `services/brain/src/rules/config.py` の `RuleThresholds` を理解している。
- Python 3.11 環境。

---

## 4. スキーマ変更

### 4.1 `threshold_drift_log` テーブル（新規、backend）

```python
class ThresholdDriftLog(Base):
    __tablename__ = "threshold_drift_log"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String, nullable=False, index=True)
    detector = Column(String, nullable=False)
    detected_at = Column(TZDateTime(timezone=True), server_default=func.now())
    old_value = Column(Float)
    proposed_value = Column(Float)
    reason = Column(String)  # drift, feedback, efficacy
    status = Column(String, default="proposed")  # proposed, approved, rejected, auto_applied
```

### 4.2 `threshold_adjustments` テーブル（新規、backend）

```python
class ThresholdAdjustment(Base):
    __tablename__ = "threshold_adjustments"
    id = Column(Integer, primary_key=True)
    metric_key = Column(String, nullable=False, index=True)
    base_value = Column(Float, nullable=False)
    offset = Column(Float, default=0.0)
    applied_at = Column(TZDateTime(timezone=True), server_default=func.now())
    approved_by = Column(String)  # system, user, auto
```

### 4.3 `drift_detections` テーブル（新規、event_store）

```sql
CREATE TABLE events.drift_detections (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_key TEXT NOT NULL,
    detector TEXT NOT NULL,
    old_threshold REAL,
    proposed_threshold REAL,
    detector_state JSONB DEFAULT '{}'
);
```

---

## 5. 新規コンポーネント

| コンポーネント | 配置 | 責務 |
|--------------|------|------|
| `AdaptiveThresholdManager` | `services/brain/src/adaptive_thresholds/manager.py` | 各メトリクスの DriftTracker 群を管理 |
| `MetricDriftTracker` | `services/brain/src/adaptive_thresholds/tracker.py` | 1 メトリクスあたりの ADWIN/Page-Hinkley ラッパー |
| `ThresholdAdjuster` | `services/brain/src/adaptive_thresholds/adjuster.py` | feedback / efficacy を使って閾値オフセット更新 |
| `AdaptiveRuleThresholds` | `services/brain/src/rules/config.py` 内 | `RuleThresholds` の動的版 |
| `threshold_drift` API | `services/backend/routers/adaptive_thresholds.py` | 閾値変更提案の取得・承認 |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/models.py` — 新規テーブル
- `services/backend/schemas.py` — Pydantic schema
- `services/backend/routers/adaptive_thresholds.py` — 新規
- `services/backend/main.py` — router 登録

### 6.2 Brain

- `services/brain/src/rules/config.py` — `AdaptiveRuleThresholds`
- `services/brain/src/rule_engine.py` — 動的閾値参照
- `services/brain/src/world_model/world_model.py` — センサー値を tracker にフィード
- `services/brain/src/brain_loops.py` — 日次バッチで再較正
- `services/brain/src/main.py` — コンポーネント wire

### 6.3 Frontend

- `services/frontend/src/components/ThresholdProposalCard.tsx` — 新規
- `services/frontend/src/app/settings/thresholds/page.tsx` — 新規
- `services/frontend/src/types.ts` — ThresholdDriftLog 型

### 6.4 依存

- `requirements*.txt` に `river>=0.21` を追加。

---

## 7. 実装ステップ

### Step 1: River 導入（0.5 週間）

1. `river` を `requirements-dev.txt` / 各サービスの requirements に追加。
2. ライセンス（MIT）と脆弱性（pip-audit）を確認。

### Step 2: スキーマ整備（1 週間）

1. `threshold_drift_log` / `threshold_adjustments` / `drift_detections` テーブルを追加。
2. `AdaptiveRuleThresholds` dataclass を設計。
   - 静的基準値 + 動的オフセット + drift_state
   - `RuleEngine` は `thresholds.temp_high` のようなプロパティを参照するだけ

### Step 3: MetricDriftTracker（1 週間）

1. `MetricDriftTracker` を実装。
   - `river.drift.ADWIN` or `PageHinkley`
   - `update(value)` → drift_detected, estimation, variance, width
2. 対象メトリクスを選定（最初は `co2_high`, `temp_high`, `temp_low`, `humidity_high` 等）。

### Step 4: AdaptiveThresholdManager（1 週間）

1. `AdaptiveThresholdManager` を実装。
   - 各 metric_key に対して `MetricDriftTracker` を保持。
   - 毎サイクル、センサー値を tracker にフィード。
   - ドリフト検出時に `threshold_drift_log` に `proposed` 状態で記録。
2. Brain 起動時に既存 `threshold_adjustments` から offset を復元。

### Step 5: ThresholdAdjuster（1 週間）

1. `ThresholdAdjuster` を実装。
   - feedback（dismiss/confirm）に応じて offset を nudge。
   - intervention_efficacy（effective/counterproductive）に応じて offset を更新。
   - offset に上限/下限を設ける。
2. ユーザー承認制 or 自動承認設定を切り替え可能に。

### Step 6: 承認 UI（1 週間）

1. `ThresholdProposalCard` を実装。
   - metric_key, old_value, proposed_value, reason 表示
   - 承認/棄却ボタン
2. `settings/thresholds` ページに履歴一覧を表示。

### Step 7: 統合テスト（1 週間）

1. ドリフト検知の unit test。
2. feedback → offset 更新のテスト。
3. 閾値変更後の RuleEngine 発火テスト。
4. 季節性データを使った sim-to-real テスト。

---

## 8. 検証方法

```bash
# 1. River 導入確認
python -c "from river import drift; print(drift.ADWIN)"

# 2. ドリフト検知をシミュレート
mosquitto_pub -t 'hems/sensors/living/co2' -m '{"value": 400}'  # 100 回
mosquitto_pub -t 'hems/sensors/living/co2' -m '{"value": 1200}' # 急変

# 3. threshold_drift_log に提案が記録されることを確認
sqlite3 data/hems.db "SELECT * FROM threshold_drift_log WHERE metric_key='co2_high'"

# 4. 承認後、RuleEngine の閾値が更新されることを確認
sqlite3 data/hems.db "SELECT * FROM threshold_adjustments WHERE metric_key='co2_high'"
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| False positive 増大 | delta パラメータ保守的、複数 detector の投票 |
| 閾値暴走 | offset に上限/下限、承認制 |
| 季節性混同 | 時刻/季節を特徴量に加え、context-aware detector を Phase 4 で拡張 |
| 計算コスト | 重要メトリクスのみ対象、edge 側で簡易検知 |
| 解釈性低下 | 閾値変更理由を常に記録、UI で説明 |

---

## 10. 工数感

- 合計: **6〜8 週間**（1.5〜2 ヶ月）

---

## 11. 次フェーズ接続

- `threshold_adjustments` は Phase 3 の `RuleLearner` / `ThresholdAdapter` と統合される。
- ドリフト検知結果は Phase 4 の因果層で再学習トリガーとして使用される。
- feedback に基づく閾値更新の履歴は Phase 5 の reward shaping にも利用可能。
