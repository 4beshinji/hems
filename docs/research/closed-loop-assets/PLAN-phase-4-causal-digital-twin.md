# Phase 4: 因果推論とデジタルツイン

> 本計画は HEMS の介入効果を因果的に推定し、デジタルツイン/What-If シミュレーションで行動を仮想実行してから実機に反映するための詳細計画です。
> 前提調査: [causal-inference-intervention-effect.md](./causal-inference-intervention-effect.md), [digital-twin-whatif-simulation.md](./digital-twin-whatif-simulation.md)

---

## 1. 目的

- 「介入が本当に効果を持ったか」を相関ではなく因果的に推定する。
- デジタルツイン上で候補行動を仮想実行し、最適行動を選択する。
- 予測と実測の差異からモデルを継続的に校正する。

---

## 2. スコープ

### 含む

- `services/brain/src/causal/` 層の構築
- `DoWhy` / `EconML` / `CausalML` の導入
- `intervention_efficacy` の因果推定拡張
- `services/simulation/` 新規サービス（軽量サロゲートモデル + EnergyPlus 連携）
- `WhatIfPlanner` / `SafetyGate` / `EfficacyComparator`

### 含まない

- フル 3D ビジュアルデジタルツイン
- クラウド DT サービス（Azure Digital Twins 等）
- リアルタイム MPC（Phase 5 以降で検討）

---

## 3. 前提条件

- Phase 1/2/3 の feedback / threshold adaptation / rule learning が利用可能。
- PostgreSQL 推奨（JSONB、統計関数）。
- 家屋メタデータ（間取り、U-value、HVAC 仕様等）の整備。

---

## 4. スキーマ変更

### 4.1 `intervention_efficacy` 拡張（event_store）

```sql
ALTER TABLE events.intervention_efficacy
ADD COLUMN action_id TEXT,
ADD COLUMN policy_id TEXT,
ADD COLUMN treatment_variant TEXT,
ADD COLUMN context_json JSONB,
ADD COLUMN propensity_score REAL,
ADD COLUMN counterfactual_value REAL,
ADD COLUMN effect_estimate REAL,
ADD COLUMN ci_lower REAL,
ADD COLUMN ci_upper REAL,
ADD COLUMN estimator TEXT,
ADD COLUMN n_samples INTEGER,
ADD COLUMN model_version TEXT,
ADD COLUMN predicted_value REAL,
ADD COLUMN predicted_delta REAL,
ADD COLUMN sim_run_id BIGINT,
ADD COLUMN model_error REAL;
```

### 4.2 `causal_estimates` テーブル（新規、event_store）

```sql
CREATE TABLE events.causal_estimates (
    id BIGSERIAL PRIMARY KEY,
    treatment_variant TEXT NOT NULL,
    context_signature TEXT NOT NULL,
    effect_estimate REAL,
    ci_lower REAL,
    ci_upper REAL,
    n_samples INTEGER,
    model_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.3 `policy_logs` テーブル（新規、event_store）

```sql
CREATE TABLE events.policy_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    context_json JSONB,
    action TEXT,
    propensity REAL,
    reward REAL,
    policy_id TEXT,
    exploration BOOLEAN DEFAULT FALSE
);
```

### 4.4 `simulation_runs` / `what_if_scenarios` テーブル（新規、event_store）

```sql
CREATE TABLE events.simulation_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario_id BIGINT,
    model_id TEXT NOT NULL,
    base_state JSONB NOT NULL,
    candidate_actions JSONB NOT NULL,
    forecast JSONB,
    result_json JSONB,
    kpi_json JSONB,
    status TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE events.what_if_scenarios (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    trigger_event_id BIGINT REFERENCES events.world_events(id),
    base_state_json JSONB NOT NULL,
    horizon_min INTEGER,
    candidate_actions_json JSONB,
    selected_action_idx INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.5 `automation_rules` 拡張（backend）

```python
# 追加想定フィールド
simulate_before_run = Column(Boolean, default=False)
simulation_horizon_min = Column(Integer, default=30)
simulation_kpi_weights = Column(JSON, default=dict)
simulation_mode = Column(String, default="surrogate")  # surrogate | energyplus | none
```

---

## 5. 新規コンポーネント

### 5.1 Causal 層（`services/brain/src/causal/`）

| コンポーネント | 責務 |
|--------------|------|
| `data_mart.py` | raw_events / device_action_log から学習用パネルデータ構築 |
| `propensity.py` | 処置選択確率を推定 |
| `effect_estimator.py` | DoWhy/EconML/CausalML で ATE/CATE 推定 |
| `policy_evaluator.py` | OPE（IPS/SNIPS/DR） |
| `policy_learner.py` | Contextual Bandit / ε-greedy |
| `intervention_planner.py` | 現在状態に対する介入候補と予測効果提示 |
| `causal_scheduler.py` | 日次/週次の再学習、閾値更新、レポート生成 |

### 5.2 Simulation 層（`services/simulation/`）

| コンポーネント | 責務 |
|--------------|------|
| `main.py` | FastAPI サービスエントリポイント |
| `models/surrogate.py` | 軽量サロゲートモデル（RC/GBDT/GP） |
| `models/energyplus.py` | EnergyPlus 連携 |
| `models/occupancy.py` | 在室・行動予測 |
| `calibration.py` | サロゲートモデルのオンライン更新 |

### 5.3 Brain What-If 層（`services/brain/src/what_if/`）

| コンポーネント | 責務 |
|--------------|------|
| `planner.py` | 候補行動生成・シミュレーション呼び出し・最適選択 |
| `client.py` | Simulation Service への REST/MQTT 呼び出し |
| `safety_gate.py` | 安全制約チェック |
| `comparator.py` | 予測 vs 実測の比較 |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/models.py` — `AutomationRule` 拡張
- `services/backend/routers/causal.py` — 新規（効果レポート API）
- `services/backend/routers/what_if.py` — 新規（シナリオ API）
- `services/backend/main.py` — router 登録

### 6.2 Brain

- `services/brain/src/event_store/database.py` — 新規テーブル DDL
- `services/brain/src/event_store/writer.py` — 新規 record メソッド
- `services/brain/src/causal/` — 新規ディレクトリ
- `services/brain/src/what_if/` — 新規ディレクトリ
- `services/brain/src/automation_engine.py` — What-If 呼び出し統合
- `services/brain/src/rule_engine.py` — CATE キャッシュ参照
- `services/brain/src/brain_cognitive.py` — ReAct loop で planner 呼び出し
- `services/brain/src/main.py` — コンポーネント wire

### 6.3 Frontend

- `services/frontend/src/components/SimulationResultCard.tsx` — 新規
- `services/frontend/src/components/CausalReportCard.tsx` — 新規
- `services/frontend/src/app/simulations/page.tsx` — 新規
- `services/frontend/src/types.ts` — SimulationRun / WhatIfScenario 型

### 6.4 Infra

- `infra/docker-compose.yml` — `simulation` サービス追加
- `infra/scripts/check_env_compose.py` — env 変数追加対応

### 6.5 依存

- `dowhy`, `econml`, `causalml`, `causal-learn`, `pgmpy`
- `pyenergyplus` / `eppy` / `fmpy`
- `scikit-learn`, `lightgbm`, `prophet`

---

## 7. 実装ステップ

### Step 1: スキーマ整備（1 週間）

1. `intervention_efficacy` / `causal_estimates` / `policy_logs` / `simulation_runs` / `what_if_scenarios` を追加。
2. `AutomationRule` に simulation 関連列を追加。

### Step 2: Causal Data Mart（1.5 週間）

1. `causal/data_mart.py` を実装。
   - raw_events / device_action_log / world_events を時系列で結合。
   - ラグ特徴量、処置系列、結果変数を生成。
2. 介入定義を設定（`ac_26c`, `window_open`, `humidifier_on` 等）。

### Step 3: Propensity & Effect Estimator（2 週間）

1. `propensity.py` を実装（LightGBM / ロジスティック回帰）。
2. `effect_estimator.py` を実装。
   - DoWhy 識別 + EconML `CausalForestDML` / `LinearDML`
   - 信頼区間、n_samples、model_version を出力
3. refutation（placebo, random cause, unobserved confounder）を実装。

### Step 4: Policy Evaluator / Learner（1.5 週間）

1. `policy_evaluator.py` を実装（IPS/SNIPS/DR）。
2. `policy_learner.py` を実装（ε-greedy contextual bandit）。
3. 探索時は承認モードと連携。

### Step 5: Simulation Service（3 週間）

1. `services/simulation/` サービスを新規作成。
2. `SurrogateModel` を実装（各ゾーン温度予測、RC/GBDT）。
3. `EnergyPlusModel` を Docker コンテナ化（オフライン校正用）。
4. `OccupancyPredictor` を実装（HMM/LSTM）。
5. FastAPI エンドポイントで `/simulate` を提供。

### Step 6: WhatIfPlanner & SafetyGate（2 週間）

1. `what_if/planner.py` を実装。
   - RuleEngine/LLM 候補を Simulation Service に送信
   - KPI スコアリングで最良行動を選択
2. `safety_gate.py` を実装。
   - 危険シナリオをブロック
3. `comparator.py` を実装。
   - 予測 vs 実測の誤差を計算

### Step 7: Frontend（1.5 週間）

1. SimulationResultCard / CausalReportCard を実装。
2. シミュレーション結果比較 UI。
3. 因果効果ダッシュボード（時系列、CATE ヒートマップ）。

### Step 8: 統合テスト（2 週間）

1. 因果推定器の合成データテスト。
2. SurrogateModel の予測精度テスト。
3. What-If → 実行 → 実測比較の end-to-end テスト。
4. SafetyGate 危険シナリオテスト。

---

## 8. 検証方法

```bash
# 1. 因果効果レポート取得
curl http://localhost:8010/causal/effects?treatment=ac_26c&metric=temperature

# 2. What-If シミュレーション要求
curl -X POST http://localhost:8010/what-if \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{
    "zone": "living",
    "horizon_min": 30,
    "candidate_actions": [
      {"device_id": "ac.living", "action": "set_temperature", "params": {"temperature": 26}},
      {"device_id": "ac.living", "action": "set_temperature", "params": {"temperature": 28}}
    ]
  }'

# 3. simulation_runs に記録されることを確認
sqlite3 services/brain/data/hems_brain.db "SELECT * FROM simulation_runs ORDER BY id DESC LIMIT 3"

# 4. モデル誤差を確認
sqlite3 services/brain/data/hems_brain.db "SELECT sim_run_id, predicted_value, post_value, model_error FROM intervention_efficacy WHERE model_error IS NOT NULL"
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| 未観測交絡 | 感度分析、単純モデル優先、IV 推定 |
| サンプル不足 | 信頼区間重視、類似セグメントプール |
| Positivity 侵害 | propensity clipping、hard safety layer 分離 |
| 遅延効果 | 複数ラグ窓、G-computation、washout period |
| Sim-to-real gap | 継続的キャリブレーション、不確実性定量化 |
| 計算コスト | オンラインはサロゲート、EnergyPlus は週次バッチ |

---

## 10. 工数感

- 合計: **12〜24 週間**（3〜6 ヶ月）
- このフェーズは最も大規模。サロゲートモデルから始め、EnergyPlus は後続で追加推奨。

---

## 11. 次フェーズ接続

- `causal_estimates` / `policy_logs` は Phase 5 の `PolicyUpdater` / `PreferenceBuilder` で使用。
- What-If の予測精度は Phase 5 の reward shaping に利用可能。
- CATE 推定結果は Phase 3 の `RuleLearner` でルール条件発見に活用。
