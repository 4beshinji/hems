# Phase 1: フィードバック収集と介入効果測定

> 本計画は HEMS の閉 loop における「実行結果の観測」を正規化し、ユーザーからの明示/暗黙フィードバックと介入効果測定を統合するための詳細計画です。
> 前提調査: [llm-agent-feedback-rlhf.md](./llm-agent-feedback-rlhf.md), [causal-inference-intervention-effect.md](./causal-inference-intervention-effect.md)

---

## 1. 目的

- ユーザーからの承認/棄却/上書き/スヌーズ等のフィードバックを正規化して収集する。
- 環境タスクに限らず、デバイス制御・シーン実行・LLM タスク全般の「介入効果」を測定する。
- Phase 0 の HITL 結果と紐付け、閉 loop の学習材料を整備する。

---

## 2. スコープ

### 含む

- `agent_feedback` / `agent_trajectories` テーブル新設
- `FeedbackCollector` コンポーネント実装
- `intervention_efficacy` テーブルの拡張
- 明示フィードバック UI（👍/👎、取り消し、再実行）
- 暗黙フィードバック検出（手動上書き、ack 遅延、スヌーズ）
- outcome reward の計算（センサー変化、タスク完了）

### 含まない

- LLM 重み更新（Phase 5）
- 因果推定器の本格導入（Phase 4）
- プロンプト最適化（Phase 3）

---

## 3. 前提条件

- Phase 0 の `approvals` テーブルと承認 API が利用可能。
- `services/brain/src/event_store/writer.py` が `record_decision` / `record_intervention_created` / `mark_intervention_completed` を提供。
- `services/brain/src/efficacy.py` が verdict 計算を行っている。

---

## 4. スキーマ変更

### 4.1 `agent_feedback` テーブル（新規、event_store）

```sql
CREATE TABLE events.agent_feedback (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decision_id BIGINT REFERENCES events.llm_decisions(id),
    approval_id UUID REFERENCES approvals(id),
    action_id TEXT,  -- device_action_log or scene id
    feedback_type TEXT NOT NULL,  -- explicit_like, explicit_dislike, implicit_override, implicit_snooze, implicit_ack_delay, outcome_verdict, ai_judge
    source TEXT NOT NULL,  -- frontend, voice, mobile, intervention_efficacy, trajectory_judge
    score REAL,  -- -1.0 ~ 1.0
    confidence REAL NOT NULL DEFAULT 1.0,
    rationale TEXT,
    payload JSONB NOT NULL DEFAULT '{}'
);
```

### 4.2 `agent_trajectories` テーブル（新規、event_store）

```sql
CREATE TABLE events.agent_trajectories (
    id BIGSERIAL PRIMARY KEY,
    decision_id BIGINT REFERENCES events.llm_decisions(id),
    prompt_hash TEXT NOT NULL,
    trajectory_json JSONB NOT NULL,  -- thought + tool_calls + observations
    reward REAL,
    judge_score REAL,
    human_score REAL,
    used_for_training BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.3 `intervention_efficacy` テーブルの拡張

```sql
ALTER TABLE events.intervention_efficacy
ADD COLUMN approval_id UUID REFERENCES approvals(id),
ADD COLUMN human_decision TEXT,  -- approve, reject, modify
ADD COLUMN rolled_back BOOLEAN DEFAULT FALSE,
ADD COLUMN rollback_success BOOLEAN,
ADD COLUMN efficacy_score REAL,
ADD COLUMN llm_decision_id BIGINT REFERENCES events.llm_decisions(id),
ADD COLUMN action_kind TEXT,  -- rule, scene, llm_task
ADD COLUMN user_override_within_window BOOLEAN DEFAULT FALSE;
```

### 4.4 `llm_decisions` テーブルの拡張

```sql
ALTER TABLE events.llm_decisions
ADD COLUMN prompt_template_version TEXT,
ADD COLUMN policy_version TEXT,
ADD COLUMN candidate_actions JSONB,
ADD COLUMN predicted_effects JSONB;
```

### 4.5 `device_action_log` テーブルの拡張

```sql
ALTER TABLE device_action_log
ADD COLUMN approval_id UUID REFERENCES approvals(id),
ADD COLUMN policy_id TEXT,
ADD COLUMN exploration BOOLEAN DEFAULT FALSE,
ADD COLUMN propensity REAL;
```

---

## 5. 新規コンポーネント

| コンポーネント | 配置 | 責務 |
|--------------|------|------|
| `FeedbackCollector` | `services/brain/src/feedback/collector.py` | 各種信号を正規化し `agent_feedback` へ書き込み |
| `ImplicitFeedbackDetector` | `services/brain/src/feedback/implicit_detector.py` | 手動上書き、ack 遅延、スヌーズ等を検出 |
| `OutcomeRewardCalculator` | `services/brain/src/feedback/outcome_reward.py` | センサー変化/タスク完了から報酬を計算 |
| `TrajectoryRecorder` | `services/brain/src/feedback/trajectory_recorder.py` | LLM decision trace を `agent_trajectories` に保存 |
| `FeedbackAPI` | `services/backend/routers/feedback.py` | Frontend からのフィードバック受付 |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/models.py` — `DeviceActionLog` 拡張
- `services/backend/routers/feedback.py` — 新規
- `services/backend/routers/approvals.py` — 承認判定時に feedback 連携
- `services/backend/routers/devices.py` — デバイス制御時に action_log 拡張
- `services/backend/main.py` — router 登録

### 6.2 Brain

- `services/brain/src/event_store/database.py` — 新規テーブル DDL
- `services/brain/src/event_store/writer.py` — `record_feedback`, `record_trajectory` 追加
- `services/brain/src/efficacy.py` — `intervention_efficacy` 拡張対応
- `services/brain/src/tool_executor.py` — 実行時に action_id と feedback 紐付け
- `services/brain/src/brain_cognitive.py` — サイクル終了時に trajectory 保存
- `services/brain/src/automation_engine.py` — 発火時に policy_id / propensity 記録
- `services/brain/src/main.py` — 新規コンポーネント wire

### 6.3 Frontend

- `services/frontend/src/components/FeedbackButtons.tsx` — 新規
- `services/frontend/src/components/VoiceEventCard.tsx` — フィードバックボタン追加
- `services/frontend/src/components/TaskCard.tsx` — 取り消し/再実行ボタン追加
- `services/frontend/src/lib/api.ts` — feedback API client

---

## 7. 実装ステップ

### Step 1: スキーマ整備（1 週間）

1. `agent_feedback` / `agent_trajectories` テーブルを event_store に追加。
2. `intervention_efficacy` / `llm_decisions` / `device_action_log` を拡張。
3. Backend migration を生成。

### Step 2: FeedbackCollector（1 週間）

1. `FeedbackCollector` を実装。
   - `record_explicit(decision_id, feedback_type, score, source, payload)`
   - `record_implicit(action_id, implicit_type, score, payload)`
   - `record_outcome(action_id, verdict, score, payload)`
2. 各フィードバックに confidence を付与。
3. event_store writer に buffer flush 対応を追加。

### Step 3: 明示フィードバック UI（1 週間）

1. `FeedbackButtons` コンポーネントを実装（👍/👎、取り消し）。
2. VoiceEventCard / TaskCard / AlertCard に組み込み。
3. `POST /feedback` API を backend に実装。

### Step 4: 暗黙フィードバック検出（1 週間）

1. `ImplicitFeedbackDetector` を実装。
   - 手動上書き: `device_action_log` で、直近の自動実行後 N 分以内に逆のアクションがあれば `implicit_override`。
   - ack 遅延: voice capsule play-log の `trigger_drift_sec` が閾値超過。
   - スヌーズ: task の `last_reminded_at` 更新パターン。
2. 検出ルールを閾値化し、テストを追加。

### Step 5: Outcome Reward（1 週間）

1. `OutcomeRewardCalculator` を実装。
   - 入力: action_id, zone, metric, baseline_value, post_value, window_sec
   - 出力: reward (-1 ~ 1)
   - 快適帯に入ったか、目標に近づいたかを評価。
2. `efficacy.py` の verdict 計算と統合。
3. `intervention_efficacy` に `efficacy_score` を保存。

### Step 6: Trajectory 記録（1 週間）

1. `TrajectoryRecorder` を実装。
   - `_postprocess_cycle` 終了時に `messages` / `tool_calls` / `world_state_snapshot` を `agent_trajectories` に保存。
2. `llm_decisions` の `candidate_actions` / `predicted_effects` を埋める。
3. prompt_template_version / policy_version を管理。

### Step 7: 統合テスト（1 週間）

1. 明示フィードバック → `agent_feedback` 書き込みテスト。
2. 暗黙フィードバック検出テスト。
3. `intervention_efficacy` → reward 計算テスト。
4. 承認/棄却 → feedback 連携テスト。

---

## 8. 検証方法

```bash
# 1. デバイス制御を実行
curl -X POST http://localhost:8010/devices/test.plug/control \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{"action": "turn_on"}'

# 2. Frontend または API で 👍/👎
curl -X POST http://localhost:8010/feedback \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{"action_id": "...", "feedback_type": "explicit_like", "score": 1.0}'

# 3. agent_feedback に記録されたことを確認
sqlite3 services/brain/data/hems_brain.db "SELECT * FROM agent_feedback LIMIT 5"

# 4. intervention_efficacy の score が更新されることを確認
sqlite3 services/brain/data/hems_brain.db "SELECT task_id, efficacy_score, verdict FROM intervention_efficacy WHERE efficacy_score IS NOT NULL"
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| 暗黙フィードバックの誤検出 | 複数回の override パターンを待つ、confidence を下げる |
| フィードバックの偏り | 明示/暗黙/結果を重み付け、多角的に評価 |
| プライバシー | 個人の発言情報は保存期間を設ける、匿名化検討 |
| ノイズの多い reward | 移動平均、時間割引、外れ値除去 |

---

## 10. 工数感

- 合計: **5〜6 週間**（1〜1.5 ヶ月）

---

## 11. 次フェーズ接続

- `agent_feedback` / `intervention_efficacy` は Phase 2 の `ThresholdAdjuster`、Phase 3 の `RuleLearner` / `PromptOptimizer`、Phase 5 の `PolicyUpdater` の入力となる。
- `agent_trajectories` は Phase 5 の `TrajectoryJudge` / `PreferenceBuilder` で使用。
