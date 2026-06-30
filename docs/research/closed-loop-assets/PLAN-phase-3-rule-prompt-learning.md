# Phase 3: ルール/プロンプトの自動学習

> 本計画は HEMS の実行結果フィードバックから、自動化ルールと LLM プロンプトを自動生成・最適化するための詳細計画です。
> 前提調査: [automated-rule-prompt-learning.md](./automated-rule-prompt-learning.md)

---

## 1. 目的

- センサー/デバイス履歴から `AutomationRule` 候補を発見・提案する。
- LLM system prompt / `llm_review` prompt を自動最適化する。
- ユーザー承認/棄却/介入効果を使ってルール信頼度を更新する。

---

## 2. スコープ

### 含む

- association rule mining によるルール候補発見
- `LearnedRuleCandidate` テーブルと承認フロー
- `PromptVariant` テーブルと A/B 運用
- `RuleLearner` / `PromptOptimizer` / `ThresholdAdapter`
- `RulePromoter` の対象拡張

### 含まない

- LLM 重み更新（Phase 5）
- 因果推論による効果検証（Phase 4）
- デジタルツイン（Phase 4）

---

## 3. 前提条件

- Phase 1 の `agent_feedback` / `intervention_efficacy` が利用可能。
- Phase 2 の `AdaptiveThresholdManager` / `ThresholdAdjuster` が利用可能。
- `mlxtend` 等の association rule mining ライブラリ導入。

---

## 4. スキーマ変更

### 4.1 `learned_rule_candidates` テーブル（新規、backend）

```python
class LearnedRuleCandidate(Base):
    __tablename__ = "learned_rule_candidates"
    id = Column(Integer, primary_key=True)
    status = Column(String, default="proposed")  # proposed | accepted | rejected | auto_disabled
    source = Column(String, nullable=False)  # association_mining | llm_proposal | threshold_adaptation
    name = Column(String, nullable=False)
    description = Column(String)
    trigger_type = Column(String, nullable=False)
    trigger_config = Column(JSON, default=dict)
    actions = Column(JSON, default=list)
    confidence = Column(Float, default=0.5)
    evidence_json = Column(Text)
    proposed_at = Column(TZDateTime(timezone=True), server_default=func.now())
    decided_at = Column(TZDateTime(timezone=True), nullable=True)
    decide_reason = Column(String, nullable=True)
```

### 4.2 `prompt_variants` テーブル（新規、backend）

```python
class PromptVariant(Base):
    __tablename__ = "prompt_variants"
    id = Column(Integer, primary_key=True)
    target = Column(String, nullable=False, index=True)  # system_prompt | llm_review | ...
    variant_hash = Column(String, nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    source = Column(String, default="ape")  # ape | human | dspy
    active = Column(Boolean, default=False)
    win_rate = Column(Float, nullable=True)
    sample_count = Column(Integer, default=0)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
```

### 4.3 `rule_feedback` テーブル（新規、backend）

```python
class RuleFeedback(Base):
    __tablename__ = "rule_feedback"
    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id"), nullable=True)
    candidate_id = Column(Integer, ForeignKey("learned_rule_candidates.id"), nullable=True)
    feedback_type = Column(String, nullable=False)  # accept | reject | override | implicit_satisfied | implicit_unsatisfied
    context_json = Column(Text)
    reward = Column(Float, nullable=True)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
```

### 4.4 `intervention_efficacy` 拡張

- `action_id` (rule_id or scene execution id)
- `action_kind` (`rule` | `scene` | `llm_task`)
- `user_override_within_window`

---

## 5. 新規コンポーネント

| コンポーネント | 配置 | 責務 |
|--------------|------|------|
| `RuleLearner` | `services/brain/src/learning/rule_learner.py` | association rule mining / classifier で候補ルール生成 |
| `PromptOptimizer` | `services/brain/src/learning/prompt_optimizer.py` | APE/DSPy による prompt variant 生成・評価 |
| `ThresholdAdapter` | `services/brain/src/learning/threshold_adapter.py` | `RuleThresholds` 内の学習対象閾値を更新 |
| `LearningScheduler` | `services/brain/src/learning/scheduler.py` | 上記を毎日/毎週起動 |
| `FeedbackCollector` 拡張 | `services/brain/src/feedback/collector.py` | rule 単位 feedback を正規化 |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/models.py` — 新規テーブル
- `services/backend/schemas.py` — Pydantic schema
- `services/backend/routers/automations.py` — candidate → rule 昇格 API
- `services/backend/routers/feedback.py` — rule feedback 受付
- `services/backend/main.py` — router 登録

### 6.2 Brain

- `services/brain/src/annotator/rule_promoter.py` — 対象拡張
- `services/brain/src/learning/` — 新規ディレクトリ・コンポーネント
- `services/brain/src/system_prompt.py` — variant 読み込み機構
- `services/brain/src/persona_rewriter.py` — variant 対応
- `services/brain/src/automation_engine.py` — 発火時に feedback 暗黙エントリ生成
- `services/brain/src/brain_loops.py` — LearningScheduler 起動
- `services/brain/src/main.py` — コンポーネント wire

### 6.3 Frontend

- `services/frontend/src/app/automations/proposals/page.tsx` — 新規
- `services/frontend/src/components/RuleProposalCard.tsx` — 新規
- `services/frontend/src/app/settings/prompts/page.tsx` — 新規

### 6.4 依存

- `mlxtend`（association rule mining）
- `dspy-ai`（optional、プロンプト最適化）
- `scikit-learn`, `xgboost` / `lightgbm`

---

## 7. 実装ステップ

### Step 1: スキーマ整備（1 週間）

1. `learned_rule_candidates` / `prompt_variants` / `rule_feedback` テーブルを追加。
2. `AutomationRule` に `source` 列を追加（`seed | llm_generated | user | learned | promoted`）。

### Step 2: RuleLearner（2 週間）

1. `RuleLearner` を実装。
   - 入力: `raw_events` + `DeviceActionLog`（過去 N 日）
   - 前処理: 時刻帯、曜日、在室、センサ値、デバイス状態を特徴量化
   - `mlxtend.frequent_patterns.apriori` / `association_rules` で候補発見
   - 候補を `AutomationRule` JSON 形式に変換
2. 閾値（support, confidence, lift）をチューニング。
3. 生成ルールの安全性検証（危険デバイス/アクションを除外）。

### Step 3: ルール候補承認 UI（1 週間）

1. `RuleProposalCard` を実装。
   - トリガー、アクション、出現頻度、効果予測を表示
   - 承認/棄却/修正ボタン
2. 承認されたら `AutomationRule` として有効化（初期 `enabled=false`、A/B 期間後に自動有効化）。

### Step 4: PromptOptimizer（2 週間）

1. `PromptOptimizer` を実装。
   - APE: 入出力例から instruction 候補を生成・評価
   - `system_prompt.py` / `llm_review` prompt を variant 化
2. `PromptVariant` テーブルに保存。
3. A/B 評価: 介入効果スコア、承認率、無駄な tool call 数を metric に。
4. 勝率が高い variant を徐々にロールアウト。

### Step 5: ThresholdAdapter（1 週間）

1. Phase 2 の `ThresholdAdjuster` と統合。
2. `RuleThresholds` 内の学習対象パラメータを定義（`LEARNABLE_THRESHOLDS`）。
3. bandit/gradient で更新。上限/下限、1 回あたり最大変化量を設ける。

### Step 6: LearningScheduler（1 週間）

1. 日次/週次バッチで以下を実行。
   - `RuleLearner.run()`
   - `PromptOptimizer.compile()`
   - `ThresholdAdapter.calibrate()`
2. 結果を Obsidian `HEMS/learnings/` に書き出し。

### Step 7: 統合テスト（1 週間）

1. association rule mining のテストデータを作成。
2. ルール候補生成 → 承認 → 発火 → feedback の一連テスト。
3. prompt variant A/B の統合テスト。
4. 閾値更新の boundary test。

---

## 8. 検証方法

```bash
# 1. 学習スケジューラを手動実行
cd services/brain && python -c "from learning.scheduler import LearningScheduler; import asyncio; asyncio.run(LearningScheduler().run_daily())"

# 2. 候補ルールを確認
sqlite3 data/hems.db "SELECT name, source, confidence, status FROM learned_rule_candidates"

# 3. 承認
curl -X POST http://localhost:8010/automations/proposals/1/accept \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{"reason": "makes sense"}'

# 4. prompt variant の勝率を確認
sqlite3 data/hems.db "SELECT target, variant_hash, win_rate, sample_count FROM prompt_variants WHERE active=true"
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| Hallucinated ルール | backend validation、承認制、危険アクション除外 |
| ルールコンフリクト | conflict detector、優先度機構 |
| 安全クリティカル領域への誤学習 | CO2/SpO2 等は学習対象外 |
| 過度なフィードバック要求 | 暗黙フィードバック主体、明示は高不確実例のみ |
| APE/DSPy コスト | バックグラウンドバッチ、評価回数制限 |

---

## 10. 工数感

- 合計: **8〜12 週間**（2〜3 ヶ月）

---

## 11. 次フェーズ接続

- `learned_rule_candidates` の効果測定は Phase 4 の因果層で検証される。
- `prompt_variants` の勝率データは Phase 5 の `PreferenceBuilder` に入力される。
- `rule_feedback` は Phase 5 の reward shaping に利用可能。
