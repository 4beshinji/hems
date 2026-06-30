# HEMS 閉 loop 実装統合計画

> 本計画は `docs/research/closed-loop-assets/IMPLEMENTATION_PLAN.md` と各 `PLAN-phase-*.md` を統合し、Phase 0〜5 のクリティカルパス、自然な作業順序、マイルストーン、リスク、Phase 0/1 の具体計画を整理したものです。

---

## 1. 全体像：Phase 0〜5 の統合

HEMS の閉 loop は「観測 → 意思決定 → 実行 → 結果観測 → 学習・適応 → 次の観測」というサイクルを完成させることを目的とします。

| フェーズ | テーマ | 期間目安 | 中核となる問い |
|---------|--------|---------|---------------|
| **Phase 0** | HITL・承認・ロールバック基盤 | 1〜2 ヶ月 | 高リスク・不可逆アクションを安全に実行するには？ |
| **Phase 1** | フィードバック収集と介入効果測定 | 1〜1.5 ヶ月 | ユーザー介入や実行結果をどう正規化して記録するか？ |
| **Phase 2** | 適応的閾値とドリフト検知 | 1.5〜2 ヶ月 | 季節変動や生活変化に閾値をどう追従させるか？ |
| **Phase 3** | ルール/プロンプトの自動学習 | 2〜3 ヶ月 | 実行履歴からどのようなルール/プロンプトを学習・提案するか？ |
| **Phase 4** | 因果推論とデジタルツイン | 3〜6 ヶ月 | 介入が本当に効いたかを因果的に推定し、仮想実行できるようにするには？ |
| **Phase 5** | LLM エージェントの RLHF | 3〜6 ヶ月 | LLM の決定軌跡を評価・学習し、個人に適合させるには？ |

### 各フェーズの位置づけ

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

- Phase 0 は安全基盤であり、後続すべての前提。
- Phase 1 はデータ基盤であり、Phase 2/3/4/5 の学習材料を供給。
- Phase 2/3 は並行開始可能だが、Phase 3 は Phase 2 の閾値機構を利用する部分あり。
- Phase 4/5 は Phase 1〜3 の蓄積データを前提とする。

---

## 2. クリティカルパス

後続をブロックするタスクを中心に、以下のようなクリティカルパスが存在します。

| 順序 | タスク | ブロックする後続 |
|-----|--------|----------------|
| 1 | Phase 0: スキーマ整備（`approvals` / `action_snapshots` / `rollback_log`） | 承認 API、Brain 承認ゲート、ロールバック、監査ログ |
| 2 | Phase 0: 承認 API 実装 | Brain 承認ゲート、Frontend 承認 UI |
| 3 | Phase 0: Brain 承認ゲート実装 | 統合テスト、Phase 1 FeedbackCollector |
| 4 | Phase 0: ロールバック機構実装 | 異常時の状態復元、Phase 3 信頼度学習 |
| 5 | Phase 1: スキーマ整備（`agent_feedback` / `agent_trajectories`） | FeedbackCollector、OutcomeReward、TrajectoryRecorder |
| 6 | Phase 1: `FeedbackCollector` 実装 | Phase 2/3/5 の学習ループ |
| 7 | Phase 1: `event_store` 拡張（`record_decision` / `record_intervention_created` / `mark_intervention_completed`） | 介入効果測定、監査証跡 |
| 8 | Phase 2: `AdaptiveThresholdManager` 実装 | Phase 3 `ThresholdAdapter`、動的閾値運用 |
| 9 | Phase 3: `RuleLearner` 実装 | Phase 4/5 の方策改善 |
| 10 | Phase 4: 因果推論層 | Phase 5 の reward shaping、What-If 精度改善 |

---

## 3. 自然な作業順序

### 直列部分（依存が強く、並行不可）

1. **Phase 0 のスキーマ整備** → 承認 API → Brain 承認ゲート → ロールバック
2. **Phase 1 のスキーマ整備** → FeedbackCollector → OutcomeReward / TrajectoryRecorder
3. **Phase 2 の River 導入** → MetricDriftTracker → AdaptiveThresholdManager → ThresholdAdjuster
4. **Phase 3 の `RuleLearner` 基盤** → ルール候補生成 → 承認 UI → 昇格フロー
5. **Phase 4 の Causal Data Mart** → Propensity/Effect Estimator → Simulation Service → What-If Planner
6. **Phase 5 の TrajectoryJudge** → PreferenceBuilder → PolicyUpdater → LoRA adapter

### 並行可能部分

- Phase 0 の Frontend UI（承認キュー）は承認 API が安定していれば並行開発可能
- Phase 1 の Frontend フィードバック UI は `POST /feedback` API 草案が決まれば並行開発可能
- Phase 2 の UI（閾値提案カード）は backend API 実装と並行可能
- Phase 3/4/5 の調査・ライブラリ選定は Phase 0/1 の実装中に並行して進められる
- Phase 4 の家屋メタデータ整備は Phase 1/2 と並行可能

### 推奨される段階的展開

```
Month 1-2 : Phase 0（安全基盤）
Month 2-3 : Phase 1（フィードバック基盤）+ Phase 2 準備（River 調査・導入）
Month 4-5 : Phase 2（適応的閾値）+ Phase 3 準備
Month 6-8 : Phase 3（ルール/プロンプト学習）
Month 9-12: Phase 4（因果推論・デジタルツイン）+ Phase 5 準備
Month 13-18: Phase 5（RLHF）
```

---

## 4. マイルストーンと受入基準

### プロジェクト全体マイルストーン

| マイルストーン | 目標時期 | 受入基準 |
|--------------|---------|---------|
| **M0: 安全基盤完成** | Phase 0 終了 | HITL 承認・棄却・修正・ロールバックが UI/API 経由で動作し、監査ログが記録される |
| **M1: フィードバックループ完成** | Phase 1 終了 | 明示/暗黙フィードバックが正規化され、介入効果測定が自動化される |
| **M2: 適応的閾値運用** | Phase 2 終了 | 季節変動やドリフトに応じて閾値が更新提案され、承認制で適用される |
| **M3: 自動学習運用** | Phase 3 終了 | 履歴からルール候補/プロンプト variant が生成・A/B 評価・承認昇格される |
| **M4: 因果推論・シミュレーション** | Phase 4 終了 | 介入効果が因果的に推定され、What-If シミュレーションが実機反映前に実行される |
| **M5: パーソナライズ LLM** | Phase 5 終了 | LLM 決定軌跡が評価・学習され、LoRA adapter による個人適合が動作する |

### 中間マイルストーン

| フェーズ | 中間マイルストーン | 受入基準 |
|---------|------------------|---------|
| Phase 0 | P0-M1: スキーマ & API | `approvals` / `action_snapshots` / `rollback_log` テーブル作成、CRUD API 動作 |
| Phase 0 | P0-M2: 承認ゲート | `require_confirm=true` のルールがトリガ時に pending 承認を生成 |
| Phase 0 | P0-M3: ロールバック | 棄却/異常時に補償操作または状態復元が実行される |
| Phase 1 | P1-M1: フィードバックスキーマ | `agent_feedback` / `agent_trajectories` テーブル作成 |
| Phase 1 | P1-M2: 収集パイプライン | 明示/暗黙フィードバックが収集・正規化される |
| Phase 1 | P1-M3: 効果測定 | `intervention_efficacy` が承認結果と紐付けて更新される |
| Phase 2 | P2-M1: DriftTracker | ADWIN/PageHinkley でドリフト検知が動作 |
| Phase 2 | P2-M2: 閾値提案 | 閾値変更提案が生成・承認可能 |
| Phase 3 | P3-M1: ルール候補生成 | 履歴から `learned_rule_candidates` が生成される |
| Phase 3 | P3-M2: プロンプト A/B | `prompt_variants` の勝率に基づくロールアウトが動作 |

---

## 5. リスクと優先順位

### 高優先（最初に取り組むべき）

| リスク | 内容 | 対策 |
|--------|------|------|
| 安全な自律実行の欠如 | `require_confirm` が未実装のため、高リスクアクションが無承認で実行される | **Phase 0 を最優先** |
| フィードバックデータ不在 | 学習ループの材料となる正規化されたフィードバックがない | Phase 1 を Phase 0 直後に開始 |
| 承認疲労 | 承認依頼が多すぎるとユーザーが機械的に承認 | 段階的自律、優先度スコアリング、スヌーズ機能 |

### 中優先（並行で進める）

| リスク | 内容 | 対策 |
|--------|------|------|
| 閾値暴走 | フィードバック偏りで閾値が極端化 | オフセット上下限制限、承認制 |
| Hallucinated ルール | LLM/マイニングが存在しないデバイスを参照 | backend validation、承認制 |
| 計算コスト | River/mlxtend 等のライブラリ導入によるオーバヘッド | オンラインは軽量モデル、学習は夜間バッチ |

### 低優先（後回しにできる）

| リスク | 内容 | 対策 |
|--------|------|------|
| Sim-to-real gap | シミュレーションと実世界のずれ | Phase 4 以降で SafetyGate・継続的キャリブレーション |
| Reward hacking | LLM が報酬指標を騙す | Phase 5 で多角的報酬、hard guardrail |
| 未観測交絡 | ユーザーの気分等が観測できない | Phase 4 で感度分析、単純モデル優先 |

### 優先順位まとめ

```
1. Phase 0（安全基盤）← 即着手
2. Phase 1（フィードバック基盤）← Phase 0 終了後または後半から並行
3. Phase 2（適応的閾値）← Phase 1 と並行開始可能
4. Phase 3（ルール/プロンプト学習）← Phase 1/2 後
5. Phase 4（因果推論・デジタルツイン）← Phase 1/2/3 後
6. Phase 5（RLHF）← Phase 1/3 後
```

---

## 6. Phase 0 具体計画

### 目的

高リスク・不可逆アクション実行前の人間承認（HITL）と、実行後の異常/棄却に対するロールバックを実装する。

### 期間

6〜8 週間

### タスク順序と依存関係

```
Week 1: スキーマ整備
   └─▶ Week 2: リスク分類器
          └─▶ Week 3: 承認 API
                 └─▶ Week 4-5: Brain 側承認ゲート
                        ├─▶ Week 5-6: ロールバック
                        └─▶ Week 6-7: Frontend UI
                               └─▶ Week 7-8: 監査ログ & 統合テスト
```

### タスク詳細

| # | タスク | 期間 | 依存 | 確認ポイント |
|---|--------|------|------|-------------|
| 0.1 | スキーマ整備 | 1 週 | なし | `approvals` / `action_snapshots` / `rollback_log` テーブルが `services/backend/models.py` に追加される |
| 0.2 | 既存テーブル拡張 | 並行 | 0.1 | `automation_rules` に `risk_tier`, `reversibility`, `approval_required`, `auto_rollback_window_seconds` を追加 |
| 0.3 | `intervention_efficacy` 拡張 | 並行 | 0.1 | `approval_id`, `human_decision`, `rolled_back`, `rollback_success`, `efficacy_score` を追加 |
| 0.4 | リスク分類器 | 1 週 | 0.2 | `action_risk_classifier.py` がルール/アクションを `low/medium/high/critical` に分類 |
| 0.5 | 承認 API | 1 週 | 0.1 | `services/backend/routers/approvals.py` で POST/GET/Decide/Timeout API が動作 |
| 0.6 | backend 承認キュー | 並行 | 0.5 | `services/backend/approval_queue.py` が pending 承認を管理 |
| 0.7 | Brain 承認ゲート | 1.5 週 | 0.4, 0.5 | `approval_gate.py` が `require_confirm=true` 時に実行を停止し承認待ち |
| 0.8 | 承認クライアント | 並行 | 0.7 | `services/brain/src/approval/client.py` が backend API をポーリング |
| 0.9 | ロールバックプランナー | 1.5 週 | 0.7 | `rollback_planner.py` が補償操作または状態復元プランを生成 |
| 0.10 | ロールバック実行器 | 並行 | 0.9 | `rollback_executor.py` がプランを実行 |
| 0.11 | 検証ウォッチャー | 並行 | 0.10 | `verification_watcher.py` がロールバック後の状態を確認 |
| 0.12 | Frontend UI | 1 週 | 0.5 | `ApprovalQueue.tsx` / `ApprovalCard.tsx` / `app/approvals/page.tsx` から操作可能 |
| 0.13 | 監査ログ | 0.5 週 | 0.7 | `audit_logger.py` が `event_store` に承認フローイベントを記録 |
| 0.14 | 統合テスト | 1 週 | 0.9, 0.12, 0.13 | 承認 → 実行 → 棄却 → ロールバックの E2E テスト |

### Phase 0 受入基準

- `require_confirm=true` のルールがトリガされた際、`pending` 承認リクエストが作成される
- 承認 API 経由で `approve` / `reject` / `modify` を判定でき、Brain が実行/キャンセル/再承認を行う
- 実行前後のデバイス/ルール状態が `action_snapshots` に記録される
- 棄却または異常検知時に `RollbackPlanner` / `RollbackExecutor` により補償操作または状態復元が実行される
- 承認フロー全体のイベントが `event_store` に監査ログとして記録される
- Frontend 承認キュー UI から承認/棄却/修正が操作できる

---

## 7. Phase 1 具体計画

### 目的

ユーザーからの承認/棄却/上書き/スヌーズ等のフィードバックを正規化して収集し、デバイス制御・シーン実行・LLM タスク全般の介入効果を測定する。

### 期間

5〜6 週間

### タスク順序と依存関係

```
Week 1: スキーマ整備
   └─▶ Week 2: FeedbackCollector
          ├─▶ Week 3: 明示フィードバック UI
          ├─▶ Week 3-4: 暗黙フィードバック検出
          ├─▶ Week 4-5: Outcome Reward
          └─▶ Week 5-6: Trajectory 記録
                 └─▶ Week 6-7: 統合テスト
```

### タスク詳細

| # | タスク | 期間 | 依存 | 確認ポイント |
|---|--------|------|------|-------------|
| 1.1 | スキーマ整備 | 1 週 | Phase 0 完了 | `agent_feedback` / `agent_trajectories` テーブルが `event_store` に作成 |
| 1.2 | 既存テーブル拡張 | 並行 | 1.1 | `intervention_efficacy`, `llm_decisions`, `device_action_log` に必要列を追加 |
| 1.3 | `event_store` writer 拡張 | 並行 | 1.1 | `record_decision`, `record_intervention_created`, `mark_intervention_completed` を提供 |
| 1.4 | FeedbackCollector | 1 週 | 1.1, 1.3 | `services/brain/src/feedback/collector.py` が明示/暗黙/AI judge フィードバックを正規化 |
| 1.5 | 明示フィードバック UI | 1 週 | 1.4 | `FeedbackButtons.tsx` / `VoiceEventCard.tsx` / `TaskCard.tsx` から 👍/👎/取り消し/再実行 |
| 1.6 | 暗黙フィードバック検出 | 1 週 | 1.4 | `implicit_detector.py` が承認後の手動上書きや即時取り消しを検出 |
| 1.7 | OutcomeReward | 1 週 | 1.4, 1.6 | `outcome_reward.py` がタスク完了/センサー変化から報酬スコアを計算 |
| 1.8 | TrajectoryRecorder | 1 週 | 1.4 | `trajectory_recorder.py` が LLM 決定軌跡を記録 |
| 1.9 | Feedback API | 並行 | 1.4 | `services/backend/routers/feedback.py` が `POST /feedback` を提供 |
| 1.10 | 統合テスト | 1 週 | 1.5, 1.7, 1.8 | フィードバック収集 → 介入効果計算 → DB 永続化の E2E テスト |

### Phase 1 受入基準

- `agent_feedback` / `agent_trajectories` テーブルが作成されている
- `intervention_efficacy`, `llm_decisions`, `device_action_log` の拡張が適用されている
- `FeedbackCollector`, `ImplicitFeedbackDetector`, `OutcomeRewardCalculator`, `TrajectoryRecorder` が実装されている
- `POST /feedback` API が動作している
- Frontend のフィードバック UI（👍/👎、取り消し、再実行）が組み込まれている
- Phase 0 の `approval_id` / `human_decision` が `intervention_efficacy` と紐付けられている

---

## 8. 必要なリソース・前提条件・実装上の注意点

### 前提条件

- `AutomationRule` テーブルが存在し、`require_confirm` 列が定義されている
- `services/brain/src/automation_engine.py` が backend から rules を pull して評価・実行している
- `tool_executor.py` / `scene_executor.py` がアクション実行を担っている
- Mosquitto MQTT broker が動作している
- `event_store/writer.py` が `record_decision`, `record_intervention_created`, `mark_intervention_completed` を提供している
- `services/brain/src/efficacy.py` が verdict 計算を行っている

### 必要なリソース

| リソース | 用途 | 備考 |
|---------|------|------|
| PostgreSQL | 承認/ロールバック/学習テーブルの永続化 | SQLite でも可だが、Phase 4 の統計関数では PostgreSQL 推奨 |
| Mosquitto MQTT | HITL/Feedback/Threshold イベントの非同期通信 | 既存インフラを流用 |
| River | Phase 2 のドリフト検知 | `river>=0.21`, MIT ライセンス |
| mlxtend / scikit-learn | Phase 3 のルール学習 | 個人運用・ローカル優先 |
| xgboost / lightgbm | Phase 3 の予測モデル | オプション |
| dowhy / econml / causalml | Phase 4 の因果推論 | 計算コスト高め |
| pyenergyplus / eppy / fmpy | Phase 4 のデジタルツイン | 家屋メタデータが必要 |
| trl / peft / transformers | Phase 5 の LoRA 学習 | GPU または十分な CPU リソース |

### 実装上の注意点

- **安全性第一**: CO₂ 危険、SpO₂ 低下、漏水等の hard safety ルールは学習対象外とする
- **段階的自律**: 新しいルール/閾値/プロンプトは必ず「提案」として始め、承認・A/B 評価を経て自動化
- **監査可能性**: 承認・実行・ロールバック・学習結果はすべて `event_store` または backend DB に immutable に記録
- **ローカル優先**: 個人運用・PolyForm Noncommercial License の特性上、学習・推論は可能な限りローカル（Ollama + SQLite/Postgres）
- **最小侵襲**: 既存の 30 秒サイクル、MQTT トピック規約、backend API、frontend 型定義を最大限尊重
- **承認疲労対策**: 承認依頼の優先度スコアリング、スヌーズ、段階的な auto-approve 条件の緩和を設計に組み込む

---

## 9. 今すぐ着手できる最初の 3 つのタスク

### タスク 1: Phase 0 スキーマ整備

- **内容**: `services/backend/models.py` に `approvals`, `action_snapshots`, `rollback_log` テーブルを追加し、`automation_rules` / `intervention_efficacy` を拡張する
- **理由**: 後続すべての前提となる最重要タスク
- **確認ポイント**: Alembic マイグレーション（または SQLAlchemy `create_all`）が成功し、テーブルが作成される
- **期間**: 1 週間

### タスク 2: Phase 0 リスク分類器実装

- **内容**: `services/brain/src/approval/action_risk_classifier.py` を新規作成し、ルール属性（`risk_tier`, `reversibility`, `approval_required`）とアクション内容からリスクスコアを計算する
- **理由**: 承認ゲートの前段として、どのアクションが承認必須かを判定する必要がある
- **確認ポイント**: テストで `critical`/`high`/`medium`/`low` の分類が期待通り動作する
- **期間**: 1 週間
- **依存**: タスク 1 の `automation_rules` 拡張

### タスク 3: Phase 0 承認 API 実装

- **内容**: `services/backend/routers/approvals.py` を新規作成し、`POST /approvals`, `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/decide`, `POST /approvals/{id}/timeout` を実装する
- **理由**: Brain 承認ゲートと Frontend UI が backend を介して連携するための最小 API
- **確認ポイント**: FastAPI `/docs` から各エンドポイントが動作し、`pending`/`approved`/`rejected`/`timed_out` 状態遷移が確認できる
- **期間**: 1 週間
- **依存**: タスク 1

---

## 10. 今後の運用

- 各フェーズ実装前に、本計画と該当詳細計画（`PLAN-phase-*.md`）をレビューし、スコープを確定する
- 必要に応じて各フェーズごとに PoC を実施し、効果を検証してから本格展開する
- 実装進捗に応じて本計画を更新し、陳腐化を防ぐ
- Phase 0/1 の段階で、未活用データフロー（weather alerts、shopping purchased 等）の統合も並行して検討する
