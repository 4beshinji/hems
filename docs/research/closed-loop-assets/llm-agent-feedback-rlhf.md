# llm-agent-feedback-rlhf — 閉 loop 学習アセット調査

## 概要

本トピックは、HEMS Brain の「観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定」という閉 loop を、LLM エージェントのフィードバックと強化学習（RLHF / RLAIF / DPO / GRPO）で強化するための知見・アセットを整理したものである。

現在の HEMS はすでに `RuleEngine` + `WorldModel` + `event_store` + `intervention_efficacy` + `RulePromoter` + `AckLearner` という形で「結果観測に基づく微調整」の萌芽を持つが、LLM 本体の重みやプロンプト戦略を継続的に更新する仕組みはない。本調査は、その橋渡しに必要な概念、論文、ツール、実装案、リスクを網羅的に示す。

## 核心概念

### 1. LLM エージェントにとけるフィードバック閉 loop

LLM エージェントの行動は通常「プロンプト → 生成 → 実行 → 観測」で終わる。閉 loop を完成させるには、次の 3 つの帰還を取得し意思決定に還元する必要がある。

- **結果帰還（Outcome Feedback）**: 行動後の環境変化から計測される reward（室温が下がった、タスクが完了したなど）。
- **人間帰還（Human Feedback）**: 利用者の明示的／暗黙的な選好（good/bad、取消し、再実行、スヌーズなど）。
- **AI 帰還（AI Feedback / RLAIF）**: 大きなモデルや専用 judge モデルが軌跡を評価し preference / score を与える。

### 2. RLHF（Reinforcement Learning from Human Feedback）

LLM を人間の選好に沿うよう調整する代表的パラダイム。

1. **SFT**: 教師ありで基本動作を学習。
2. **Reward Model**: 人間の preference ペアから scalar reward を予測するモデルを学習。
3. **Policy Optimization**: PPO などで LLM policy を reward 最大化方向に更新。

LLM エージェントに応用する際の違い:

- 通常の対話 RLHF は「1ターンの応答」が action。
- エージェント RLHF は「複数ツール呼び出しからなる軌跡（trajectory）」が action。
- reward は最終的なタスク成否だけでなく、行動列全体（过程）に与える Process Reward Model（PRM）が有効。

### 3. DPO（Direct Preference Optimization）

Rafailov ら（2023）が提案。reward model を省略し、preference データを直接 policy の分類問題として解く。

```
L_DPO = -log σ(β log π_θ(y_w|x) / π_ref(y_w|x) - β log π_θ(y_l|x) / π_ref(y_l|x))
```

HEMS 規模の個人運用では、reward model を別途保持・推論するコストを避けられる DPO／IPO／KTO 系が現実的。

### 4. GRPO（Group Relative Policy Optimization）

DeepSeekMath / DeepSeek-R1（2024-2025）で実用化。PPO の value model（critic）を廃止し、同一プロンプトに対する複数サンプルの報酬平均を baseline に用いる。

- メリット: 推論コスト・メモリ半減、長い CoT の学習に強い。
- デメリット: バイナリ／検証可能な reward が必要、家庭環境のような曖昧な reward には要工夫。

### 5. エージェント軌跡の報酬設計

HEMS のような家庭環境では reward 関数が曖昧。以下のハイブリッド設計が現実的。

| 信号源 | 例 | 信頼性 |
|---|---|---|
| 確定的検証 | デバイス状態変化、タスク完了フラグ、ルールマッチ | 高 |
| センサー変化 | 温度・湿度・CO2 の変化、生体指標 | 中（遅延・ノイズあり） |
| 人間の明示FB | ダッシュボードの 👍/👎、取り消し | 高（希少） |
| 人間の暗黙FB | スヌーズ、再スケジュール、ack 遅延 | 中（解釈が必要） |
| LLM-as-Judge | 強いモデルに軌跡評価させる | 中（コスト・バイアス） |

## 論文・先行研究

### 総説・サーベイ

- **A Survey of Reinforcement Learning from Human Feedback**  
  Kaufmann et al., 2023/2024, TMLR / arXiv:2312.14925  
  要点: RLHF の基礎から制御・ロボティクス・LLM まで包括。preference-based RL と AI/HITL feedback の位置づけを示す。  
  HEMS 応用: フィードバック種別の分類と、reward model / direct policy optimization の選択指針。

- **Personalization of Large Language Models: A Survey**  
  arXiv:2411.00027, 2024  
  要点: 個人ユーザーの選好に合わせた RLHF / personalization のサーベイ。  
  HEMS 応用: 単身者の個別選好を学習する枠組み。

- **A Survey on the Optimization of Large Language Model-based Agents**  
  arXiv:2503.12434, 2025  
  要点: LLM エージェントの計画・推論・記憶・適応を強化する手法を体系化。  
  HEMS 応用: ReAct サイクル内の各段階にどの最適化を入れるかのマッピング。

### 基礎・代表的論文

- **Training language models to follow instructions with human feedback（InstructGPT）**  
  Ouyang et al., NeurIPS 2022  
  要点: SFT → reward model → PPO という 3 段階 RLHF パイプラインを確立。  
  HEMS 応用: 基本パイプラインの理解。family/personal assistant としての整列。

- **Deep Reinforcement Learning from Human Preferences**  
  Christiano et al., 2017  
  要点: 比較 preference から reward model を学習し、RL で政策を最適化する先駆的研究。  
  HEMS 応用: 数値的に測れない「快適さ」などを preference 比輇で学習する発想。

- **Direct Preference Optimization: Your Language Model is Secretly a Reward Model**  
  Rafailov et al., NeurIPS 2023  
  要点: reward model 不要で preference データから直接 policy を最適化。  
  HEMS 応用: リソース制約下で最も現実的な重み更新手法。

- **DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models**  
  Shao et al., 2024  
  要点: GRPO を提案。value network を廃止し group 内相対報酬で advantage を推定。  
  HEMS 応用: 大規模 GPU がない個人環境で推論能力を向上させる可能性。

- **DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning**  
  DeepSeek-AI, 2025  
  要点: 少数の cold-start SFT + GRPO で長い CoT と自己検証を獲得。  
  HEMS 応用: 計画立案やルール生成の品質向上。ただし reward の検証可能性が前提。

- **RLAIF: Scaling Reinforcement Learning from Human Feedback with AI Feedback**  
  Lee et al., Google, 2023  
  要点: 人間の代わりに LLM が preference ラベルを生成する RLAIF。  
  HEMS 応用: 個人運用で人間ラベルが不足する課題を AI judge で補完。

- **Learning Reward Models from In-the-Wild Human Interactions**  
  arXiv（WildReward）, 2024-2025  
  要点: 自然対話から暗黙的フィードバックを抽出し reward model を学習。フィードバックの希少性（陽性 1%）とノイズを扱う。  
  HEMS 応用: ユーザーが「ありがとう」とは言わない家庭環境での implicit feedback 活用。

- **ARMAP: Scaling Autonomous Agents via Automatic Reward Modeling and Planning**  
  arXiv:2502.12130, 2025  
  要点: 強い LLM API に依存せず、環境内の成否軌跡から軽量な報酬モデルを学習し MCTS/reflexion と組み合わせる。  
  HEMS 応用: ローカル small LM で報酬モデルを蒸留し、Brain の計画に組み込む。

- **AgentRewardBench: Evaluating Automatic Evaluations of Web Agent Trajectories**  
  Lù et al., COLM 2025  
  要点: LLM-as-Judge の精度限界を実証（精度 70% 未満）。軌跡全体を見る judge の重要性。  
  HEMS 応用: AI judge のみに依存しない、人間確認・確定ルールを組み合わせた設計が必要。

- **Meta-Reward: Reward Modeling as Harness Optimization**  
  Sleiman, Canvas, 2026  
  要点: judge LLM は固定し、評価 harness（ルーブリック・手続き・構造化出力）を最適化することで judge 精度を向上。  
  HEMS 応用: 固定のローカル judge に対して評価プロンプトやチェックリストを DPO で調整。

## OSS・商用ツール・フレームワーク

### 強化学習・ファインチューニングフレームワーク

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **TRL** | https://huggingface.co/docs/trl | HuggingFace 公式。SFT / DPO / PPO / GRPO / Reward / KTO / ORPO を単一 GPU から分散までサポート。LoRA/QLoRA 標準。 | **最優先**。Ollama 連携や ONNX 変換後の軽量モデルにも適用可能。 |
| **OpenRLHF** | https://github.com/OpenRLHF/OpenRLHF | Ray + vLLM + DeepSpeed による分散 RLHF。70B 級も扱える。PPO / REINFORCE++ / GRPO / DAPO。 | 個人運用ではオーバースペック。研究段階やクラウドバースト時に検討。 |
| **verl** | https://github.com/volcengine/verl | ByteDance 系。分散 RL トレーニング。vLLM/SGLang 推論。 | OpenRLHF 代替。HEMS 規模では不要。 |
| **LLaMA-Factory** | https://github.com/hiyouga/LLaMA-Factory | YAML/CLI ベースの統合ファインチューニング。SFT/DPO/RLHF を手軽に。 | HEMS 固有データ形式への前処理が必要だが、小規模実験に最適。 |
| **Unsloth** | https://github.com/unslothai/unsloth | 高速 LoRA/QLoRA。メモリ効率が高い。 | 7B 級以下の継続学習に最適。 |

### フィードバック収集・AI judge フレームワーク

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **LangSmith** | https://smith.langchain.com | LLM アプリのトレース、人間注釈キュー、LLM-as-judge、dataset 化。 | 商用だが無料ティアあり。LangGraph 使用時に強力。HEMS は自前で同等機能を作るか、SDK 連携。 |
| **LangGraph** | https://github.com/langchain-ai/langgraph | 状態付きグラフエージェント。HITL 中断・再開が組み込み。 | Brain の ReAct loop をグラフ化する際に参考。既存 Brain 置き換えは大工事。 |
| **agentevals** | https://github.com/langchain-ai/agentevals | LangChain 謹製。trajectory match / LLM-as-judge evaluator。 | HEMS の action 軌跡評価に流用可能。 |
| **DeepEval** | https://github.com/confident-ai/deepeval | pytest スタイルのローカル LLM eval。G-Eval、正解性、幻覚等 50+ メトリクス。 | CI 組み込みが容易。テスト資産として有用。 |
| **Ragas** | https://github.com/explodinggradients/ragas | RAG 品質評価中心。参照不要メトリクス。 | RAG 検索品質の自動評価に。 |
| **Arize Phoenix** | https://github.com/Arize-ai/phoenix | OTel 対応トレース＋eval。セルフホスト可能。 | 自前トレース基盤の代替または併用。 |
| **Braintrust** | https://www.braintrust.dev | eval-first な評価基盤。autoevals 強力。 | 商用。小規模なら無料ティアで運用可能。 |

### データセット・AI Feedback 構築

| 名前 | URL | 特徴 | HEMS への流用可否 |
|---|---|---|---|
| **distilabel** | https://github.com/argilla-io/distilabel | AI Feedback（AIF）フレームワーク。preference データセット構築、reward model、DPO データ生成。 | 推奨。HEMS の軌跡を preference ペアに変換するパイプラインとして活用。 |
| **Argilla** | https://github.com/argilla-io/argilla | 人間注釈 UI。フィードバック収集と dataset 管理。 | ダッシュボードに組み込むか、別 UI として利用。 |
| **OpenPipe** | https://openpipe.ai | プロダクションログからファインチューニングデータセットを作成。 | 商用だが、HEMS の対話ログを SFT/DPO データに変換する参考。 |

## HEMS への適用案

### 1. 位置づけ: 既存ループを拡張する形

現在の HEMS ループ:

```
MQTT 観測 → WorldModel 更新 → ReAct/RuleEngine → 実行 → event_store/intervention_efficacy → RulePromoter/AckLearner
```

追加する層:

```
LLM decision trace → FeedbackCollector → Preference/Trajectory DB → Reward Model / DPO trainer → LoRA adapter / prompt diff
                                    ↑___________________________________________|
```

重み更新はオプション。まずは「軌跡記録 + 人間／AI 評価 + few-shot プロンプト更新」から始め、軽量 DPO/GRPO は後続とする。

### 2. フィードバック取得ポイント

| HEMS コンポーネント | 取得できる信号 | 活用方法 |
|---|---|---|
| **Backend / Frontend** | 👍/👎、取り消し、再実行、編集 | 明示 preference。reward ±1 に相当。 |
| **voice-service / mobile-android** | ack 遅延、スヌーズ、reject | 暗黙 preference。AckLearner と連携。 |
| **intervention_efficacy** | baseline → post_value, verdict | 結果帰還。action が実際に環境を改善したか。 |
| **event_store.llm_decisions** | tool_calls, world_state_snapshot | 軌跡全体。trajectory-level reward / judge 評価の材料。 |
| **RulePromoter / ClassifierCache** | hit_count, source=promoted | 頻出パターンの教師データ化。 |
| **MQTT sensors** | センサー変化、安定時間 | reward shaping に用いる中間報酬。 |

### 3. 新規コンポーネント案

#### `FeedbackCollector`（services/brain/src/feedback/collector.py）

- 各種信号を正規化し `agent_feedback` テーブルへ書き込む。
- 信号の種別（explicit, implicit, outcome, ai_judge）と信頼度スコアを付与。
- 30 秒サイクル終了時に LLM decision trace と紐付ける。

#### `TrajectoryJudge`（services/brain/src/feedback/trajectory_judge.py）

- ローカル small LM（例: Qwen2.5-7B-Instruct または Ollama 上のモデル）で軌跡を評価。
- HEMS 用ルーブリック: 安全性、無駄なアクションの少なさ、ユーザー選好の一致、エネルギー効率。
- 確定ルール（safety violation など）で即座に 0/1 reward を上書き。

#### `PreferenceDatasetBuilder`（services/brain/src/feedback/preference_builder.py）

- 同一 trigger に対する成功／失敗軌跡、または人間の good/bad 信号から chosen/rejected ペアを構築。
- distilabel または自前ロジックでフォーマット変換。

#### `PolicyUpdater`（services/brain/src/feedback/policy_updater.py）

- 3 段階の更新戦略を切り替える。
  1. **Prompt-level**: 成功例を few-shot 例として追加（LlamaIndex/テンプレート更新）。
  2. **LoRA adapter**: DPO/KTO/GRPO で軽量 adapter を学習し、推論時に動的ロード。
  3. **Full SFT**: 大規模データが集まったら TRL で本格的 fine-tuning（オプション）。

### 4. スキーマ変更案

#### `events.agent_feedback` 新規テーブル

```sql
CREATE TABLE events.agent_feedback (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decision_id BIGINT REFERENCES events.llm_decisions(id),
    trigger_event_id BIGINT REFERENCES events.world_events(id),
    feedback_type TEXT NOT NULL,      -- explicit_like, explicit_dislike, implicit_snooze, implicit_ack_delay, outcome_verdict, ai_judge
    source TEXT NOT NULL,             -- frontend, voice, mobile, intervention_efficacy, trajectory_judge
    score REAL,                       -- -1.0 ~ 1.0 または NULL
    confidence REAL NOT NULL DEFAULT 1.0,
    rationale TEXT,
    payload JSONB NOT NULL DEFAULT '{}'
);
```

#### `events.agent_trajectories` 新規テーブル

```sql
CREATE TABLE events.agent_trajectories (
    id BIGSERIAL PRIMARY KEY,
    decision_id BIGINT REFERENCES events.llm_decisions(id),
    prompt_hash TEXT NOT NULL,
    trajectory_json JSONB NOT NULL,   -- thought + tool_calls + observations の列
    reward REAL,
    judge_score REAL,
    human_score REAL,
    used_for_training BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `events.intervention_efficacy` 拡張

- `llm_decision_id` 外部キーを追加し、行動 → 結果の因果を追跡。
- `predicted_outcome` / `actual_outcome` 列を追加し reward shaping に利用。

### 5. 既存コンポーネントとの統合

- **RulePromoter**: `classifier_cache` の昇格条件に「人間／AI 評価が高い」ことを加え、頻出かつ好ましいパターンをルール化。
- **AckLearner**: 暗黙的拒否信号を `FeedbackCollector` に流し、reminder 系 action の reward 計算に利用。
- **intervention_efficacy**: 行動後の環境変化を `PolicyUpdater` の outcome reward として供給。
- **event_store**: `llm_decisions` と `world_events` を結合して軌跡を再構成。
- **Backend AutomationRule**: 新規 `automation_rules` テーブルに学習済み rule 候補を保存し、ユーザー承認フローを追加。

## 実装に必要なアセット

### データ

1. **成否ラベル付き decision 履歴**: 最低数百〜数千件。
2. **Preference ペア**: 同一状況で chosen/rejected となった軌跡のペア。最低数十〜数百件で DPO 可能。
3. **ルーブリック定義**: HEMS 用の judge 評価基準（安全性、効率、静寂性、省エネ、快適性）。
4. **検証可能な報酬関数**: 温度変化、タスク完了、デバイス状態変化など、自動で正誤判定できるメトリクス。

### スキーマ変更

- `events.agent_feedback` 新設。
- `events.agent_trajectories` 新設。
- `events.llm_decisions` に `prompt_template_version`、`policy_version`、`lora_adapter_id` を追加。
- `events.intervention_efficacy` に `llm_decision_id` と予測/実績カラムを追加。

### 新規コンポーネント

| コンポーネント | 責務 | 置き場所 |
|---|---|---|
| `FeedbackCollector` | 各種信号の正規化・永続化 | `services/brain/src/feedback/collector.py` |
| `TrajectoryJudge` | 軌跡評価（LLM-as-Judge + 確定ルール） | `services/brain/src/feedback/judge.py` |
| `PreferenceBuilder` | chosen/rejected ペア生成 | `services/brain/src/feedback/preference_builder.py` |
| `PolicyUpdater` | few-shot / LoRA / SFT 更新 | `services/brain/src/feedback/policy_updater.py` |
| `RewardModelTrainer` | reward model 学習（必要なら） | `services/brain/src/feedback/reward_trainer.py` |
| `FeedbackAPI` | Frontend からのフィードバック受付 | `services/backend/routers/feedback.py` |

### 外部依存

- **必須**:
  - `trl`（DPO/KTO/GRPO trainer）
  - `peft`（LoRA adapter 管理）
  - `datasets`（HuggingFace datasets 形式）
  - `transformers`（推論・重み更新）
- **推奨**:
  - `distilabel`（AI Feedback パイプライン）
  - `argilla`（人間注釈 UI）
  - `deepeval`（ローカル評価）
- **任意**:
  - `OpenRLHF`（分散大規模学習）
  - `vLLM`（学習時高速推論）

### 実行フロー例

1. Brain の 30 秒サイクルで decision trace を `events.llm_decisions` + `events.agent_trajectories` に保存。
2. ユーザーがダッシュボードで 👍/👎 → `FeedbackCollector` が `events.agent_feedback` へ。
3. `intervention_efficacy` の評価期限が来たら outcome reward を計算。
4. `TrajectoryJudge` が未評価軌跡をバッチ評価。
5. `PreferenceBuilder` が一定量のペアを構築。
6. 日次／週次バッチで `PolicyUpdater` が LoRA adapter を学習し、`~/.hems/adapters/` に保存。
7. Brain 起動時に最新 adapter を動的ロード。adapter 切り替えは徐々に行い A/B 監視。

## リスク・検討事項

### 技術リスク

| リスク | 内容 | 対策 |
|---|---|---|
| **サンプル不足** | 家庭環境では positive/negative ペアが不足しがち | implicit feedback（ack 遅延、再実行）も利用。reward shaping で中間報酬を与える。 |
| **Reward hacking** | LLM が reward 指標を騙す行動に偏る | 多角的報酬（安全性、効率、人間評価）を組み合わせ、確定ルールで hard constraint を設ける。 |
| **遅延した帰還** | 行動と結果の因果が時間を空けて現れる | `intervention_efficacy` の window_sec を可変にし、time-discounted reward を採用。 |
| **Catastrophic forgetting** | ファインチューニングで汎用能力が失われる | LoRA adapter を分離し、KL regularization / reference model を保持。 |
| **Judge のバイアス・コスト** | LLM-as-Judge は長さバイアスや位置バイアスを持つ | 複数 judge の voting、人間校正サンプル、確定ルールによる上書き。 |
| **計算コスト** | DPO/GRPO も GPU を消費する | 軽量モデル（7B 以下）+ QLoRA。学習は夜間バッチ。推論は Ollama/GGUF で維持。 |
| **アクションの安全性** | 学習した policy が危険なデバイス操作を提案 | safety rules は常に上位に置き、学習対象外の hard guardrail を維持。 |

### 運用・倫理

- **透明性**: 学習によって変更されたプロンプト／ルールは Obsidian `HEMS/learnings/` に記録し、ユーザーが監査可能にする。
- **制御権**: 学習したルールは自動適用ではなく「提案」として提示し、ユーザー承認後に有効化。
- **プライバシー**: preference データはローカル SQLite/Postgres に留め、クラウド学習を行う場合は anonymization / differential privacy を検討。
- **バージョニング**: policy version と LoRA adapter version を明示し、ロールバック可能にする。

### 妥協点・段階的アプローチ

1. **Phase 0（現在）**: `intervention_efficacy` + `RulePromoter` + `AckLearner` を拡張し、軌跡記録と明示フィードバックを追加するのみ。
2. **Phase 1（数週間後）**: `TrajectoryJudge` を導入し、AI judge での自動評価と人間確認キューを回す。
3. **Phase 2（数か月後）**: `PreferenceBuilder` + DPO/LoRA で adapter 学習を試験。影響の小さい reminder ・chat 応答から始める。
4. **Phase 3（安定的に運用できてから）**: GRPO や reward model による大規模 policy 更新を検討。

## 参考リンク

### 論文

- A Survey of Reinforcement Learning from Human Feedback: https://arxiv.org/abs/2312.14925
- Training language models to follow instructions with human feedback: https://arxiv.org/abs/2203.02155
- Deep Reinforcement Learning from Human Preferences: https://arxiv.org/abs/1706.03741
- Direct Preference Optimization: https://arxiv.org/abs/2305.18290
- DeepSeekMath / GRPO: https://arxiv.org/abs/2402.03300
- DeepSeek-R1: https://arxiv.org/abs/2501.12948
- RLAIF: https://arxiv.org/abs/2309.00267
- ARMAP: https://arxiv.org/abs/2502.12130
- AgentRewardBench: https://arxiv.org/abs/2501.03256
- Meta-Reward: https://www.canvas.inc/research/reward-models

### OSS / フレームワーク

- TRL: https://huggingface.co/docs/trl
- OpenRLHF: https://github.com/OpenRLHF/OpenRLHF
- verl: https://github.com/volcengine/verl
- LLaMA-Factory: https://github.com/hiyouga/LLaMA-Factory
- Unsloth: https://github.com/unslothai/unsloth
- distilabel: https://github.com/argilla-io/distilabel
- Argilla: https://github.com/argilla-io/argilla
- LangSmith: https://smith.langchain.com
- LangGraph: https://github.com/langchain-ai/langgraph
- agentevals: https://github.com/langchain-ai/agentevals
- DeepEval: https://github.com/confident-ai/deepeval
- Ragas: https://github.com/explodinggradients/ragas
- Arize Phoenix: https://github.com/Arize-ai/phoenix
- OpenPipe: https://openpipe.ai

### 解説・調査

- Hugging Face RLHF blog: https://huggingface.co/blog/rlhf
- DataCamp RLAIF: https://www.datacamp.com/blog/rlaif-reinforcement-learning-from-ai-feedback
- Restack AI feedback loop: https://www.restack.io/p/reinforcement-learning-answer-ai-feedback-loop-cat-ai

---

*調査日: 2026-06-30*
*トピック: llm-agent-feedback-rlhf*
*対象リポジトリ: /home/sin/code/agent/auto/hems*
