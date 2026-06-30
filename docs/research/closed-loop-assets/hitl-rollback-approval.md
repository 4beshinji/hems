# hitl-rollback-approval 調査レポート

## 概要

**hitl-rollback-approval** は、自律システム（特に AI エージェントや自動化システム）が「実行する前・実行後」に人間の承認を得たり、誤った実行を巻き戻したりするためのガバナンス・セーフティ機構である。HEMS のような個人向けホーム自動化においては、Brain が自律的にデバイスを操作・ルールを変更・環境を制御する中で、以下の 3 つの機能を統合することで閉 loop の安全性を高める。

1. **Human-in-the-Loop（HITL）**: 高リスク行動や不確実な行動を人間に提示し、承認・修正・拒否を得てから実行する。
2. **Rollback**: 実行後に異常や人間の拒否があった場合、デバイス状態・ルール・設定を前の安全な状態に戻す。
3. **Approval workflow**: 承認フローそのものを管理する状態機械、キュー、タイムアウト、監査証跡。

本レポートでは、核心概念、学術論文・先行研究、OSS/商用ツール、HEMS への適用案、必要アセット、リスクを網羅的にまとめる。

## 核心概念

### hitl-rollback-approval が解く問題

HEMS の Brain は 30 秒サイクルで観測 → 意思決定 → 実行を繰り返す。LLM や学習済みポリシーが以下のような誤りを起こすリスクがある。

- ルールベースしきい値を超えたデバイス制御（例：不在時にエアコンを極端に冷やす）
- ルールの自己昇格（RulePromoter）による意図しない自動化の拡大
- センサー異常・幻覚に基づく誤った介入
- 外部サービス（Home Assistant 等）との状態不整合

HITL + rollback + approval は、これらの誤りを「実行前に防ぐ」または「実行後に修復する」二段階の安全網として機能する。

### 主要な用語とパターン

| 用語 | 意味 | HEMS での例 |
|------|------|------------|
| **Human-in-the-Loop (HITL)** | 人間が AI の意思決定に積極的に関与し、承認/修正/拒否を行う | 高リスクなデバイス操作を実行前にダッシュボード/モバイル通知で承認させる |
| **Human-on-the-Loop (HOTL)** | AI が自律実行し、人間はモニタリングし必要に応じて介入 | 通常運転を自動化し、異常時だけ通知して手動オーバーライドを可能にする |
| **Human-over-the-Loop** | 人間はポリシー/監査を定期的にレビュー | 週次でルール昇格履歴を確認し、方針を調整 |
| **Pre-execution approval gate** | 不可逆・高リスク行動の前に強制停止して承認を得る | 鍵の解錠、防犯システム無効化、高電力機器の長時間稼働前に承認 |
| **Post-execution review / rollback window** | 実行後にレビュー期間を設け、補償操作で巻き戻す | 照明シーン変更後 5 分以内なら元の明るさに戻す |
| **Compensating transaction** | 失敗時に意味的に元に戻す新たなトランザクション | 「エアコン ON」→ rollback 時に「エアコン OFF + 元の温度設定復元」 |
| **Saga pattern** | 分散処理をローカルトランザクションの連鎖で管理し、失敗時に逆順で補償する | 複数デバイスにまたがるシーン実行を saga として管理 |
| **Graduated autonomy** | 信頼性に応じて段階的に自律度を上げる | 新ルールは承認制→サンプリング監視→完全自律へ移行 |

### 判断軸：いつ承認が必要か

業界で広く使われている 4 軸は以下の通り。

1. **Irreversibility（可逆性）**: 元に戻せない行動は承認必須
2. **Blast radius（影響範囲）**: 多数デバイス・長時間に影響する行動は承認
3. **Compliance exposure（コンプライアンス）**: プライバシー・安全規制に触れる行動は承認
4. **Confidence（確信度）**: エージェントの自信が低い・分布外の場合は承認

HEMS では「単身者・自宅環境」という文脈を加味し、例外的に「寝ている間の緊急対応」などは HOTL/自動 fallback に移行する必要もある。

## 論文・先行研究

### 学術論文・サーベイ

| タイトル | 著者 | 年 | 要点 | HEMS への応用可能性 |
|---------|------|-----|------|-------------------|
| **A Survey of Human-in-the-Loop Reinforcement Learning** | K. Besigomwe ら | 2026 | 安全制約付き RL における人間の関与を体系的に分類。Preventive / Corrective / Advisory / Normative 制約を提示。 | Brain の行動空間に対し、人間承認による Preventive 制約、介入による Corrective 制約を実装可能。 |
| **Human-in-the-Loop Artificial Intelligence: A Systematic Review** | K. Lazaros ら | 2026 | HITL AI の包括的サーベイ。配置（loop placement）、相互作用粒度、時間的特性の 3 軸分類。 | HEMS での承認配置（実行前/実行後/監査）を設計する際の指針。 |
| **A Control-Theoretic Architecture for Governing Socio-Technical AI** | (複数) | 2025 | 社会技術的 AI を制御理論で統治。継続観測 → しきい値評価 → 比例介入（スロットリング/監視強化/ロールバック）の閉 loop。 | RuleThresholds と intervention_efficacy テーブルに直結。drift 検知 → 自動スロットリング/人間承認へのエスカレーション。 |
| **Reversible Reinforcement Learning Framework (arXiv:2510.14503)** | (複数) | 2025 | 遷移可逆性推定と明示的 rollback 演算子を組み合わせ、CliffWalking/Taxi で 99%以上の破滅的行動を抑制。 | 行動前に「この操作は元に戻せるか」を推定し、不可逆行動は自動的に承認ゲートに回す。 |
| **CARE: Decoding Time Safety Alignment via Rollback and Introspection Intervention** | (複数) | 2025 | LLM の生成過程で guard model が危険な軌道を検知 → rollback + introspection で安全に再アライメント。 | Brain が生成する計画/行動シーケンスに対し、危険な行動を検知して rollback し再計画。 |
| **Human-In-The-Loop Machine Learning for Safe and Ethical Autonomous Vehicles** | (複数) | 2024 | HITL-ML / HITL-RL の AV 応用レビュー。reward shaping、action injection、interactive learning。 | 家庭内ロボット/自動運転的な制御に応用。人間の修正を学習データに変換。 |
| **Safety-aware Human-in-the-Loop Reinforcement Learning with Shared Control for Autonomous Driving** | W. Huang ら | 2024 | 共有制御による安全な HITL-RL。人間と AI の制御権をブレンド。 | デバイス制御の権限共有（例：人間が部分的に操作を修正しながら自動化が継続）。 |
| **Automated Decision Making Systems in Smart Homes** | L. Jin ら | 2022 | スマートホームの ADM システムレビュー。エネルギー/安全/エンタメのトレードオフと「co-performance」の必要性を指摘。 | HEMS のユーザー制御と自動化のバランス設計の理論基盤。 |
| **Predictive Shared Steering Control for Driver Override** | C. Guo ら | 2019 | 自動運転ステアリングのドライバーオーバーライドを MPC 共有制御でスムーズに。 | 人間が HEMS の自動制御を即座に引き継ぐ際の滑らかな遷移制御。 |

### 白書・調査報告・規制文書

| タイトル | 発行体 | 年 | 要点 | HEMS への応用可能性 |
|---------|--------|-----|------|-------------------|
| **AI in GRC: Promise, Pitfalls and a Practical Path Forward** | SureCloud | 2025 | HITL、Reversibility、Separation of duties、Auditability、Versioning を AI ガバナンス原則として提示。「サイレント自動化なし、状態変更は承認と rollback を伴う」。 | HEMS のルール変更・デバイス制御に reversibility 要件を課す。 |
| **Strategies for Scaling to a Large Number of AI Models in Production** | AI Sweden | 2025 | モデルライフサイクルに human-in-the-loop 承認ゲート、監視 → 自動リトレイン/再配信/rollback の閉 loop。 | Brain のポリシー/プロンプト/ルールのバージョン管理と昇降格に適用。 |
| **TechDispatch #2/2025: Human Oversight of Automated Decision-Making** | EDPS | 2025 | 「meaningful」「effective」な人間監視の定義。実質的に品質を向上させ、被害を防止する関与。 | HEMS の承認 UI が単なる形式ではなく、文脈・権限・説明を提供する設計指針。 |
| **EU AI Act（特に Article 14）** | EU | 2024/以降 | 高リスク AI システムは自然人能動的監督下にあり、無視/上書き/逆転（rollback）が可能でなければならない。 | HEMS の生体認識・重要インフラ制御・医療支援機能に該当する場合の設計基準。 |
| **Assessing High-Risk AI Systems under the EU AI Act** | (複数) | 2026 | 高リスク AI 適合評価方法論。Human Agency & Oversight、Technical Robustness、Transparency、Audit trails。 | HEMS の hitl-rollback-approval コンポーネントを適合評価に組み込む。 |

## OSS・商用ツール・フレームワーク

### 汎用エージェント/ワークフロー系

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-----------------|
| **LangGraph** | https://github.com/langchain-ai/langgraph | グラフベースのステートフルエージェント実行エンジン。`interrupt()` / `interrupt_before` / `interrupt_after` による HITL、PostgreSQL/SQLite チェックポインタ、ロールバック/タイムトラベル。 | 高。Brain の ReAct ループを LangGraph 化し、承認ゲートをノードとして組み込める。ただし Brain は既存の自前実装なので、部分的な移植 or 参考実装に留める。 |
| **Temporal** | https://temporal.io | 耐久性のあるワークフローエンジン。Signal/Query/Condition による長時間承認待ち、Saga rollback、クラッシュ復旧。 | 中〜高。承認待ちフローの耐久性を確保できる。ただし新規インフラ（Temporal Server）が必要。 |
| **n8n** | https://n8n.io | ビジュアルワークフロー。Human Review/Approval ノード、メール/Slack/Telegram 承認、ツール単位の承認、タイムアウト。 | 中。フロントエンド・モバイル通知連携の参考に。HEMS の Python スタックには直接組み込みにくい。 |
| **Node-RED** | https://nodered.org | IoT/ホーム自動化向けフローエディタ。フロー実行、承認 UI（dashboard）、MQTT 連携。 | 中。HEMS の MQTT イベント駆動承認フローの参考に。 |
| **Floxy** | https://github.com/floxy-project/floxy | Go 製軽量ワークフローエンジン。Saga rollback、SavePoint、Human-in-the-loop、PostgreSQL/SQLite。 | 中。参考アーキテクチャ。HEMS では Python 実装が自然。 |
| **workflow-core** | https://github.com/danielgerlag/workflow-core | .NET 製ワークフロー。承認待ち、rollback 拡張議論あり。 | 低。言語スタックが異なる。 |
| **HITL Protocol (rotorstar)** | https://github.com/rotorstar/hitl-protocol | 自律エージェントサービス向け HITL オープン標準。Approval/Selection/Input/Confirmation/Escalation 5 種のレビュー、Polling/SSE/Callback トランスポート。 | 中。HEMS のモバイル/ダッシュボード承認 API 設計の参考。 |

### ロボティクス/サイバーフィジカル系

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-----------------|
| **OpenClaw / capability governance runtime** | arXiv:2604.07833 等 | 能力（capability）ごとに permission/risk/rollback/env_profile を宣言。Governance layer が admission、実行監視、rollback を仲介。 | 高。HEMS の device/tool ごとに `risk` と `rollback` メタデータを定義する設計に直接適用。 |
| **TRANSIC** | https://transic-robot.github.io | Sim-to-real ロボット学習。人間の online correction と rollback point を使った CIL-SERL。 | 中。人間の修正を学習データに組み込む AckLearner の拡張に参考。 |
| **ParkingWorld** | https://yu-zhengcheng-11.github.io/ParkingWorld/ | 自律駐車の HITL-RL。失敗ロールアウトと人間修正をペアリングした replay buffer、rollback snapshot。 | 中。Brain の行動履歴と人間介入をペアで保存する仕組みに参考。 |

### 商用/クラウド系

| 名前 | URL | 特徴 | HEMS への流用可否 |
|------|-----|------|-----------------|
| **StackAI** | https://www.stackai.com | AI エージェント承認ワークフロー。リスク別承認マトリクス、拒否率/KPI 追跡。 | 低〜中。設計パターンの参考。 |
| **LaunchDarkly / FeatBit** | https://launchdarkly.com, https://www.featbit.co | Feature flag によるモデル/プロンプトの段階的ロールアウト、kill switch、A/B、自動 rollback。 | 中。Brain のポリシー/プロンプト/ルールの段階的デプロイと即座の無効化に活用。 |
| **Dolt** | https://www.dolthub.com | Git ライクなデータベース。ブランチ/差分/レビュー/rollback。 | 中。ルールや設定のバージョン管理・人間レビュー・rollback に活用可能（ただし SQLite/Postgres からの移行コスト）。 |
| **GitLab Approval HITL Node** | https://gitlab.com/groups/gitlab-org/-/work_items/20652 | AI エージェント用 HITL ノード。リスクスコア、ロールバック戦略、影響範囲提示。 | 中。承認 UI に提示すべき情報の参考。 |

## HEMS への適用案

### アーキテクチャ全体像

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  承認キュー一覧 / 行動プレビュー / 理由説明 / 承認・拒否・修正  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS/WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  POST /approvals           ← 承認リクエスト作成・照会          │
│  POST /approvals/{id}/decide ← 人間の判定受信                 │
│  GET  /pending-actions     ← 保留中アクション一覧             │
│  POST /rollbacks           ← ロールバック実行                 │
│  GET  /audit-trail         ← 監査証跡                         │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/MQTT
┌──────────────────────▼──────────────────────────────────────┐
│                     Brain (Python)                           │
│  ReAct loop + Action Gate + Rollback Planner                  │
│   - 行動生成時に risk/irreversibility/confidence を評価       │
│   - 承認必須 → MQTT/HTTP で承認リクエスト発行後中断           │
│   - 承認済み → 実行 + 検証 + 学習                            │
│   - 拒否/異常 → Rollback Planner で補償操作を生成・実行        │
└──────────────────────┬──────────────────────────────────────┘
                       │ MQTT
┌──────────────────────▼──────────────────────────────────────┐
│              Device Registry / Bridges / MQTT               │
│  デバイス状態の取得・操作、heartbeats、イベントストア         │
└─────────────────────────────────────────────────────────────┘
```

### 既存コンポーネントとの統合

#### 1. RuleThresholds / AutomationRule

- 各 `AutomationRule` に `risk_tier` と `reversibility` フィールドを追加。
- ルールが発火する際、`risk_tier=high` または `reversibility=irreversible` なら HITL 承認ゲートにルーティング。
- しきい値違反の自動修復（例：温度異常→エアコン停止）でも、影響範囲が大きい場合は承認を挟む。

#### 2. RulePromoter / AckLearner

- RulePromoter が提案する新ルール/ルール昇格は、デフォルトで承認制とする。
- AckLearner（人間の承認/拒否/修正を学習）は、hitl-rollback-approval からの拒否データをネガティブフィードバックとして使う。
- `intervention_efficacy` テーブルに「承認→実行→結果」の因果を記録し、効果検証に使う。

#### 3. event_store

- すべての承認リクエスト、判定、実行、rollback を event_store に immutable に記録。
- イベントタイプ: `approval_requested`, `approval_decided`, `action_executed`, `verification_failed`, `rollback_executed`, `policy_violation`。

#### 4. intervention_efficacy

- テーブル/モデルに以下のカラムを追加。
  - `approval_id`（外部キー）
  - `human_decision`（approve/reject/modify）
  - `rolled_back`（bool）
  - `rollback_success`（bool）
  - `efficacy_score`（人間介入が実際にどれだけ被害を防いだかの推定値）

### 承認フローの状態機械

```
[PROPOSED]
   │
   ▼
[PENDING_APPROVAL] ──timeout──▶ [AUTO_REJECTED or ESCALATED]
   │
   ├─ approve ──▶ [APPROVED] ──▶ [EXECUTING] ──▶ [VERIFYING]
   │                                              │
   │                              success ◀───────┘
   │                                 │
   │                                 ▼
   │                           [COMPLETED]
   │
   ├─ reject ──▶ [REJECTED] ──▶ [CANCELLED]
   │
   └─ modify ──▶ [MODIFIED] ──▶ [RE-PROPOSED]

[VERIFYING] ──failure──▶ [ROLLING_BACK] ──▶ [ROLLED_BACK] or [ROLLBACK_FAILED]
```

### ロールバックの種類

| 種類 | 対象 | 実装方法 | 例 |
|------|------|---------|-----|
| **State restore** | デバイスの状態値 | 実行前 snapshot を保存し、元の値を書き戻す | 照明の明るさ・色温度を元に戻す |
| **Compensating action** | デバイス操作の意味的 undo | 逆操作を発行 | エアコン ON → OFF、カーテン開 → 閉 |
| **Rule/policy revert** | ルール/しきい値 | ルールバージョンを前の版に戻す | RulePromoter の昇格を取り消し |
| **Configuration rollback** | 設定ファイル | Git 管理 or DB 履歴から復元 | `character.yaml` / プロンプト変更の revert |
| **Notification/alert** | 人間への通知 | 誤りを報告し手動対応を促す | ロールバックできない行動（例：メール送信後）を検知 |

## 実装に必要なアセット

### データスキーマ変更

#### `approvals` テーブル（新規）

```sql
CREATE TABLE approvals (
    id UUID PRIMARY KEY,
    thread_id TEXT,                    -- ReAct サイクル/会話単位
    action_type TEXT NOT NULL,         -- device_control, rule_promotion, config_change, ...
    risk_tier TEXT NOT NULL,           -- safe, low, medium, high, critical
    reversibility TEXT NOT NULL,       -- reversible, compensatable, irreversible
    confidence REAL,                   -- エージェントの確信度 0.0-1.0
    proposed_payload JSONB NOT NULL,   -- 提案内容
    context JSONB,                     -- 理由、センサーデータ、関連イベント
    status TEXT NOT NULL,              -- proposed, pending, approved, rejected, modified, expired, rolled_back
    reviewer_id TEXT,                  -- 承認者（user_id or system）
    decision TEXT,                     -- approve, reject, modify
    decision_reason TEXT,
    requested_at TIMESTAMPTZ DEFAULT now(),
    decided_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    rollback_plan JSONB,               -- 実行後 rollback 用プラン
    rollback_status TEXT,              -- none, pending, success, failed
    audit_log JSONB DEFAULT '[]'
);
```

#### `action_snapshots` テーブル（新規）

```sql
CREATE TABLE action_snapshots (
    id UUID PRIMARY KEY,
    approval_id UUID REFERENCES approvals(id),
    entity_type TEXT NOT NULL,         -- device, scene, rule, config
    entity_id TEXT NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB,
    captured_at TIMESTAMPTZ DEFAULT now()
);
```

#### `rollback_log` テーブル（新規）

```sql
CREATE TABLE rollback_log (
    id UUID PRIMARY KEY,
    approval_id UUID REFERENCES approvals(id),
    trigger TEXT NOT NULL,             -- human_reject, verification_failure, timeout, policy_violation
    compensation_plan JSONB,
    execution_status TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);
```

#### 既存テーブルの拡張

- `automation_rules`: `risk_tier`, `reversibility`, `approval_required`, `auto_rollback_window_seconds` カラム追加。
- `intervention_efficacy`: `approval_id`, `human_decision`, `rolled_back`, `rollback_success`, `efficacy_score` カラム追加。
- `events` / `event_store`: `approval_id` カラム追加で紐付け。

### 新規コンポーネント

| コンポーネント | 責務 | 配置 |
|--------------|------|------|
| **ActionRiskClassifier** | 提案行動の risk_tier / reversibility / confidence を判定 | Brain |
| **ApprovalGate** | 承認が必要な行動を検出し、Backend に承認リクエストを発行、Brain を中断 | Brain |
| **ApprovalQueueManager** | 承認リクエストの CRUD、タイムアウト、エスカレーション、通知発行 | Backend |
| **HumanNotificationService** | モバイル/ダッシュボード/音声での承認依頼通知 | Backend + Frontend |
| **RollbackPlanner** | 失敗/拒否時の補償操作列を生成（State restore + Compensating action） | Brain |
| **RollbackExecutor** | 補償操作を実際に実行し、結果を検証 | Brain + Backend |
| **VerificationWatcher** | 実行後の状態を監視し、異常を検知して rollback をトリガ | Brain |
| **AuditLogger** | 承認・実行・rollback の immutable ログを event_store へ書き込み | Backend |
| **AckLearningAdapter** | 承認/拒否/修正データを AckLearner/RewardShaper に渡す | Brain |

### 外部依存

| 依存 | 用途 | 導入判断 |
|------|------|---------|
| **PostgreSQL/SQLite** | approvals, snapshots, rollback_log の永続化 | 既存の DB を流用。PostgreSQL を推奨（JSONB・同時更新）。 |
| **MQTT** | 承認依頼・判定・rollback 完了の非同期通知 | 既存の Mosquitto を流用。トピック例: `hems/approvals/{id}/decide`。 |
| **Redis / 既存のキャッシュ** | 保留中承認の高速参照、ロック | 既存があれば流用。なければ PostgreSQL advisory lock で代替可能。 |
| **Temporal** | 長時間承認待ち・Saga 実行の耐久性 | オプション。30 秒サイクルの HEMS では必須ではないが、長時間承認には有効。 |
| **LangGraph** | ステートフルな ReAct + HITL | 参考実装。既存 Brain への完全移行は大工事。 |
| **n8n/Node-RED** | 承認フローのプロトタイプ | 参考。HEMS には直接組み込まず、UI/UX 設計に活用。 |
| **Dolt** | ルール・設定の Git 的バージョン管理 | オプション。ルール変更のレビュー/rollback を強化する場合に検討。 |

### 推奨 MQTT トピック追加

```
hems/approvals/request           # Brain → Backend/Frontend: 承認依頼
hems/approvals/{id}/decide       # Frontend/Backend → Brain: 承認判定
hems/approvals/{id}/timeout      # Backend → Brain: タイムアウト
hems/actions/{id}/execute        # Brain → Device bridge: 承認済み実行
hems/actions/{id}/verify         # Device bridge → Brain: 実行結果検証
hems/actions/{id}/rollback       # Brain → Device bridge: ロールバック
hems/audit/approval              # Backend → event_store: 監査ログ
```

## リスク・検討事項

### 1. 人間の過負荷（Reviewer overload）

- 承認依頼が多すぎると「承認ハメ」が発生し、ユーザーが機械的に承認（rubber-stamping）したり無視したりする。
- **対策**: 段階的自律（graduated autonomy）で、信頼性が高まるにつれて承認を例外的に。機械学習で誤りリスクを予測し、優先度の高いものだけを人間に提示。

### 2. タイムアウト設計

- 寝ている間や離席中に承認待ちが発生すると、緊急時対応が遅れる。
- **対策**: 緊急度に応じたタイムアウト（火災検知→即自動実行、照明シーン→15分待つ）。デフォルト動作を `auto_reject` / `auto_execute` / `escalate` のいずれかに設定。

### 3. Rollback の限界

- 物理的副作用（ドアを開けた、水を出した、メールを送った）は完全に undo できない。
- **対策**: 事前に「可逆性」を分類。不可逆行動は実行前承認を厳格化。rollback 不能時は人間への緊急通知と手順提示。

### 4. 状態不整合と競合

- rollback 実行中にユーザーが手動でデバイスを操作すると、snapshot が古くなる。
- **対策**: 実行時に楽観的ロック/バージョン番号を使用。競合検知時は「最終書き込み勝利」ではなく、人間確認 or 調停ロジックを入れる。

### 5. エスカレーションと責任の所在

- HITL は「人間が責任を持つ」という幻想を生みがち。実際には UI が貧弱だと人間は正しく判断できない。
- **対策**: 承認 UI には文脈（センサーデータ、理由、影響範囲、rollback 可否）を十分提示。Shneiderman の「Human-centered AI」に基づき、説明可能性を確保。

### 6. セキュリティ

- 承認エンドポイントのなりすまし、MQTT トピックの改ざん、承認履歴の漏洩。
- **対策**: 承認トークンの暗号化、JWT 検証、トピックACL、`BACKEND_API_KEY` / `HEMS_INTERNAL_TOKEN` の分離、監査ログの改ざん防止（append-only + 署名）。

### 7. 規制対応

- EU AI Act Article 14 では高リスク AI に「上書き/逆転/不使用の権限」が必要。HEMS が生体認識や医療支援機能を含む場合に該当する可能性。
- **対策**: 高リスク機能を特定し、hitl-rollback-approval を要件として設計。Article 14 対応を技術文書に記録。

### 8. 性能とレイテンシ

- 承認待ちで 30 秒サイクルがブロックされると、他の観測・処理も止まる。
- **対策**: Brain は非同期/並列で複数サイクルを管理。承認待ちアクションは専用スレッド/キューに委ね、メインサイクルは継続。

### 9. 学習への悪影響

- 人間が頻繁に拒否すると、AckLearner が過度に保守的になり、システムが自動化しなくなる。
- **対策**: 拒否データの重み付け、探索と利用のバランス、定期的なルールレビュー（Human-over-the-Loop）。

### 10. 導入段階の推奨

1. **Phase 0: 監視のみ** — すべての高リスク行動をログ/通知だけし、実行は手動。
2. **Phase 1: 実行後レビュー** — 低リスク行動を自動実行し、影響範囲の小さいものだけ rollback 可能に。
3. **Phase 2: 実行前承認** — 不可逆・高影響行動に対して承認ゲートを導入。
4. **Phase 3: 段階的自律** — 精度と信頼性の証拠に基づき、承認対象を絞り込む。

## 参考リンク

- LangGraph HITL: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- LangGraph interrupts: https://langchain-ai.github.io/langgraph/concepts/interrupt/
- LangChain Human-in-the-Loop middleware: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- Temporal workflows (operator approval + saga rollback): https://github.com/studiomeyer-io/temporal-memory-workflows
- n8n Human in the Loop: https://n8n.io/workflows/2907-a-very-simple-human-in-the-loop-email-response-system-using-ai-and-imap/
- HITL Protocol Open Standard: https://github.com/rotorstar/hitl-protocol
- EU AI Act Article 14: https://artificialintelligenceact.eu/article/14/
- EDPS TechDispatch on Human Oversight: https://www.edps.europa.eu/data-protection/our-work/publications/techdispatch/2025-09-23-techdispatch-22025-human-oversight-automated-making_en
- SureCloud AI in GRC: https://www.surecloud.com/hubfs/ai-in-grc-promise-pitfalls-and-a-practical-path-forward.pdf
- AI Sweden "1000 models in production": https://www.ai.se/sites/default/files/2025-12/Strategies%20for%20Scaling%20to%20a%20Large%20Number%20of%20AI%20Models%20in%20production%20-%20251215.pdf
- Reversible RL (arXiv:2510.14503): https://arxiv.org/abs/2510.14503
- CARE: Rollback for LLM safety (arXiv:2509.06982): https://arxiv.org/abs/2509.06982
- A Survey of HITL RL (Cognizance): https://cognizancejournal.com/vol6issue4/V6I402.pdf
- Human-in-the-Loop AI Systematic Review (MDPI Entropy): https://www.mdpi.com/1099-4300/28/4/377
- Automated Decision Making Systems in Smart Homes (CEUR-WS): https://ceur-ws.org/Vol-3154/paper12.pdf
- Preserving Sense of Agency in Household Robots (HCRL): https://hcrlab.cs.washington.edu/assets/pdfs/2025/yang2025senseofagency.pdf
- StackAI Approval Workflows: https://www.stackai.com/insights/human-in-the-loop-ai-agents-how-to-design-approval-workflows-for-safe-and-scalable-automation
- FeatBit Approval Flow for AI Model Changes: https://www.featbit.co/blogs/approval-flow-for-ai-model-changes
- Dolt + EU AI Act rollback: https://www.dolthub.com/blog/2026-02-02-eu-ai-act/
- OpenClaw capability governance (arXiv:2604.07833): https://arxiv.org/abs/2604.07833
