# VOICEVOX Voice Notification Service

ナースロボ＿タイプＴの声でタスクを親しみやすく読み上げるサービスです。

## 概要

このサービスは以下の機能を提供します：

1. **タスク発注時の音声通知**: BrainサービスがタスクをDashboardに登録する際、自動的にVOICEVOXで音声を生成し読み上げます
2. **二重音声生成 (Dual Voice)**: タスク作成時にアナウンスと完了メッセージを同時生成
3. **リジェクション音声ストック**: アイドル時にLLM+VOICEVOXで拒否音声を事前生成 (最大100件)
4. **通貨単位ランダム化**: アイドル時にLLMでユーモラスな通貨単位名を事前生成 (テキストのみ, 最大50件)。タスク告知のたびにランダムな単位名を使用
5. **直接音声合成**: `speak` ツールやタスク受諾時の定型フレーズ合成
6. **LLM統合**: タスクデータから自然な日本語文章をLLMで生成
7. **多様性重視**: 同じ内容でも毎回異なる表現を使用

## アーキテクチャ

```
Brain Service ──┬──→ voice /announce_with_completion ──→ LLM → 文章生成
                │                                        ↓
                │                                    VOICEVOX → MP3生成
                │
Frontend ───────┼──→ voice /synthesize (受諾: 定型フレーズ)
                │
                └──→ voice /rejection/random (無視: ストックから即座)

Background ─────┬─ idle_generation_loop → リジェクション音声事前生成
                └─ idle_currency_generation_loop → 通貨単位名事前生成
```

## 使用技術

- **VOICEVOX Engine**: CPU版（LLMとのリソース競合を避けるため）
- **Voice Character**: ナースロボ＿タイプＴ (Speaker ID: 47)
- **FastAPI**: Voice Service API
- **LLM**: 自然な日本語文章生成 (mock-llm or Ollama)
- **Audio Format**: MP3

## ディレクトリ構成

```
services/voice/
├── Dockerfile
├── requirements.txt
├── voicevox/
│   └── Dockerfile             # VOICEVOX Engine コンテナ
├── CONTEXT_AWARE_COMPLETION.md # Dual Voice 設計ドキュメント
└── src/
    ├── main.py                # FastAPI アプリケーション (11エンドポイント)
    ├── models.py              # Pydantic リクエスト/レスポンスモデル
    ├── voicevox_client.py     # VOICEVOX REST API クライアント
    ├── speech_generator.py    # LLM統合・文章生成パイプライン + 通貨単位生成
    ├── rejection_stock.py     # リジェクション音声事前生成 (max 100)
    └── currency_unit_stock.py # 通貨単位名ストック (テキストのみ, max 50)
```

## API エンドポイント

### `POST /api/voice/synthesize`
テキストを直接音声合成（LLMテキスト生成をスキップ）。`speak` ツールやタスク受諾時に使用。

**Request:**
```json
{
  "text": "了解しました。頑張ってください。",
  "tone": "caring"
}
```

**Response:**
```json
{
  "audio_url": "/audio/speak_abc123.mp3",
  "text_generated": "了解しました。頑張ってください。",
  "duration_seconds": 2.5
}
```

### `POST /api/voice/announce`
タスクをLLMで自然な文章に変換し、音声合成。

**Request:**
```json
{
  "task": {
    "title": "コーヒー豆の補充",
    "description": "給湯室のコーヒー豆がなくなっています",
    "location": "給湯室",
    "bounty_gold": 1500,
    "urgency": 2,
    "zone": "main"
  }
}
```

**Response:**
```json
{
  "audio_url": "/audio/task_abc123.mp3",
  "text_generated": "お願いがあります。給湯室でコーヒー豆の補充をお願いします。1500ポイント獲得できます。",
  "duration_seconds": 5.2
}
```

### `POST /api/voice/announce_with_completion`
二重音声生成: アナウンス + 文脈に合った完了メッセージを同時生成。Brain → DashboardClient から使用。

**Response:**
```json
{
  "announcement_audio_url": "/audio/task_announce_abc.mp3",
  "announcement_text": "...",
  "announcement_duration": 5.2,
  "completion_audio_url": "/audio/task_complete_def.mp3",
  "completion_text": "...",
  "completion_duration": 3.1
}
```

### `POST /api/voice/feedback/{feedback_type}`
フィードバックメッセージを生成。

**Feedback Types:**
- `task_completed`: タスク完了時の応答
- `task_accepted`: タスク受諾時の応答

### `GET /api/voice/rejection/random`
ストックからランダムなリジェクション音声を即座に返却（合成待ち時間なし）。
ストックが空の場合はオンデマンド生成にフォールバック。

**Response:**
```json
{
  "audio_url": "/audio/rejections/rejection_001_abc.mp3",
  "text": "あら、今回はスルーですか。まあ、タイミングってありますよね。"
}
```

### `GET /api/voice/rejection/status`
リジェクション音声ストックの状態を返却。

**Response:**
```json
{
  "stock_count": 42,
  "max_stock": 100,
  "is_generating": false,
  "needs_refill": false
}
```

### `POST /api/voice/rejection/clear`
ストックを全削除し再生成を開始。

### `GET /api/voice/currency-units/status`
通貨単位名ストックの状態を返却。

**Response:**
```json
{
  "stock_count": 35,
  "max_stock": 50,
  "needs_refill": false,
  "sample": "お手伝いポイント"
}
```

### `POST /api/voice/currency-units/clear`
通貨単位名ストックを全削除し再生成を開始。

### `GET /audio/{filename}`
生成済み音声ファイル (MP3) を配信。

### `GET /audio/rejections/{filename}`
リジェクションストックの音声ファイルを配信。

## セットアップ

### 1. Docker Compose で起動

```bash
docker compose -f infra/docker-compose.yml up -d voicevox voice-service
```

### 2. サービス確認

```bash
# VOICEVOX Engine
curl http://localhost:50021/version

# Voice Service
curl http://localhost:8002/

# リジェクションストック状態
curl http://localhost:8002/api/voice/rejection/status
```

### 3. nginx 経由アクセス (Frontend から)

Frontend の nginx がリバースプロキシとして動作:
- `/api/voice/*` → `voice-service:8000`
- `/audio/*` → `voice-service:8000`

## 環境変数

### Voice Service (`voice-service` container)

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `VOICEVOX_URL` | `http://voicevox:50021` | VOICEVOX Engine URL |
| `LLM_API_URL` | `http://mock-llm:8000/v1` | LLM API URL |
| `LLM_MODEL` | (env) | Ollama モデル名 |

### Dashboard Client (Brain 側)

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `VOICE_SERVICE_URL` | `http://voice-service:8000` | Voice Service URL |

## 設計方針

### CPU版 VOICEVOX
LLMとGPUリソースの競合を避けるため、VOICEVOX CPU版を使用しています。

### リジェクションストック
タスク無視時のレイテンシをゼロにするため、アイドル時にバックグラウンドでLLMテキスト生成+VOICEVOX合成を繰り返し、最大100件のストックを維持します。リクエスト処理中は生成を一時停止し、リソース競合を回避します。

### 通貨単位ランダム化
タスク告知の報酬単位名を毎回ランダムに変化させ、繰り返し聞いても飽きない演出を実現。`currency_unit_stock.py` がアイドル時にLLMで単位名を事前生成（テキストのみ、音声合成不要）。ストックが空の場合はフォールバックリストから選択。キャラクターはコミカルなAI隣人で、たまにAI支配者の本性が漏れる路線。

### 二重音声 (Dual Voice)
タスク作成時に「アナウンス」と「完了メッセージ」を同時生成。完了メッセージはタスク内容に文脈的に関連した表現になります。詳細は [CONTEXT_AWARE_COMPLETION.md](CONTEXT_AWARE_COMPLETION.md) を参照。

### 単一ボイス
ナースロボ＿タイプＴ（Speaker ID: 47）のみを使用します。

## トラブルシューティング

### VOICEVOX Engine が起動しない
```bash
docker logs hems-voicevox
docker restart hems-voicevox
```

### LLM が応答しない
Voice Service はフォールバック機能を持っており、LLM が失敗しても簡易テンプレートで音声を生成します。

### リジェクションストックが貯まらない
```bash
# ストック状態を確認
curl http://localhost:8002/api/voice/rejection/status

# Voice Service のログを確認
docker logs hems-voice | grep -i rejection
```

### 音声が生成されない
```bash
docker logs hems-voice
curl -X POST "http://localhost:50021/audio_query?speaker=47&text=テストです"
```
