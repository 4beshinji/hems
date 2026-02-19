# Context-Aware Completion Voice Implementation

## Overview

タスク作成時に**依頼音声**と**完了時音声**を同時に生成し、完了時音声が依頼内容とリンクするように実装しました。

例：
- **掃除タスク** → 完了時: "ありがとうございます！これで皆が気持ちよく過ごせますね。"
- **コーヒー豆補充** → 完了時: "ありがとうございます！これで美味しいコーヒーが飲めますね。"
- **備品補充** → 完了時: "ありがとうございます！これで作業がスムーズに進みます。"

## Architecture Flow

```
1. Brain Service (create_task)
   ↓
2. → Voice Service (/api/voice/announce_with_completion)
   ├─ LLM: Generate announcement text
   ├─ LLM: Generate contextual completion text (linked to task)
   ├─ VOICEVOX: Synthesize announcement audio
   └─ VOICEVOX: Synthesize completion audio
   ↓
3. Return both audio URLs + texts to Brain
   ↓
4. Brain → Backend: Create task with voice data
   ↓
5. Backend: Store task with voice URLs in database
   ↓
6. On task completion: Play completion_audio_url
```

## Implementation Changes

### 1. Backend Database (`services/dashboard/backend/models.py`)

Added voice data fields to `Task` model:

```python
# Voice announcement fields
announcement_audio_url = Column(String, nullable=True)
announcement_text = Column(String, nullable=True)
completion_audio_url = Column(String, nullable=True)
completion_text = Column(String, nullable=True)
```

### 2. Backend Schemas (`services/dashboard/backend/schemas.py`)

Added voice fields to `TaskBase` and `Task` schemas:

```python
# Voice data (optional, provided by Brain if voice enabled)
announcement_audio_url: Optional[str] = None
announcement_text: Optional[str] = None
completion_audio_url: Optional[str] = None
completion_text: Optional[str] = None
```

### 3. Voice Service (`services/voice/src/`)

#### New Endpoint: `/api/voice/announce_with_completion`

Generates both announcement and completion voices simultaneously.

**Request:**
```json
{
  "task": {
    "title": "掃除機をかける",
    "description": "オフィスの床を掃除してください",
    "location": "オフィス",
    "bounty_gold": 30,
    "urgency": 1,
    "zone": "1F"
  }
}
```

**Response:**
```json
{
  "announcement_audio_url": "/audio/task_announce_xxx.wav",
  "announcement_text": "お願いがあります。1階オフィスで掃除機をかけてください。30神保ポイントです。",
  "announcement_duration": 5.2,
  "completion_audio_url": "/audio/task_complete_yyy.wav",
  "completion_text": "ありがとうございます！これで皆が気持ちよく過ごせますね。",
  "completion_duration": 3.8
}
```

#### New Method: `SpeechGenerator.generate_completion_text()`

Generates contextual completion text based on task content:

```python
async def generate_completion_text(self, task: Task) -> str:
    """
    Generate contextual completion message linked to task content.
    - 掃除タスク → "これで皆が気持ちよく過ごせます"
    - コーヒー豆 → "これで美味しいコーヒーが飲めます"
    - 備品補充 → "これで作業がスムーズに進みます"
    """
```

### 4. Brain Service (`services/brain/src/dashboard_client.py`)

Updated `create_task` method:

```python
async def create_task(self, ...):
    # Generate dual voice BEFORE task creation
    voice_data = await self._generate_dual_voice(task_data)
    
    # Include voice data in task creation payload
    payload = {
        "title": title,
        ...
        "announcement_audio_url": voice_data["announcement_audio_url"],
        "announcement_text": voice_data["announcement_text"],
        "completion_audio_url": voice_data["completion_audio_url"],
        "completion_text": voice_data["completion_text"]
    }
    
    # Create task with voice data
    await backend.create_task(payload)
```

## Usage

### Creating a Task with Voice

```python
from dashboard_client import DashboardClient

client = DashboardClient(enable_voice=True)

# Automatically generates both announcement and completion voices
await client.create_task(
    title="コーヒー豆の補充",
    description="給湯室のコーヒー豆がなくなっています",
    bounty=50,
    urgency=2,
    zone="2F"
)
```

**What happens:**
1. Voice service generates announcement: "お願いがあります。2階給湯室でコーヒー豆の補充をお願いします..."
2. Voice service generates completion: "ありがとうございます！これで美味しいコーヒーが飲めますね。"
3. Both audio files are created and URLs stored in database
4. Task created with voice URLs

### Playing Completion Voice

When a task is marked complete, retrieve and play the `completion_audio_url`:

```python
# Get task details
task = await backend.get_task(task_id)

# Play completion audio
completion_url = task["completion_audio_url"]
# → http://voice-service:8000/audio/task_complete_xxx.wav

# Play the audio (implementation depends on frontend/client)
# Example: audio_player.play(completion_url)
```

### API Access

```bash
# Direct API call to voice service
curl -X POST http://localhost:8002/api/voice/announce_with_completion \
  -H "Content-Type: application/json" \
  -d '{
    "task": {
      "title": "掃除機をかける",
      "description": "オフィスの床を掃除してください",
      "location": "オフィス",
      "bounty_gold": 30,
      "urgency": 1,
      "zone": "1F"
    }
  }'

# Download and play audio
curl http://localhost:8002/audio/task_announce_xxx.wav -o announcement.wav
curl http://localhost:8002/audio/task_complete_xxx.wav -o completion.wav
aplay announcement.wav
aplay completion.wav
```

## Database Schema Update

The database will need to be reset to apply the new schema:

```bash
# Stop services
cd infra
docker-compose down

# Remove database to force recreation
docker volume rm infra_soms_db_data

# Restart services (schema will be recreated)
docker-compose up -d
```

## Benefits

1. **Contextual Feedback**: Completion messages are linked to task content, making them more meaningful
2. **Consistent Experience**: Same voice and style for announcement and completion
3. **Reduced Latency**: Both voices generated upfront, no delay on completion
4. **Better UX**: Users hear relevant feedback like "これで皆が気持ちよく過ごせます" instead of generic "ありがとうございます"

## LLM Prompt for Completion

The completion prompt includes task details to generate contextual responses:

```
以下のタスクが完了しました。完了への感謝と、そのタスクがもたらす効果を含めた応答を70文字以内で生成してください。

【完了したタスク】
- タイトル: {task.title}
- 説明: {task.description}
- 場所: {task.location}
- エリア: {task.zone}

【制約】
- 70文字以内
- 親しみやすく温かい口調
- タスクの完了がもたらす効果を含める
- 毎回異なる表現を使用してバリエーションを出す
```

This ensures the completion voice is always relevant to the specific task.
