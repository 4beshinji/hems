# HEMS 閉 loop 実装計画（マスター）

> 本計画は `ROADMAP.md` の指摘を受け、HEMS（Home Environment Management System）に「観測 → 意思決定 → 実行 → 結果観測 → 学習 → 次の意思決定」という閉 loop を段階的に構築するためのものです。
> 調査ドキュメントは `docs/research/closed-loop-assets/` 以下に Swarm 単位で残しており、本計画はそれらを統合・具体化した実装ロードマップです。
> 計画は大規模なため、マスター計画とフェーズ別詳細計画に分割しています。

---

## 1. 背景・目的

### 1.1 きっかけ

`ROADMAP.md`（`/home/sin/code/agent/auto/hems/ROADMAP.md`）では以下の指摘があります。

- `require_confirm` 未実装
- data-bridge 空
- モバイル Android 未完了
- 未活用データフロー多数
- セキュリティ未対応（無認証・平文）
- ドリフト検知・自動再学習不足

特に 4 軸評価では「意思決定ループ完成度 3/5: 生活リズムループは閉じている。HITL（`require_confirm`）・ロールバック・学習自動反映が不足」とされ、長期課題として「閾値・ルール・プロンプトを実行結果から自動更新する学習ループを構築する」が掲げられています。

上位ロードマップ（`/home/sin/code/agent/auto/ROADMAP.md`）でも、HEMS は「生活リズムループは閉じている。承認・ドリフト・学習反映が不足」と位置づけられ、横断的優先課題として以下が挙げられています。

1. 人間承認（HITL）と自動ロールバック
2. ドリフト検知と再校正フレームワーク
9. 学習ループの自動化

本計画はこれらを実装するための青写真です。

### 1.2 目的

HEMS Brain（ReAct + Rule-based dual-mode、30 秒サイクル）が自律的にデバイス制御・タスク作成・ルール更新を行う中で、以下を実現します。

- **安全性**: 高リスク・不可逆アクション前に人間承認（HITL）を取得し、誤実行時はロールバックできる。
- **適応性**: センサーデータのドリフトや生活リズムの変化に応じて閾値を自動再較正する。
- **学習性**: 承認/棄却/完了/介入効果からルール・プロンプト・方策を更新する。
- **因果性**: 介入が本当に効果を持ったかを推定し、偶然の相関と区別する。
- **予測性**: デジタルツイン/What-If シミュレーションで行動を仮想実行してから実機に反映する。

---

## 2. ROADMAP.md 指摘の検証サマリー

コードベースを確認した結果、ROADMAP.md の指摘はおおむね正しいが、一部は最新の監査文書で補足されています。

| 指摘 | 検証結果 | 補足 |
|------|---------|------|
| `require_confirm` 未実装 | **正しい** | `services/backend/models.py` の `AutomationRule.require_confirm` は存在するが、`services/brain/src/automation_engine.py` では参照されていない。 |
| data-bridge 空 | **正しい** | `services/data-bridge/` は `README.md` のみ。実装は `services/_common` 共有ライブラリ確立後が計画されている。 |
| モバイル Android 未完了 | **部分的に正しい** | `services/mobile-android/` と `apps/healthconnect-companion/` にプロジェクトは存在するが、HEMS Docker 化対象外であり、完了度はコードレベルで要確認。 |
| 未活用データフロー多数 | **正しい** | `docs/wiring-gap-06-data-flow-consolidation.md` と `docs/feature-proposals-2026-06-11.md` で weather alerts、shopping purchased、personal notes/knowledge changes 等が未活用と特定されている。 |
| セキュリティ未対応（無認証・平文） | **部分的に正しい** | `docs/hardening-audit-2026-04.md` および `docs/audit/2026-06-11/SUMMARY.md` によれば、MQTT ACL 等の P0 群は実装済み。残存は brain chat server 認証、webhook replay 防御等の P1 群。 |
| ドリフト検知・自動再学習不足 | **正しい** | `services/brain/src/world_model/sensor_validation.py` は範囲検証のみ。`sensor_fusion.py` の `TrendDetector` は単純。`schedule_learner.py` も統計的学習に留まる。 |

本計画では、**閉 loop に直接関わる「`require_confirm` / HITL / ロールバック / ドリフト検知 / 自動再学習 / 未活用データフロー」**を優先して扱います。

---

## 3. 閉 loop の定義（HEMS 文脈）

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  観測       │────▶│  意思決定   │────▶│  実行       │
│  (Sensors)  │     │  (Brain)    │     │  (Tools)    │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                         │
       │                                         ▼
       │                                  ┌─────────────┐
       │                                  │  結果観測   │
       │                                  │  (Outcome)  │
       │                                  └──────┬──────┘
       │                                         │
       └─────────────┬───────────────────────────┘
                     ▼
              ┌─────────────┐
              │  学習・適応 │
              │  (Learning) │
              └─────────────┘
```

HEMS での各段階：

1. **観測**: MQTT 経由で環境センサー、生体情報、PC/サービス、天気、カレンダー、VLM 等を収集。
2. **意思決定**: ReAct loop（LLM）または RuleEngine（ルールベース）でアクションを決定。
3. **実行**: ToolExecutor 経由でデバイス制御、タスク作成、通知発話等を実行。
4. **結果観測**: センサー変化、タスク完了、ユーザー承認/棄却を観測。
5. **学習・適応**: 介入効果、閾値ドリフト、ルール/プロンプトの自動更新を実施。

現在の HEMS は 1→2→3→4 の一部まで実装済みですが、4→5→1 のフィードバックループが断片的です。本計画はこのループを完成させます。

---

## 4. 現状アセットと不足アセット

### 4.1 既存の学習/適応機構

| コンポーネント | 場所 | 現在の役割 |
|---------------|------|-----------|
| `RuleThresholds` | `services/brain/src/rules/config.py` | ルールエンジンの静的閾値セット。 |
| `RulePromoter` | `services/brain/src/annotator/rule_promoter.py` | LLM 分類キャッシュの高頻度エントリを `source=llm` から `source=promoted` へ昇格。 |
| `AckLearner` | `services/brain/src/voice_capsule/ack_learner.py` | voice capsule の再生ログ `trigger_drift_sec` からリマインダーの `lead_time_min` を学習。 |
| `intervention_efficacy` | `services/brain/src/event_store/database.py`, `efficacy.py` | 環境タスクの baseline/post 判定。 |
| `event_store` | `services/brain/src/event_store/` | raw_events / llm_decisions / hourly_aggregates を蓄積。 |
| `ScheduleLearner` | `services/brain/src/schedule_learner.py` | 起床/帰宅パターンの統計的学習。 |
| `ShoppingClassifier` | `services/brain/src/annotator/shopping_classifier.py` | 購買周期学習。 |

### 4.2 不足アセット

| # | 不足アセット | 解く問題 | 関連調査ドキュメント |
|---|-------------|---------|---------------------|
| A | HITL 承認フロー | 高リスク・不可逆アクション前の人間承認 | `hitl-rollback-approval.md` |
| B | ロールバック機構 | 誤実行/棄却時の状態復元 | `hitl-rollback-approval.md` |
| C | 実行結果フィードバック収集 | 承認/棄却/スヌーズ/上書きの正規化記録 | `llm-agent-feedback-rlhf.md` |
| D | 介入効果測定の拡張 | 相関から因果への昇華 | `causal-inference-intervention-effect.md` |
| E | 適応的閾値・ドリフト検知 | 季節/生活変化に応じた閾値再較正 | `adaptive-threshold-drift-detection.md` |
| F | ルール/プロンプトの自動学習 | 実行結果からのルール生成・プロンプト最適化 | `automated-rule-prompt-learning.md` |
| G | 因果推論層 | 介入の真の効果推定 | `causal-inference-intervention-effect.md` |
| H | デジタルツイン/What-If シミュレータ | 実機実行前の仮想試行 | `digital-twin-whatif-simulation.md` |
| I | LLM エージェントの RLHF | 軌跡評価・偏好学習 | `llm-agent-feedback-rlhf.md` |
| J | 未活用データフローの活用 | weather alerts、shopping purchased 等の統合 | 各調査ドキュメント |

---

## 5. 実装原則

### 5.1 安全性第一

- 生命・安全に関わるルール（CO₂ 危険、SpO₂ 低下、漏水等）は学習対象外の **hard safety layer** として維持。
- 高リスク・不可逆アクションは実行前承認必須。
- ロールバック不能なアクション（メール送信、鍵開錠等）は特別な承認ポリシー。

### 5.2 段階的自律（Graduated Autonomy）

```
監視のみ → 実行後レビュー → 実行前承認 → 段階的自律
```

- 新しいルール/閾値/プロンプトは「提案」として始まり、承認・A/B 評価を経て自動化。

### 5.3 監査可能性

- 承認・実行・ロールバック・学習結果はすべて `event_store` または backend DB に immutable に記録。
- Obsidian `HEMS/learnings/` への学習ログ書き出しを維持・拡張。

### 5.4 ローカル優先

- 個人運用・PolyForm Noncommercial License の特性上、学習・推論は可能な限りローカル（Ollama + SQLite/Postgres）。
- 外部クラウド連携はオプション。

### 5.5 最小侵襲

- 既存の 30 秒サイクル、MQTT トピック規約、backend API、frontend 型定義を最大限尊重。
- 新規コンポーネントは明確な責務境界を持つ。

---

## 6. フェーズロードマップ

| フェーズ | テーマ | 期間目安 | 主要成果物 | 詳細計画 |
|---------|--------|---------|-----------|---------|
| **Phase 0** | HITL・承認・ロールバック基盤 | 1〜2 ヶ月 | `approvals` テーブル、承認 UI、RollbackPlanner | `PLAN-phase-0-hitl-rollback.md` |
| **Phase 1** | フィードバック収集と介入効果測定 | 1〜1.5 ヶ月 | `agent_feedback` / `intervention_efficacy` 拡張、FeedbackCollector | `PLAN-phase-1-feedback-efficacy.md` |
| **Phase 2** | 適応的閾値とドリフト検知 | 1.5〜2 ヶ月 | `AdaptiveThresholdManager`、River 導入 | `PLAN-phase-2-adaptive-thresholds.md` |
| **Phase 3** | ルール/プロンプトの自動学習 | 2〜3 ヶ月 | `RuleLearner`、`PromptOptimizer`、`LearnedRuleCandidate` | `PLAN-phase-3-rule-prompt-learning.md` |
| **Phase 4** | 因果推論とデジタルツイン | 3〜6 ヶ月 | `CausalDecisionLayer`、`WhatIfPlanner`、サロゲートモデル | `PLAN-phase-4-causal-digital-twin.md` |
| **Phase 5** | LLM エージェントの RLHF | 3〜6 ヶ月 | `FeedbackCollector` → DPO/LoRA adapter | `PLAN-phase-5-llm-rlhf.md` |

### 6.1 依存関係

```
Phase 0 ──┬──▶ Phase 1 ──┬──▶ Phase 2 ──┬──▶ Phase 3
          │              │              │
          │              └──────────────┘              
          │                             │
          └─────────────────────────────┴──▶ Phase 4
                                           │
                                           ▼
                                        Phase 5
```

- Phase 1 は Phase 0 の承認結果をフィードバックとして使う。
- Phase 2/3 は Phase 1 の介入効果測定を前提とする。
- Phase 4 は Phase 2/3 の結果を因果推論・シミュレーションに統合する。
- Phase 5 は Phase 1/3 のフィードバック収集を前提とする。

---

## 7. 横断的インフラ

### 7.1 新規テーブル（概要）

| テーブル | 用途 | 配置 |
|---------|------|------|
| `approvals` | 承認リクエスト・判定・実行・ロールバック履歴 | `services/backend/models.py` |
| `action_snapshots` | 実行前後のデバイス/ルール状態スナップショット | `services/backend/models.py` |
| `rollback_log` | ロールバック実行ログ | `services/backend/models.py` |
| `agent_feedback` | 明示/暗黙/結果/AI judge フィードバック | `services/brain/src/event_store/database.py` |
| `agent_trajectories` | LLM 決定軌跡 | `services/brain/src/event_store/database.py` |
| `threshold_drift_log` | 閾値ドリフト検知ログ | `services/backend/models.py` |
| `threshold_adjustments` | 適用済み閾値オフセット | `services/backend/models.py` |
| `learned_rule_candidates` | 人間承認待ちの学習ルール候補 | `services/backend/models.py` |
| `prompt_variants` | プロンプト variant と A/B 結果 | `services/backend/models.py` |
| `rule_feedback` | ルール単位のフィードバック | `services/backend/models.py` |
| `causal_estimates` | CATE/ATE 推定値キャッシュ | `services/brain/src/event_store/database.py` |
| `policy_logs` | 方策選択ログ（OPE 用） | `services/brain/src/event_store/database.py` |
| `simulation_runs` | What-If シミュレーション実行履歴 | `services/brain/src/event_store/database.py` |
| `what_if_scenarios` | What-If シナリオ定義 | `services/brain/src/event_store/database.py` |

### 7.2 新規 MQTT トピック

```
# HITL / Rollback
hems/approvals/request
hems/approvals/{id}/decide
hems/approvals/{id}/timeout
hems/actions/{id}/execute
hems/actions/{id}/verify
hems/actions/{id}/rollback
hems/audit/approval

# Feedback
hems/feedback/explicit
hems/feedback/implicit

# Adaptive Threshold
hems/thresholds/drift_detected
hems/thresholds/adjustment_proposed
hems/thresholds/adjustment_applied

# Simulation
hems/brain/whatif/request
hems/brain/whatif/result
hems/simulation/model/status
hems/brain/whatif/safety_halt
```

### 7.3 新規コンポーネント配置（概要）

```
services/brain/src/
├── approval/
│   ├── action_risk_classifier.py
│   ├── approval_gate.py
│   ├── rollback_planner.py
│   └── rollback_executor.py
├── feedback/
│   ├── collector.py
│   ├── trajectory_judge.py
│   ├── preference_builder.py
│   └── policy_updater.py
├── adaptive_thresholds/
│   ├── manager.py
│   ├── tracker.py
│   └── adjuster.py
├── learning/
│   ├── rule_learner.py
│   ├── prompt_optimizer.py
│   └── scheduler.py
├── causal/
│   ├── data_mart.py
│   ├── propensity.py
│   ├── effect_estimator.py
│   ├── policy_evaluator.py
│   └── intervention_planner.py
└── what_if/
    ├── planner.py
    ├── client.py
    ├── safety_gate.py
    └── comparator.py

services/simulation/        # 別サービス（Phase 4）
├── main.py
├── models/
│   ├── surrogate.py
│   ├── energyplus.py
│   └── occupancy.py
└── calibration.py

services/backend/routers/
├── approvals.py            # 新規
├── feedback.py             # 新規
├── adaptive_thresholds.py  # 新規
├── causal.py               # 新規
└── what_if.py              # 新規

services/frontend/src/
├── components/
│   ├── ApprovalQueue.tsx
│   ├── ThresholdProposalCard.tsx
│   ├── SimulationResultCard.tsx
│   └── FeedbackButtons.tsx
└── app/
    ├── approvals/
    ├── thresholds/
    └── simulations/
```

---

## 8. リスクと対策（横断的）

| リスク | 内容 | 対策 |
|--------|------|------|
| Reviewer overload | 承認依頼が多すぎて機械的承認 | 段階的自律、優先度スコアリング |
| 閾値暴走 | フィードバック偏りで閾値極端化 | オフセット上下限制限、承認制 |
| Hallucinated ルール | LLM/マイニングが存在しないデバイスを参照 | backend validation、承認制 |
| Reward hacking | LLM が報酬指標を騙す | 多角的報酬、hard guardrail |
| Sim-to-real gap | シミュレーションと実世界のずれ | 継続的キャリブレーション、SafetyGate |
| 未観測交絡 | ユーザーの気分等が観測できない | 感度分析、単純モデル優先 |
| サンプル不足 | 単一住戸で統計的有意性が得にくい | 信頼区間重視、類似セグメントプール |
| 計算コスト | EnergyPlus/DPO が重い | オンラインは軽量モデル、学習は夜間バッチ |
| プライバシー | 行動/生体データの濃密化 | ローカル学習、保存期間ポリシー |

---

## 9. 各フェーズ計画へのリンク

- [Phase 0: HITL・承認・ロールバック基盤](./PLAN-phase-0-hitl-rollback.md)
- [Phase 1: フィードバック収集と介入効果測定](./PLAN-phase-1-feedback-efficacy.md)
- [Phase 2: 適応的閾値とドリフト検知](./PLAN-phase-2-adaptive-thresholds.md)
- [Phase 3: ルール/プロンプトの自動学習](./PLAN-phase-3-rule-prompt-learning.md)
- [Phase 4: 因果推論とデジタルツイン](./PLAN-phase-4-causal-digital-twin.md)
- [Phase 5: LLM エージェントの RLHF](./PLAN-phase-5-llm-rlhf.md)

---

## 10. 参考調査ドキュメント

- [HITL・承認・ロールバック調査](./hitl-rollback-approval.md)
- [適応的閾値・ドリフト検知調査](./adaptive-threshold-drift-detection.md)
- [デジタルツイン・What-If シミュレーション調査](./digital-twin-whatif-simulation.md)
- [因果推論・介入効果調査](./causal-inference-intervention-effect.md)
- [ルール/プロンプト自動学習調査](./automated-rule-prompt-learning.md)
- [LLM エージェント・RLHF 調査](./llm-agent-feedback-rlhf.md)

---

## 11. 次のアクション

1. Phase 0 から順次実装を開始する。
2. 各フェーズの実装前に、本計画と該当詳細計画をレビューし、スコープを確定する。
3. 必要に応じて、各フェーズごとに PoC を実施し、効果を検証してから本格展開する。
4. 実装進捗に応じて本計画を更新し、陳腐化を防ぐ。
