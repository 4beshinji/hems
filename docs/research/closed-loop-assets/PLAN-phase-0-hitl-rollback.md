# Phase 0: HITL・承認・ロールバック基盤

> 本計画は HEMS における高リスク・不可逆アクションの実行前承認（HITL）と、誤実行/棄却時のロールバック機構を構築するための詳細計画です。
> 前提調査: [hitl-rollback-approval.md](./hitl-rollback-approval.md)

---

## 1. 目的

- `services/backend/models.py` に存在する `AutomationRule.require_confirm` を `services/brain/src/automation_engine.py` で参照し、重大自動アクション前の人間承認を実装する。
- 承認フローの状態機械、キュー、タイムアウト、監査証跡を構築する。
- 実行後の異常/棄却に対するロールバック（状態復元・補償操作）を実装する。

---

## 2. スコープ

### 含む

- `AutomationRule.require_confirm` の評価
- 承認リクエストの作成・照会・判定 API
- 承認待ちアクションの非同期実行
- 実行前後のデバイス/ルール状態スナップショット
- ロールバックプランの生成と実行
- Frontend 承認キュー UI
- event_store への監査ログ記録

### 含まない

- LLM ReAct loop 全体の LangGraph 化（参考に留める）
- Temporal 等の外部ワークフローエンジン導入（将来オプション）
- 承認依頼のモバイル通知自体の新規実装（既存 ambient_speaker / mobile 通知基盤を流用）

---

## 3. 前提条件

- `services/backend/models.py` に `AutomationRule` テーブルが存在し、`require_confirm` 列がある。
- `services/brain/src/automation_engine.py` が rules を backend から pull して評価・実行している。
- `services/brain/src/tool_executor.py` / `services/brain/src/scene_executor.py` がアクション実行を担っている。
- Mosquitto MQTT broker が動作している。

---

## 4. スキーマ変更

### 4.1 `approvals` テーブル（新規）

```python
class Approval(Base):
    __tablename__ = "approvals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(String, nullable=True, index=True)
    action_type = Column(String, nullable=False)  # device_control, scene, rule_promotion, config_change
    risk_tier = Column(String, nullable=False, default="low")  # safe, low, medium, high, critical
    reversibility = Column(String, nullable=False, default="reversible")  # reversible, compensatable, irreversible
    confidence = Column(Float, nullable=True)
    proposed_payload = Column(JSON, nullable=False, default=dict)
    context = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False, default="proposed")  # proposed, pending, approved, rejected, modified, expired, rolled_back
    reviewer_id = Column(String, nullable=True)
    decision = Column(String, nullable=True)  # approve, reject, modify
    decision_reason = Column(String, nullable=True)
    requested_at = Column(TZDateTime(timezone=True), server_default=func.now())
    decided_at = Column(TZDateTime(timezone=True), nullable=True)
    expires_at = Column(TZDateTime(timezone=True), nullable=True)
    executed_at = Column(TZDateTime(timezone=True), nullable=True)
    rollback_plan = Column(JSON, nullable=True)
    rollback_status = Column(String, nullable=True, default="none")  # none, pending, success, failed
    audit_log = Column(JSON, nullable=False, default=list)
```

### 4.2 `action_snapshots` テーブル（新規）

```python
class ActionSnapshot(Base):
    __tablename__ = "action_snapshots"
    id = Column(Integer, primary_key=True)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approvals.id"), nullable=False, index=True)
    entity_type = Column(String, nullable=False)  # device, scene, rule, config
    entity_id = Column(String, nullable=False)
    before_state = Column(JSON, nullable=False, default=dict)
    after_state = Column(JSON, nullable=True)
    captured_at = Column(TZDateTime(timezone=True), server_default=func.now())
```

### 4.3 `rollback_log` テーブル（新規）

```python
class RollbackLog(Base):
    __tablename__ = "rollback_log"
    id = Column(Integer, primary_key=True)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approvals.id"), nullable=False, index=True)
    trigger = Column(String, nullable=False)  # human_reject, verification_failure, timeout, policy_violation
    compensation_plan = Column(JSON, nullable=True)
    execution_status = Column(String, nullable=True)
    started_at = Column(TZDateTime(timezone=True), server_default=func.now())
    completed_at = Column(TZDateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)
```

### 4.4 既存テーブルの拡張

```python
# automation_rules
class AutomationRule(Base):
    # ... existing columns ...
    risk_tier = Column(String, nullable=True, default="low")
    reversibility = Column(String, nullable=True, default="reversible")
    approval_required = Column(Boolean, default=False)
    auto_rollback_window_seconds = Column(Integer, nullable=True, default=300)

# intervention_efficacy (event_store)
# approval_id, human_decision, rolled_back, rollback_success, efficacy_score を追加
```

---

## 5. 新規コンポーネント

| コンポーネント | 配置 | 責務 |
|--------------|------|------|
| `ActionRiskClassifier` | `services/brain/src/approval/action_risk_classifier.py` | 提案行動の risk_tier / reversibility / confidence を判定 |
| `ApprovalGate` | `services/brain/src/approval/approval_gate.py` | 承認が必要な行動を検出し、backend に承認リクエストを発行 |
| `ApprovalClient` | `services/brain/src/approval/client.py` | Brain から backend 承認 API を呼び出す |
| `RollbackPlanner` | `services/brain/src/approval/rollback_planner.py` | 失敗/拒否時の補償操作列を生成 |
| `RollbackExecutor` | `services/brain/src/approval/rollback_executor.py` | 補償操作を実行し結果を検証 |
| `VerificationWatcher` | `services/brain/src/approval/verification_watcher.py` | 実行後の状態を監視し、異常を検知 |
| `ApprovalQueueManager` | `services/backend/approval_queue.py` | backend 側の承認リクエスト CRUD、タイムアウト、通知発行 |
| `AuditLogger` | `services/brain/src/approval/audit_logger.py` | 承認・実行・rollback の immutable ログを event_store へ書き込み |

---

## 6. 変更対象ファイル

### 6.1 Backend

- `services/backend/models.py` — 新規テーブル・列追加
- `services/backend/schemas.py` — Pydantic schema 追加
- `services/backend/database.py` — Alembic migration or lifespan ALTER
- `services/backend/routers/approvals.py` — 新規（承認 API）
- `services/backend/routers/automations.py` — `require_confirm` 更新対応
- `services/backend/main.py` — router 登録

### 6.2 Brain

- `services/brain/src/automation_engine.py` — `_fire` で承認ゲート挿入
- `services/brain/src/tool_executor.py` — スナップショット取得 hook
- `services/brain/src/scene_executor.py` — シーン実行前後のスナップショット
- `services/brain/src/brain_cognitive.py` — 承認結果待ちの非同期処理
- `services/brain/src/brain_mqtt.py` — 承認判定 MQTT トピック購読
- `services/brain/src/main.py` — 新規コンポーネントの wire

### 6.3 Frontend

- `services/frontend/src/components/ApprovalQueue.tsx` — 新規
- `services/frontend/src/components/ApprovalCard.tsx` — 新規
- `services/frontend/src/app/approvals/page.tsx` — 新規
- `services/frontend/src/types.ts` — Approval 型追加
- `services/frontend/src/lib/api.ts` — API client 追加

---

## 7. 実装ステップ

### Step 1: スキーマ整備（1 週間）

1. `approvals` / `action_snapshots` / `rollback_log` テーブルを `backend/models.py` に追加。
2. `AutomationRule` に `risk_tier` / `reversibility` / `approval_required` / `auto_rollback_window_seconds` を追加。
3. Alembic migration を生成（SQLite 既存環境向けに `DROP TABLE` 再作成 or `ALTER TABLE` fallback も検討）。
4. Pydantic schema を `backend/schemas.py` に追加。

### Step 2: リスク分類器（1 週間）

1. `ActionRiskClassifier` を実装。
   - 入力: action_type, device_id, params, current_state
   - 出力: risk_tier, reversibility, confidence
2. ルールベースの分類マトリクスを定義。
   - 例: `lock`, `security`, `high_voltage` → critical / irreversible
   - 例: `light.brightness` → low / reversible
3. テストを追加。

### Step 3: 承認 API（1 週間）

1. `services/backend/routers/approvals.py` を新規作成。
   - `POST /approvals` — 承認リクエスト作成
   - `GET /approvals` — 承認キュー一覧
   - `GET /approvals/{id}` — 詳細
   - `POST /approvals/{id}/decide` — 承認/棄却/修正
   - `POST /approvals/{id}/timeout` — タイムアウト処理
2. `ApprovalQueueManager` を実装（タイムアウト処理、通知発行）。
3. backend main.py に router 登録。

### Step 4: Brain 側承認ゲート（1.5 週間）

1. `ApprovalGate` を実装。
   - `AutomationEngine._fire` 終了後、承認が必要か判定。
   - 必要なら backend `POST /approvals` を呼び出し、status を `pending` にして非同期待機。
2. `ApprovalClient` を実装。
3. `brain_mqtt.py` に `hems/approvals/{id}/decide` 購読を追加。
   - 承認されたら `hems/actions/{id}/execute` を発行。
   - 棄却されたら RollbackPlanner を呼ばずにキャンセル。
   - 修正されたら proposed_payload を更新して再承認。
4. 承認待ち中もメイン 30 秒サイクルはブロックしない設計。

### Step 5: ロールバック（1.5 週間）

1. `action_snapshots` に実行前後の状態を保存する hook を `tool_executor.py` / `scene_executor.py` に追加。
2. `RollbackPlanner` を実装。
   - デバイス状態復元: before_state を書き戻す。
   - 補償操作: 逆アクションを生成（例: ON → OFF）。
3. `RollbackExecutor` を実装。
   - MQTT 経由でデバイス制御を実行。
   - 実行結果を `rollback_log` に記録。
4. `VerificationWatcher` を実装。
   - 実行後 N 分間、関連センサー/デバイス状態を監視。
   - 異常検知時にロールバックをトリガ。

### Step 6: Frontend UI（1 週間）

1. `ApprovalQueue` コンポーネントを実装。
   - 承認/棄却/修正ボタン
   - 行動プレビュー、理由説明、影響範囲表示
2. Dashboard 上部に承認依頼の sticky banner または toast 通知。
3. 承認履歴ページを実装。

### Step 7: 監査ログ（0.5 週間）

1. `AuditLogger` を実装。
2. `event_store` に `approval_requested`, `approval_decided`, `action_executed`, `rollback_executed` 等を記録。

### Step 8: 統合テスト（1 週間）

1. mock LLM / virtual edge を使った end-to-end テスト。
2. 承認→実行→完了、承認→実行→ロールバック、タイムアウト棄却のシナリオ。
3. `tests/security/` に承認 API の認証・認可テストを追加。

---

## 8. 検証方法

```bash
# 1. 高リスクルールを作成（require_confirm=true）
curl -X POST http://localhost:8010/automations/ \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": " test_critical",
    "trigger_type": "sensor_threshold",
    "trigger_config": {"device_id": "test.plug", "channel": "power", "op": ">", "value": 1000},
    "actions": [{"device_id": "test.plug", "action": "turn_off"}],
    "require_confirm": true,
    "risk_tier": "high",
    "reversibility": "compensatable"
  }'

# 2. トリガを発火させ、frontend/承認 API で承認
mosquitto_pub -t 'hems/sensors/living/test.plug/power' -m '{"value": 1500}'

# 3. 承認キューに追加されたことを確認
curl http://localhost:8010/approvals?status=pending

# 4. 承認判定
curl -X POST http://localhost:8010/approvals/{id}/decide \
  -H "Authorization: Bearer $BACKEND_API_KEY" \
  -d '{"decision": "approve", "reason": "OK"}'

# 5. 実行とロールバックのログを確認
docker logs hems-brain | grep -E "approval|rollback"
sqlite3 data/hems.db "SELECT * FROM approvals WHERE status='rolled_back'"
```

---

## 9. リスクと対策

| リスク | 対策 |
|--------|------|
| 承認待ちで緊急時対応が遅れる | 緊急度に応じたタイムアウト、危険時は auto_execute |
| ロールバック不能な副作用 | 事前に可逆性分類、不能時は人間への緊急通知 |
| 状態不整合・競合 | 楽観的ロック/バージョン番号、競合検知時は人間確認 |
| 承認 UI のなりすまし | JWT 検証、トピック ACL、`BACKEND_API_KEY` / `HEMS_INTERNAL_TOKEN` 分離 |
| Reviewer overload | 段階的自律、信頼性に応じて承認対象を絞る |

---

## 10. 工数感

- 合計: **6〜8 週間**（1〜2 ヶ月）
- 想定: 1 名フルタイム or 2 名で並行

---

## 11. 次フェーズ接続

- Phase 0 で収集した承認/棄却/修正データは、Phase 1 の `FeedbackCollector` / Phase 3 の `RuleLearner` に入力される。
- `intervention_efficacy` への `approval_id` / `human_decision` 紐付けは Phase 1 で活用。
- ロールバック成功/失敗の履歴は Phase 3 のルール信頼度学習に利用。
