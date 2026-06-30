# automated-rule-prompt-learning 調査報告

## 概要

**automated-rule-prompt-learning** とは、HEMS のようなパーソナル AI ホームアシスタントが「観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定」という閉ループを回すために必要な、以下 3 層の学習を統合する領域である。

1. **ルール（閾値・自動化）の自動学習**: ユーザー行動・センサ履歴・介入結果から、IF-THEN 型のルールや閾値を発見・更新する。
2. **プロンプトの自動最適化**: LLM（ReAct エージェント）が使う system prompt、few-shot 例、instruction を継続的に改善する。
3. **人間介入（feedback）からの学習**: ユーザーの取消し、承認、手動操作、遅延評価を報酬信号に変換し、ルール・プロンプトの双方を更新する。

本調査では、学術論文・OSS・商用ツール・フレームワークを網羅し、HEMS 既存アーキテクチャ（MQTT、FastAPI backend、Python brain、event_store、`RuleThresholds`、`AutomationRule`、`RulePromoter`/`AckLearner`、`intervention_efficacy`）への組み込み案と、実装に必要なスキーマ変更・新規コンポーネント・リスクを整理する。

## 核心概念

### 解くべき問題

- **静的ルールの陳腐化**: `RuleThresholds` や `AutomationRule` は手動設定または初期値に固定されており、季節変動、生活リズム変化、新デバイス追加に追従できない。
- **プロンプトの手動チューニング**: `system_prompt.py` や `persona_rewriter.py` の調整は経験依存で、モデル変更（OpenAI → Ollama 等）で再調整が必要。
- **介入の効果測定の不足**: LLM/ルールがデバイスを動かしても、本当に快適性・省エネ・健康指標が改善したかを閉ループで評価する仕組みが限定的（`intervention_efficacy` は環境タスクのみ対象）。
- **ユーザー意図の希薄なフィードバック**: 承認／取消しのログはあるが、それをルール重みやプロンプト例に還元する仕組みが未整備。

### 目指す状態

観測データと人間フィードバックをもとに、以下を自律的に更新する HEMS。

- センサ閾値（`RuleThresholds` の各種 `*_high` / `*_low`）の適応。
- `AutomationRule` のトリガ条件、アクション、クールダウン、モード（direct / llm_review）の提案・生成・A/B 評価。
- LLM への system prompt / few-shot / CoT instruction の自動生成・選択。
- 介入効果（`intervention_efficacy`）に基づくルール信頼度の上下。

### 主要技術パターン

| パターン | 内容 | HEMS 利用例 |
|---------|------|------------|
| 自動プロンプト工学（APE / OPRO / DSPy） | 入力・出力例から最適な instruction / few-shot を生成・選択する | system prompt / `llm_review` prompt の自動改善 |
| ルール学習（Association Rule / Decision List） | センサ・デバイス状態の頻出パターンから IF-THEN ルールを発見 | `AutomationRule` の新規提案、閾値調整 |
| 強化学習 / Contextual Bandit | 人間フィードバックを報酬として方策・パラメータを更新 | 照明・エアコンの設定温度、カーテン開閉の好み学習 |
| 人間介入型学習（TAMER / RLHF） | ユーザーからの承認・取消しをスカラー報酬に変換 | 介入の効果・ユーザー承認率をルール重みに反映 |
| タスク記憶・プリファレンス抽象化 | 過去の指示と補正を階層的に記憶し、デバイス非依存の好みを転用 | IoTGPT 型の few-shot 蓄積、voice capsule / scene 推薦 |

## 論文・先行研究

### 自動プロンプト最適化

| 論文 | 著者・年 | 要点 | HEMS 応用 |
|------|---------|------|-----------|
| **Large Language Models Are Human-Level Prompt Engineers** (APE) | Yongchao Zhou et al., ICLR 2023 | 入出力例から LLM が複数 instruction 候補を生成し、ターゲットモデルで評価して最良を選択。「Let's work this out in a step by step way...」を自動発見。 | ReAct system prompt の instruction 自動生成・A/B テスト。`llm_review` 用の「fire/skip 判断」プロンプト最適化。 |
| **Large Language Models as Optimizers** (OPRO) | Chengrun Yang et al., Google DeepMind, 2023 | 履歴 prompt とそのスコアを LLM に入力し、より良い prompt を反復生成（LLM-as-optimizer）。 | prompt の「進化的」最適化。過去の cycle ごとの介入効果スコアを使って system prompt を更新。 |
| **DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines** | Omar Khattab et al., Stanford, 2023 | Signature + Module + Optimizer（BootstrapFewShot, COPRO, MIPRO）でプロンプトを「コンパイル」。 | HEMS の LLM ツール呼び出しパイプラインを DSPy module 化し、few-shot 例を自動選定。 |
| **Automatic Prompt Optimization with "Gradient Descent" and Beam Search** (APO) | Reid Pryzant et al., EMNLP 2023 | 自然言語上の「擬似勾配」とビームサーチで prompt を最適化。 | 日本語 prompt に対する局所改良。 |

### スマートホーム・ルール学習

| 論文 | 著者・年 | 要点 | HEMS 応用 |
|------|---------|------|-----------|
| **An Interaction-Centric Dataset for Learning Automation Rules in Smart Homes** | Kai Frederic Engelmann et al., LREC 2016 | 59 ユーザー・5 タスクのセンサ・アクチュエータイベントを収録し、行動から自動化ルールを学習するためのコーパス。 | HEMS event_store の `raw_events` を類似コーパス化し、ルール発見の教師データに。 |
| **Generating HomeAssistant Automations Using an LLM-based Chatbot** (EcoMate) | Giudici et al., arXiv 2025 | HomeAssistant 自動化 JSON を LLM 対話で生成。GPT-4 が JSON 正当性で最高、Hallucination と即時/継続命令の混同が課題。 | HEMS frontend の AutomationEditor への LLM 生成支援、`AutomationRule` JSON 生成。 |
| **Leveraging LLMs for Efficient and Personalized Smart Home Automation** (IoTGPT) | Yu et al., 2026 (arXiv:2601.04680) | Decompose–Derive–Refine パイプライン + 階層的タスク記憶 + EUPont オントロジーに基づく環境プロパティ抽象化。人間補正でタスク記憶・偏好テーブルを更新。 | HEMS ReAct の tool 呼び出しを subtask 単位で記憶。温度・明るさ・湿度などを「環境プロパティ」として抽象化し、デバイス変更時も偏好を転用。 |
| **Sasha: An LLM-based Goal-oriented Home Automation** | King et al. (Giudici et al. 引用) | 自然言語目標を JSON action plan に変換。 | HEMS の「目的 → デバイス操作」変換のベースライン。 |
| **SAGE: LLM-based Smart Home Agent** | prior work (IoTGPT 比較対象) | 動的推論モジュール選択 + 過去のデバイス操作履歴からのパーソナライズ。 | ユーザーの過去操作履歴を retrieve して few-shot に追加。 |
| **Automatic Trigger Generation for Rule-based Smart Homes** | Chinmaya Nandi et al., PLAS 2016 | ユーザーのルールに不足しているトリガを静的解析で追加。 | `AutomationRule` の trigger_config 検証・不足トリガー提案。 |
| **Hybrid Prompt Learning for Generating Justifications of Security Risks in Automation Rules** | ACM 2024 | TAP（Trigger-Action Programming）ルールのセキュリティリスク説明生成。 | 学習によって生成されたルールの安全性説明・コンフリクト検知。 |

### 強化学習・人間介入型学習

| 論文 | 著者・年 | 要点 | HEMS 応用 |
|------|---------|------|-----------|
| **TAMER: Training an Agent Manually via Evaluative Reinforcement** | W. Bradley Knox & Peter Stone, 2008 | 人間が良い/悪いスカラー報酬を与え、エージェントが人間の報酬関数をモデル化。 | ユーザーが「いいね/取消し」ボタンや音声「違うよ」を与え、ルール重みを更新。 |
| **User Involvement in Training Smart Home Agents** | Sieger et al., HAI 2022 | SL（教師ありラベル付け）と RL（フィードバック）のユーザ受容性を比較。RL の方が「コントロール感」が高いとの結果。 | 学習フェーズの UI/UX 設計。ユーザーの自律感を損なわない feedback フロー。 |
| **User in the Loop: Adaptive Smart Homes Exploiting User Feedback** | MDPI Information 2016 | 明示・暗黙フィードバックを組み合わせた adaptive smart home のサーベイ。 | フィードバック収集設計（暗黙: 手動上書き、明示: 評価）。 |
| **Deep Reinforcement Learning for Home Energy Management System Control** | P. Lissa et al., Energy Reports 2021 | DRL で HVAC 制御、ルールベース比 8% 省エネ。 | エアコン・照明の設定温度・輝度を RL で最適化。 |
| **Multi-Agent-Based Smart-Home Energy Management with Adaptive Reasoning** | Dolinin et al., Appl. Sci. 2026 | LLM エージェント + 強化学習による multi-agent 制御。Contextual bandit で温度・明るさ偏好を学習。 | HEMS brain の「環境調整」タスクを contextual bandit で最適化。 |

### 行動予測・個人化

| 論文 | 著者・年 | 要点 | HEMS 応用 |
|------|---------|------|-----------|
| **Personalized Smart Home Automation Using Machine Learning: Predicting User Activities** (EL-HARP) | Gad et al., Sensors 2025 | Gradient boosting（XGBoost/CatBoost/LightGBM）でユーザ活動を予測。Raspberry Pi 5 上で継続学習。 | `raw_events` からユーザ活動を予測し、proactive な scene 実行・ルール提案。 |
| **Reinforcement Learning in Home Energy Management Systems: A Review** | Zhang et al., IEEE Access 2020 | HEMS 向け RL アルゴリズムの包括レビュー。 | アルゴリズム選定（Q-learning, DQN, PPO, SAC）の指針。 |
| **Reinforcement Learning-Based Approaches for Security and Resilience in Smart Control** | Zhang et al., arXiv 2024 | RL 制御システムへの敵対的攻撃と防御のサーベイ。 | 学習したルールに対する adversarial 入力・セキュリティ設計。 |

## OSS・商用ツール・フレームワーク

### 自動プロンプト最適化

| 名前 | URL | 特徴 | HEMS 流用可否 |
|------|-----|------|--------------|
| **DSPy** | https://github.com/stanfordnlp/dspy | Signature/Module/Optimizer による宣言的 LLM パイプライン。BootstrapFewShot、COPRO、MIPRO 等。 | **高**。ReAct tool 呼び出しを module 化し、介入効果に応じた metric でコンパイル。依存増加と学習曲線が課題。 |
| **APE 公式実装** | https://github.com/keirp/automatic_prompt_engineer | Zhou et al. 論文の実装。入出力例から instruction 生成・評価。 | **中**。system prompt instruction 生成に軽量に組み込める。検索空間が大きい場合コスト高。 |
| **DSPy-HELM** | https://github.com/StanfordMIMI/dspy-helm | HELM ベンチマーク向け DSPy プロンプト最適化。 | **中（参考）**。評価基準の設計例として有用。 |
| **MARS** | 論文 + GitHub | Socratic guidance による multi-agent prompt optimization。 | **低〜中**。研究者向け。HEMS への直接的流用は過剰。 |

### スマートホーム・ルール学習

| 名前 | URL | 特徴 | HEMS 流用可否 |
|------|-----|------|--------------|
| **Home Assistant** | https://www.home-assistant.io/ | 最大 OSS スマートホームプラットフォーム。自動化 YAML/blueprint、adaptive-lighting 等。 | **高**。`AutomationRule` スキーマとの互換性検討、blueprint 形式の参考。 |
| **HA-Architect** | Home Assistant Community | ローカル LLM Add-on。実体レジストリを SQLite に保存し、YAML 生成を人間が承認。 | **高**。HEMS frontend への LLM rule ドラフト生成 UI の参考。 |
| **openHAB** | https://www.openhab.org/ | Java ベース OSS ホームオートメーション。 | **低**。ルール記述パラダイムの参考。 |
| **Adaptive Lighting (HACS)** | https://github.com/basnijholt/adaptive-lighting | 太陽位置に応じた照明輝度・色温度の適応。手動上書きを検出。 | **高**。HEMS circadian/absence lighting と連携・学習への参考。 |

### 強化学習・ML

| 名前 | URL | 特徴 | HEMS 流用可否 |
|------|-----|------|--------------|
| **Stable-Baselines3** | https://github.com/DLR-RM/stable-baselines3 | PPO, SAC, DQN 等の実装。 | **中**。エネルギー制御や偏好学習に使用可。ただし軽量エッジ向けでは要注意。 |
| **scikit-learn / XGBoost / LightGBM** | 各公式 | 行動予測、ルール重要度、異常検知。 | **高**。`EL-HARP` と同様に、活動予測モデルのベース。 |
| **mlxtend** | https://rasbt.github.io/mlxtend/ | Apriori / FP-Growth による association rule mining。 | **高**。センサ・デバイス状態の共起パターン発見に最適。 |
| **Bayesian Rule Lists (BRL)** | letham / imodels 等 | 解釈可能なルールリストをベイズ学習。 | **中**。生成ルールの解釈性を高めたい場合に有効。 |

### データ・ベクトル・フィードバック基盤

| 名前 | URL | 特徴 | HEMS 流用可否 |
|------|-----|------|--------------|
| **LangSmith / Langfuse** | 各公式 | LLM トレース、評価、フィードバック収集。 | **中**。ReAct cycle の tracing とプロンプト改善ループ。ただし自己完結が HEMS 精神。 |
| **Weights & Biases** | https://wandb.ai | 実験管理、prompt バージョニング。 | **低〜中**。研究段階での A/B 管理。 |

## HEMS への適用案

### アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────────────────────┐
│  HEMS Brain (Python)                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ RuleEngine   │  │ ReAct / LLM  │  │ AutomationEngine         │  │
│  │ (threshold)  │  │ (prompt)     │  │ (backend AutomationRule) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                 │                      │                  │
│         ▼                 ▼                      ▼                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Learning Orchestrator (新規)                    │  │
│  │  - RuleLearner (association / classifier / RL)               │  │
│  │  - PromptOptimizer (APE/DSPy/BootstrapFewShot)               │  │
│  │  - FeedbackCollector (ack / dismiss / override / efficacy)   │  │
│  │  - RulePromoter (既存) / AckLearner (既存) 拡張              │  │
│  └───────────────────────┬──────────────────────────────────────┘  │
│                          │                                          │
│                          ▼ MQTT / HTTP                              │
┌─────────────────────────────────────────────────────────────────────┤
│  Backend (FastAPI) + DB (SQLite/Postgres)                           │
│  - AutomationRule, ClassifierCache, Task, DeviceActionLog           │
│  - intervention_efficacy (event_store)                              │
│  - learned_rules / prompt_variants / feedback_log (新規テーブル)    │
└─────────────────────────────────────────────────────────────────────┘
```

### 既存コンポーネントとの接続

| 既存コンポーネント | 現在の役割 | 学習への接続案 |
|-------------------|-----------|---------------|
| `RuleThresholds` (`rules/config.py`) | 環境・生体・PC 等の固定閾値 | 各閾値に「学習対象フラグ」と「適応幅（±Δ）」を持たせ、過去の発火結果と介入効果から勾配 or bandit で更新。 |
| `AutomationRule` (`backend/models.py`) | backend 永続化ルール | `source` 列を追加し `seed | llm_generated | user | learned | promoted` を管理。生成ルールは初期 `enabled=false`（proposed）で人間承認後 activated。 |
| `RuleEngine` (`brain/src/rule_engine.py`) | GPU 高負荷時のルールベース fallback | 学習した閾値を即座に反映。発火履歴・効果を `RuleLearner` に返送。 |
| `AutomationEngine` (`brain/src/automation_engine.py`) | backend rule の定期評価 | 発火ごとに `fire_count` + ユーザー override 率を記録。`llm_review` の prompt を `PromptOptimizer` が最適化。 |
| `RulePromoter` (`brain/src/annotator/rule_promoter.py`) | `ClassifierCache` source=llm → promoted | 対象を拡張: `AutomationRule` 候補、`RuleThresholds` 変更、`prompt_variant` も promote 可能に。 |
| `AckLearner` (`brain/src/voice_capsule/ack_learner.py`) | voice capsule のリードタイム調整 | 同じ枠組みで「ユーザー承認/取消し」からルール重みを更新する `FeedbackLearner` を新設 or 統合。 |
| `intervention_efficacy` (`event_store/database.py`) | 環境タスクの前後効果測定 | 対象を全デバイス制御・scene 実行に拡大。`verdict=effective/counterproductive/inconclusive` をルール信頼度に反映。 |
| `event_store.raw_events` | 全イベント履歴 | ルール学習の教師データソース。時間帯・曜日・在室・天気を特徴量に。 |
| `DeviceActionLog` (`backend/models.py`) | デバイス操作ログ | 学習したルールの発火結果と、ユーザーによる直後の手動上書きを紐付けて評価。 |

### 提案する学習ループ

1. **データ収集**: `raw_events` + `DeviceActionLog` + `intervention_efficacy` + `ClassifierCache` hit_count + ユーザー承認/取消しを集約。
2. **候補生成**: 定期的（例: 毎日夜）に `RuleLearner` を実行し、
   - association rule mining で「条件 X → アクション Y」候補を発見、
   - LLM で自然言語 description と `trigger_config`/`actions` JSON を生成。
3. **人間レビュー**: frontend の AutomationEditor に「提案ルール」として表示。承認されると `source=learned` で enabled。
4. **A/B 評価**: 承認されたルールは `fire_count`・override 率・介入効果を記録。効果が悪ければ `confidence` 下降 or 無効化。
5. **プロンプト更新**: 成功例・失敗例を few-shot 例として蓄積。`PromptOptimizer` が `llm_review` 用 prompt をコンパイル。
6. **閾値適応**: `RuleThresholds` 内の学習対象パラメータを、季節・快適性フィードバックに応じて調整。

## 実装に必要なアセット

### 新規データスキーマ（backend / event_store）

```python
# backend/models.py への追加案

class LearnedRuleCandidate(Base):
    """RuleLearner が生成した、人間承認待ちのルール候補。"""
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
    evidence_json = Column(Text)  # 生成根拠（出現頻度、支持例、metrics）
    proposed_at = Column(TZDateTime(timezone=True), server_default=func.now())
    decided_at = Column(TZDateTime(timezone=True), nullable=True)
    decide_reason = Column(String, nullable=True)

class PromptVariant(Base):
    """system prompt / llm_review prompt の variant と評価結果。"""
    __tablename__ = "prompt_variants"
    id = Column(Integer, primary_key=True)
    target = Column(String, nullable=False, index=True)  # system_prompt | llm_review | ...
    variant_hash = Column(String, nullable=False, index=True)
    prompt_text = Column(Text, nullable=False)
    source = Column(String, default="ape")  # ape | human | dspy
    active = Column(Boolean, default=False)
    win_rate = Column(Float, nullable=True)  # A/B metric
    sample_count = Column(Integer, default=0)
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())

class RuleFeedback(Base):
    """ユーザーからの明示・暗黙フィードバック。"""
    __tablename__ = "rule_feedback"
    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("automation_rules.id"), nullable=True)
    candidate_id = Column(Integer, ForeignKey("learned_rule_candidates.id"), nullable=True)
    feedback_type = Column(String, nullable=False)  # accept | reject | override | implicit_satisfied | implicit_unsatisfied
    context_json = Column(Text)  # 時刻、zone、センサ値、アクション
    reward = Column(Float, nullable=True)  # -1 .. 1
    created_at = Column(TZDateTime(timezone=True), server_default=func.now())
```

`event_store/database.py` の `intervention_efficacy` を拡張:

- `task_id` → `action_id` (rule_id or scene execution id)
- `action_kind` 列追加 (`rule` | `scene` | `llm_task`)
- `user_override_within_window` 列追加（ユーザーが window 内に手動で戻したか）

### 新規コンポーネント

| コンポーネント | 配置 | 役割 |
|--------------|------|------|
| `RuleLearner` | `services/brain/src/learning/rule_learner.py` | association rule mining / classifier / クラスタリングで候補ルール生成。 |
| `PromptOptimizer` | `services/brain/src/learning/prompt_optimizer.py` | APE/DSPy による prompt variant 生成・評価・A/B 運用。 |
| `FeedbackCollector` | `services/brain/src/learning/feedback_collector.py` | accept/reject/override を `RuleFeedback` 化。暗黙フィードバックを検出。 |
| `ThresholdAdapter` | `services/brain/src/learning/threshold_adapter.py` | `RuleThresholds` 内の学習対象閾値を bandit/gradient で更新。 |
| `LearningScheduler` | `services/brain/src/learning/scheduler.py` | 上記を毎日 or 毎週起動し、backend への書き込みを制御。 |

### 新規外部依存

| パッケージ | 用途 | 備考 |
|-----------|------|------|
| `dspy-ai` | プロンプト最適化 | 本格的導入時。軽量運用なら自前 APE で代替可。 |
| `mlxtend` | association rule mining | `mlxtend.frequent_patterns.apriori` / `association_rules`。 |
| `xgboost` / `lightgbm` | 行動予測 | 必要に応じて。 |
| `scikit-learn` | 分類・クラスタリング | 既存環境に含まれている可能性が高い。 |

### 既存コンポーネント改修

- `RulePromoter`: 対象を `classifier_cache` から `learned_rule_candidates` や `prompt_variants` へ拡張。
- `AckLearner`: voice capsule 専用から汎用 `FeedbackLearner` へリファクタ or 新設。
- `AutomationEngine`: 発火時に `RuleFeedback` 暗黙エントリを生成（no-override within N min → satisfied）。
- `RuleEngine`: 学習可能閾値を動的に読み込み、発火結果をログ化。
- `system_prompt.py` / `persona_rewriter.py`: 最適化された prompt variant を読み込む機構。

## リスク・検討事項

### 安全性・信頼性

- **Hallucinated ルール**: LLM 生成ルールは存在しない device_id や不正な JSON を含みうる（EcoMate 調査で顕在）。必ず backend validation と人間承認を挟む。
- **ルールコンフリクト**: 学習により多数のルールが増えると、同デバイスへの相反アクションが発生。conflict detector と優先度機構が必要。
- **安全クリティカル領域**: CO2 危険、SpO2 低下等は学習対象外とし、固定閾値のままにする。
- **ガードレール**: 学習による閾値変更は `MIN`/`MAX` バウンド、1 回あたり最大変化量を設ける。

### ユーザー体験

- **過度なフィードバック要求**: 学習のために承認ダイアログを頻出させると UX を損なう。暗黙フィードバックを主体とし、明示フィードバックは高不確実例のみに絞る。
- **コントロール感の喪失**: Sieger et al. の調査でも示される通り、ユーザーは「自分が教えている」感覚を重視。全自動化ではなく「提案→承認」モデルが安心感を生む。
- **コールドスタート**: IoTGPT の評価通り、学習前の精度は低い。初期は保守的なデフォルトルールを維持し、十分なエビデンス（support ≥ N、feedback ≥ M）を待つ。

### データ・プライバシー

- 在室パターン・生体データを学習に使う場合、個人の行動履歴が濃密になる。local-only 学習（Ollama + SQLite）をデフォルトとし、外部 LLM 使用時は匿名化を検討。
- `prompt_variants` や `RuleFeedback` に個人の発言情報が含まれうる。保存期間ポリシーが必要。

### コスト・性能

- APE/DSPy は評価のために多数の LLM 呼び出しを消費。30 分〜数時間かかる場合あり（参考: Towards Data Science DSPy 記事）。
- 30 秒サイクルの HEMS において、プロンプト最適化はバックグラウンドバッチにする必要がある。
- association rule mining は頻繁なデバイスイベントで計算量が爆発。時間枠を制限し、頻出アイテムセットの数を上限設定する。

### 測定・評価の困難さ

- 快適性・省エネ・健康の「真の報酬」は主観的。`intervention_efficacy` の `verdict` はあくまで代理指標。
- ユーザーが手動でデバイスを戻しても、それが「学習したルールが悪い」のか「一時的な例外」なのか判別困難。複数回の override からのみ重み更新すべき。

### 技術的負債

- プロンプトを DB 化すると reproducibility が変わる。`prompt_variants` は git 管理可能な dump 形式を併設。
- 学習結果が Obsidian vault（`RulePromoter`）に書き込まれる仕組みは維持し、人間監査可能性を担保。

## 参考リンク

### 自動プロンプト最適化

- APE 論文: https://arxiv.org/abs/2211.01910
- APE GitHub: https://github.com/keirp/automatic_prompt_engineer
- DSPy: https://github.com/stanfordnlp/dspy
- OPRO 論文: https://arxiv.org/abs/2309.03409
- APO 論文: https://arxiv.org/abs/2305.03495
- Prompt Engineering Guide - APE: https://www.promptingguide.ai/jp/techniques/ape

### スマートホーム・ルール学習

- EcoMate / Generating HomeAssistant Automations: https://arxiv.org/abs/2505.02802
- IoTGPT: https://arxiv.org/abs/2601.04680
- Interaction-Centric Dataset (LREC 2016): https://aclanthology.org/L16-1228/
- Automatic Trigger Generation (PLAS 2016): https://cnandi.com/docs/plas16-cr.pdf
- Hybrid Prompt Learning for Security Risk Justifications: https://dl.acm.org/doi/10.1145/3675401

### 強化学習・人間介入型学習

- TAMER 論文: https://ieeexplore.ieee.org/document/4640845
- User Involvement in Training Smart Home Agents: https://papers.dice-research.org/2022/HAI_SmartHome/User_Involvement_in_Training_Smart_Home_Agents_public.pdf
- User in the Loop Adaptive Smart Homes: https://www.mdpi.com/2078-2489/7/2/35
- DRL for HEMS (Energy Reports 2021): https://www.sciencedirect.com/science/article/pii/S2666546820300434
- Multi-Agent Smart-Home Energy Management: https://www.mdpi.com/2076-3417/16/4/1896

### ツール・フレームワーク

- Home Assistant: https://www.home-assistant.io/
- Adaptive Lighting: https://github.com/basnijholt/adaptive-lighting
- Stable-Baselines3: https://github.com/DLR-RM/stable-baselines3
- mlxtend: https://rasbt.github.io/mlxtend/
- Awesome LLM Prompt Optimization: https://github.com/Xiaopengli1/Awesome-LLM-Prompt-Optimization

### HEMS 内部参考

- `services/brain/src/annotator/rule_promoter.py`
- `services/brain/src/voice_capsule/ack_learner.py`
- `services/brain/src/efficacy.py`
- `services/brain/src/rules/config.py`
- `services/brain/src/automation_engine.py`
- `services/brain/src/rule_engine.py`
- `services/brain/src/event_store/database.py`
- `services/backend/models.py`
- `services/backend/schemas.py`
- `services/backend/routers/automations.py`
