# Task Reminder System

## Overview

一定時間経過した未完了タスクに対して、自動的に**完全な音声通知**を再生成してリマインドするシステムです。

## 設計方針

### ❌ 避けるべき設計
```
リマインド音声: "まだ未完了です、よろしくお願いします"
```
→ 初回音声を聞いていないユーザーには何のことか分からない

### ✅ 採用した設計
```
リマインド音声: "お願いがあります。2階給湯室でコーヒー豆の補充をお願いします。50神保ポイントです。"
```
→ **初回と同じ完全な情報、ただし表現は異なる**（LLMの多様性）

## メリット

1. **初めて聞く人にも分かりやすい**: 完全な情報が含まれている
2. **既に聞いた人にも新鮮**: LLMが毎回異なる表現を生成
3. **シンプルな実装**: 既存の`/api/voice/announce`エンドポイントを再利用

## 実装

### 1. データベース (`models.py`)

```python
class Task(Base):
    # ... existing fields ...
    
    # Reminder tracking
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)
```

### 2. Reminder Service (`task_reminder.py`)

```python
class TaskReminder:
    REMINDER_INTERVAL = 60  # 1時間経過したタスクをチェック
    REMINDER_COOLDOWN = 30  # 30分以内の再リマインドを防止
    CHECK_INTERVAL = 300    # 5分ごとにチェック
```

**処理フロー:**
1. 定期的に（5分ごと）未完了タスクをチェック
2. 作成から1時間以上経過したタスクを検出
3. 同じエンドポイント（`/api/voice/announce`）で新しい音声を生成
4. `last_reminded_at`タイムスタンプを更新
5. 30分経過するまで同じタスクはリマインドしない

### 3. Brain統合 (`main.py`)

```python
class Brain:
    def __init__(self):
        # ...
        self.task_reminder = TaskReminder()
    
    async def run(self):
        # ...
        # Start reminder service as background task
        asyncio.create_task(self.task_reminder.run_periodic_check())
```

### 4. Backend API (`routers/tasks.py`)

新しいエンドポイント:

```python
@router.put("/{task_id}/reminded")
async def mark_task_reminded(task_id: int, db: AsyncSession = Depends(get_db)):
    """Update the last_reminded_at timestamp for a task."""
    task.last_reminded_at = func.now()
    await db.commit()
    return task
```

## 設定

環境変数で調整可能:

```bash
# リマインド対象の閾値（分）
REMINDER_INTERVAL_MINUTES=60

# リマインド間隔の最小値（分）
REMINDER_COOLDOWN_MINUTES=30

# チェック間隔（秒）
REMINDER_CHECK_INTERVAL_SECONDS=300
```

## 使用例

### シナリオ: 人がいない時にタスクが発注された

```
09:00 - タスク作成: "会議室Aの掃除"
        → 音声A: "お願いがあります。2階会議室Aの掃除をお願いします。30ポイントです。"
        （誰もいなくて聞いていない）

10:00 - リマインダーチェック（1時間経過）
        → 音声B: "2階会議室Aで掃除をお願いできますか？30神保ポイントを獲得できます。"
        （異なる表現、でも完全な情報）

10:30 - 誰かがオフィスに来て、音声Bを聞く
        → 何をすべきか完全に理解できる ✓

11:00 - 2回目のリマインダーチェック
        → まだ30分経っていないのでスキップ（cooldown）

11:30 - 3回目のリマインダーチェック
        → 音声C: "会議室Aの掃除作業をお願いします。報酬は30ポイントです。"
        （さらに別の表現）
```

## テスト

```bash
# リマインダーシステムのテスト
python3 infra/tests/integration/test_reminder_system.py

# 実際の動作確認
# 1. サービスを起動
docker-compose up -d

# 2. タスクを作成
# 3. 1時間待つ（または REMINDER_INTERVAL_MINUTES を短く設定）
# 4. Brainログで自動リマインドを確認
docker logs -f hems-brain
```

## ログ出力例

```
[INFO] TaskReminder initialized - interval: 60m, cooldown: 30m
[INFO] TaskReminder service started
...
[INFO] Found 2 tasks needing reminders
[INFO] Sending reminder for task #5: コーヒー豆の補充
[INFO] Generating reminder audio for task: コーヒー豆の補充
[INFO] Reminder audio generated: お願いがあります。給湯室でコーヒー豆の補充をお願いします...
[INFO] ✓ Reminder sent for task #5: コーヒー豆の補充
```

## データベーススキーマ更新

新しいフィールドを追加したため、データベースリセットが必要:

```bash
docker-compose down
docker volume rm infra_hems_db_data
docker-compose up -d
```

## 今後の拡張案

1. **段階的緊急度**: 時間経過に応じて緊急度を上げる
2. **リマインド回数**: 3回リマインドしても未完了なら別の対応
3. **時間帯考慮**: 夜間はリマインドしない
4. **動的間隔**: タスクの緊急度に応じてリマインド間隔を調整
