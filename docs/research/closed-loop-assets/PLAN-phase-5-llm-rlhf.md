# Phase 5: LLM エージェントの RLHF

> 本計画は HEMS Brain の LLM エージェントに対し、実行結果フィードバックから軌跡を評価・学習し、few-shot プロンプト更新から LoRA adapter 学習（DPO/KTO/GRPO）まで段階的に強化するための詳細計画です。
> 前提調査: [llm-agent-feedback-rlhf.md](./llm-agent-feedback-rlhf.md)

---

## 1. 目的

- `event_store.llm_decisions` + `intervention_efficacy` + Frontend フィードバックを統合した `FeedbackCollector` を完成させる。
- LLM 決定軌跡を評価し、preference ペアを構築する。
- 軽量な LoRA adapter 学習で、パーソナライズされた応答・計画品質を向上させる。

---

## 2. スコープ

### 含む

- `FeedbackCollector` 完成（Phase 1 から拡張）
- `TrajectoryJudge`（LLM-as-Judge + 確定ルール）
- `PreferenceDatasetBuilder`
- `PolicyUpdater`（few-shot → LoRA → SFT）
- `agent_feedback` / `agent_trajectories` テーブル活用
- 軽量 DPO/LoRA 学習パイプライン

### 含まない

- 大規模分散 RLHF（OpenRLHF 等は将来オプション）
- 基盤モデルの pre-training
- 商用クラウド評価基盤（LangSmith 等）への完全移行

---

## 3. 前提条件

- Phase 1 の `agent_feedback` / `agent_trajectories` が蓄積されている。
- Phase 3 の `PromptOptimizer` / `prompt_variants` が利用可能。
- GPU or 十分な CPU リソース（LoRA 学習用）。
- Ollama または HuggingFace transformers 環境。

---

## 4. スキーマ変更

### 4.1 `llm_decisions` 拡張（event_store）

```sql
ALTER TABLE events.llm_decisions
ADD COLUMN prompt_template_version TEXT,
ADD COLUMN policy_version TEXT,
ADD COLUMN lora_adapter_id TEXT,
ADD COLUMN candidate_actions JSONB,
ADD COLUMN predicted_effects JSONB;
```

### 4.2 `agent_feedback` 活用（Phase 1 で作成済み）

- `feedback_type`: explicit_like, explicit_dislike, implicit_snooze, implicit_ack_delay, outcome_verdict, ai_judge
- `source`: frontend, voice, mobile, intervention_efficacy, trajectory_judge
- `score`, `confidence`, `rationale`, `payload`

### 4.3 `agent_trajectories` 活用（Phase 1 で作成済み）

- `trajectory_json`: thought + tool_calls + observations
- `reward`, `judge_score`, `human_score`, `used_for_training`

### 4.4 `intervention_efficacy` 拡張

- `predicted_outcome` / `actual_outcome` 列を追加し reward shaping に利用。

---

## 5. 新規コンポーネント

| コンポーネント | 配置 | 責務 |
|--------------|------|------|
| `FeedbackCollector` | `services/brain/src/feedback/collector.py` | 各種信号の正規化・永続化（Phase 1 から拡張） |
| `TrajectoryJudge` | `services/brain/src/feedback/trajectory_judge.py` | LLM-as-Judge + 確定ルールで軌跡評価 |
| `PreferenceBuilder` | `services/brain/src/feedback/preference_builder.py` | chosen/rejected ペア生成 |
| `PolicyUpdater` | `services/brain/src/feedback/policy_updater.py` | few-shot / LoRA / SFT 更新 |
| `RewardModelTrainer` | `services/brain/src/feedback/reward_trainer.py` | reward model 学習（必要なら） |
| `FeedbackAPI` | `services/backend/routers/feedback.py` | Frontend からのフィードバック受付（Phase 1 から拡張） |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/routers/feedback.py` — フィードバック受付（Phase 1 から拡張）

### 6.2 Brain

- `services/brain/src/feedback/collector.py` — 完成
- `services/brain/src/feedback/trajectory_judge.py` — 新規
- `services/brain/src/feedback/preference_builder.py` — 新規
- `services/brain/src/feedback/policy_updater.py` — 新規
- `services/brain/src/event_store/writer.py` — `record_feedback`, `record_trajectory` 完成
- `services/brain/src/llm_router.py` — adapter 動的ロード
- `services/brain/src/brain_cognitive.py` — サイクル終了時に軌跡保存・judge 呼び出し
- `services/brain/src/main.py` — コンポーネント wire

### 6.3 Frontend

- `services/frontend/src/components/FeedbackButtons.tsx` — 完成

### 6.4 依存

- 必須: `trl`, `peft`, `datasets`, `transformers`
- 推奨: `distilabel`, `argilla`, `deepeval`
- 任意: `OpenRLHF`, `vLLM`

---

## 7. 実装ステップ

### Step 1: TrajectoryJudge（2 週間）

1. `TrajectoryJudge` を実装。
   - ローカル small LM（Qwen2.5-7B-Instruct / Ollama）で軌跡を評価。
   - HEMS 用ルーブリック: 安全性、無駄なアクションの少なさ、ユーザー選好の一致、エネルギー効率。
   - 確定ルール（safety violation 等）で即座に 0/1 reward を上書き。
2. 信頼度スコアを計算。

### Step 2: PreferenceBuilder（1.5 週間）

1. `PreferenceBuilder` を実装。
   - 同一 trigger に対する成功/失敗軌跡、または人間の good/bad 信号から chosen/rejected ペアを構築。
   - `distilabel` または自前ロジックでフォーマット変換。
2. ペアの質フィルタ（score 差が大きいものを優先）。

### Step 3: PolicyUpdater Phase 1 — Few-shot（1 週間）

1. 成功例を `prompt_variants` / few-shot 例として追加。
2. `system_prompt.py` / `persona_rewriter.py` が動的に few-shot を読み込む機構。
3. A/B 評価で効果を検証。

### Step 4: PolicyUpdater Phase 2 — LoRA adapter（3 週間）

1. `PolicyUpdater` に DPO/KTO/GRPO 学習パイプラインを実装。
   - `trl` + `peft` + QLoRA
   - 軽量モデル（7B 以下）を対象
2. 学習済み adapter を `~/.hems/adapters/` に保存。
3. Brain 起動時に最新 adapter を動的ロード。
4. adapter 切り替えは徐々に行い、A/B 監視。

### Step 5: Reward Model（Optional、2 週間）

1. `RewardModelTrainer` を実装（必要なら）。
   - 軽量な reward model を訓練し、PPO 用 baseline に。
2. 家庭環境では DPO/KTO/GRPO が優先なので、本 step は後回し可。

### Step 6: 統合テスト（2 週間）

1. 軌跡 → judge score → preference ペアのテスト。
2. few-shot 更新 → 応答変化テスト。
3. LoRA adapter 学習・ロード・A/B テスト。
4. Reward hacking 防止テスト。

---

## 8. 検証方法

```bash
# 1. TrajectoryJudge を手動実行
python -c "from feedback.trajectory_judge import TrajectoryJudge; import asyncio; asyncio.run(main())"

# 2. Preference ペア数を確認
sqlite3 services/brain/data/hems_brain.db "SELECT COUNT(*) FROM agent_trajectories WHERE reward IS NOT NULL"

# 3. LoRA adapter 学習
python services/brain/src/feedback/policy_updater.py --method dpo --adapter-id v1

# 4. adapter ロード後の応答テスト
curl -X POST http://localhost:8010/chat \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{"message": "部屋が暑い", "lora_adapter": "v1"}'

# 5. reward hacking 防止: safety violation で reward=0 が強制されることを確認
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| サンプル不足 | implicit feedback 活用、reward shaping で中間報酬 |
| Reward hacking | 多角的報酬、確定ルールで hard constraint |
| Catastrophic forgetting | LoRA adapter 分離、KL regularization |
| Judge バイアス | 複数 judge voting、人間校正サンプル |
| 計算コスト | 軽量モデル + QLoRA、夜間バッチ |
| 安全性劣化 | safety rules は学習対象外、承認モード維持 |

---

## 10. 工数感

- 合計: **12〜24 週間**（3〜6 ヶ月）
- Few-shot 更新から始め、LoRA adapter 学習は安定的に運用できてから本格化。

---

## 11. 次フェーズ接続

- Phase 5 は最終フェーズ。得られた学習結果は Phase 0〜4 の全コンポーネントに還元される。
- 特に `PolicyUpdater` は Phase 3 の `PromptOptimizer`、Phase 4 の `PolicyLearner` と統合される。
- adapter 学習結果は `RulePromoter` / `AckLearner` の汎用化にも活用。
