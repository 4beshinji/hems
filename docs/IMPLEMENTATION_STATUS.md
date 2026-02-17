# SOMS 実装状態レポート

**生成日**: 2026-02-13
**ブランチ**: `main` (HEAD: `5a8bdfc`)
**未コミット**: 12ファイル変更 + 5新規 + 1マージコンフリクト

---

## 全体サマリー

| カテゴリ | ファイル数 | 行数 | 状態 |
|----------|-----------|------|------|
| Brain (LLM決定エンジン) | 17 .py | 2,474 | 完成・本番対応 |
| Voice (音声合成) | 5 .py | 864 | 完成・本番対応 |
| Perception (画像認識) | ~20 .py | 1,687 | 完成・本番対応 |
| Dashboard Backend | 9 .py | 605 | 95% (users.pyスタブ) |
| Dashboard Frontend | 11 .tsx/.ts | 823 | 完成・本番対応 |
| Wallet (クレジット経済) | 10 .py | 811 | 完成・本番対応 |
| Edge Firmware (Python) | 33 .py | 2,562 | 完成 |
| Edge Firmware (C++) | 4 .cpp/.h | 817 | 完成 |
| Infra/テスト | 14 .py | 3,197 | 完成 |
| **合計** | **~124** | **~13,840** | |

---

## 1. Brain Service (`services/brain/`)

**役割**: LLM駆動の意思決定エンジン。ReAct (Think→Act→Observe) 認知ループ。

### コアモジュール

| ファイル | 行数 | 役割 | 主要クラス/関数 |
|---------|------|------|---------------|
| `src/main.py` | 232 | メインオーケストレータ | `Brain` — MQTT受信、認知ループ(max 5反復)、30秒ポーリング+イベント駆動 |
| `src/llm_client.py` | 154 | LLM API通信 | `LLMClient` — OpenAI互換async wrapper、120秒タイムアウト |
| `src/tool_registry.py` | 133 | ツール定義(5種) | `get_tools()` — create_task, send_device_command, get_zone_status, speak, get_active_tasks |
| `src/tool_executor.py` | 207 | ツール実行ルーター | `ToolExecutor` — sanitizer経由のバリデーション + 各ツールハンドラ |
| `src/mcp_bridge.py` | 62 | MQTT⇔JSON-RPC変換 | `MCPBridge` — asyncio.Futureベースの要求応答相関、10秒タイムアウト |
| `src/sanitizer.py` | 106 | 入力バリデーション | `Sanitizer` — 温度18-28℃、ポンプ最大60秒、タスク作成10件/時間 |
| `src/system_prompt.py` | 59 | 憲法AI系プロンプト | `SYSTEM_PROMPT` — 安全第一/コスト意識/重複防止/段階的アプローチ/プライバシー |
| `src/dashboard_client.py` | 178 | タスク管理REST | `DashboardClient` — タスクCRUD + 二重音声生成(announce + completion) |
| `src/task_reminder.py` | 196 | リマインダー | `TaskReminder` — 1時間後再アナウンス、30分クールダウン、5分チェック間隔 |

### WorldModel モジュール (`src/world_model/`)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `world_model.py` | 441 | ゾーン統一状態管理、MQTTトピック解析、8種イベント検知(CO2超過/温度急変/長時間座位/ドア開閉等) |
| `data_classes.py` | 155 | Pydanticモデル5種: EnvironmentData, OccupancyData, DeviceState, Event, ZoneState |
| `sensor_fusion.py` | 170 | 指数減衰重み付けセンサーフュージョン (温度半減期2分、CO2 1分、在室30秒) |

### Task Scheduling モジュール (`src/task_scheduling/`)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `queue_manager.py` | 194 | 最小ヒープタスクキュー、24時間で強制ディスパッチ |
| `decision.py` | 105 | ディスパッチ判定: 緊急度/ゾーン活動/在室人数/時間帯/集中度 |
| `priority.py` | 70 | 優先度計算: urgency×1000 + 待機時間 + 締切ボーナス |

### 設計パターン
- **ReAct Loop**: Think→Act→Observe、最大5反復/サイクル
- **Hybrid Scheduling**: MQTTイベント駆動 (3秒バッチ遅延) + 30秒ポーリング
- **Dual Voice**: タスク作成時にannouncement + completion音声を事前生成
- **Duplicate Prevention**: アクティブタスク一覧をLLMコンテキストに注入

---

## 2. Voice Service (`services/voice/`)

**役割**: VOICEVOX経由の日本語音声合成 + LLMテキスト生成。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 306 | FastAPI エンドポイント7種 |
| `src/speech_generator.py` | 247 | VOICEVOX合成パイプライン (speaker_id=47, ナースロボ_タイプT) |
| `src/voicevox_client.py` | 83 | VOICEVOX REST APIクライアント |
| `src/models.py` | 34 | Pydanticリクエスト/レスポンスモデル |
| `src/rejection_stock.py` | 194 | リジェクション音声事前生成 (max 100、アイドル時LLM+VOICEVOX) |

### エンドポイント

| メソッド | パス | 用途 |
|---------|------|------|
| POST | `/api/voice/synthesize` | テキスト→音声直接合成 (speakツール/受諾) |
| POST | `/api/voice/announce` | タスクアナウンス (LLMテキスト生成 + 合成) |
| POST | `/api/voice/announce_with_completion` | 二重音声: アナウンス + 完了メッセージ |
| POST | `/api/voice/feedback/{type}` | 確認メッセージ |
| GET | `/api/voice/rejection/random` | ストックからランダムリジェクション音声 |
| GET | `/api/voice/rejection/status` | ストック状況 |
| GET | `/audio/{filename}` | 生成済みMP3配信 |

---

## 3. Perception Service (`services/perception/`)

**役割**: YOLOv11ベースのコンピュータビジョン。カメラ自動発見、在室検知、活動分析。

### コアモジュール

| モジュール | ファイル数 | 主要クラス |
|-----------|-----------|-----------|
| `monitors/` | 4 | `MonitorBase`, `OccupancyMonitor`, `WhiteboardMonitor`, `ActivityMonitor` |
| `image_sources/` | 5 | `ImageSourceFactory`, `RtspSource`, `HttpStreamSource`, `MqttImageSource`, `CameraInfo` |
| (ルート) | ~6 | `main.py`, `camera_discovery.py`, `pose_estimator.py`, `activity_analyzer.py`, `yolo_inference.py` |

### 機能

- **カメラ自動発見**: ICMP pingスイープ + YOLO検証 (192.168.128.0/24)
- **在室モニタ**: YOLO物体検知 → 人数カウント → MQTT publish
- **ホワイトボード**: 変化検知 → キャプチャ
- **活動分析**: 4段ティアードバッファ (最大4時間)、姿勢正規化、長時間座位検知
- **ポーズ推定**: YOLO11s-pose → 17キーポイント

### 設定 (`config/monitors.yaml`)
```yaml
monitors:
  - name: occupancy_meeting_room
    type: OccupancyMonitor
    camera_id: camera_node_01
    zone_name: meeting_room_a
discovery:
  network: "192.168.128.0/24"
  zone_map:
    "192.168.128.172": "kitchen"
    "192.168.128.173": "meeting_room_b"
yolo:
  model: yolo11s.pt
  pose_model: yolo11s-pose.pt
```

---

## 4. Dashboard Service (`services/dashboard/`)

### Backend (FastAPI + SQLAlchemy async)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `backend/main.py` | 33 | FastAPIアプリ初期化、CORS、ルーター登録 |
| `backend/database.py` | 14 | aiosqlite非同期エンジン |
| `backend/models.py` | 59 | SQLAlchemyモデル: Task(19列), VoiceEvent, SystemStats, User |
| `backend/schemas.py` | 104 | Pydantic 2.xスキーマ (TaskCreate/Update/Accept, UserBase, etc.) |
| `backend/routers/tasks.py` | 326 | タスクCRUD: 2段階重複検知、受諾/完了/リマインダー/キュー管理、wallet連携 |
| `backend/routers/users.py` | 11 | ユーザー一覧 (**スタブ**: ハードコードmockデータ) |
| `backend/routers/voice_events.py` | 48 | speakツール用エフェメラルイベント記録 (60秒ポーリング) |

**Task重複検知**:
1. Stage 1: タイトル + ロケーション完全一致
2. Stage 2: ゾーン + task_type重複検知 (LLMの揺れに対応)

### Frontend (React 19 + TypeScript + Vite 7 + Tailwind CSS 4)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/App.tsx` | 340 | メインダッシュボード: 3カラムグリッド、タスクポーリング(5秒)、音声イベント(3秒) |
| `src/components/TaskCard.tsx` | 153 | タスクカード: 受諾→対応中→完了のステート遷移、urgencyカラー |
| `src/components/UserSelector.tsx` | 50 | ユーザー選択ドロップダウン |
| `src/components/WalletBadge.tsx` | 39 | クレジット残高バッジ (10秒ポーリング) |
| `src/components/WalletPanel.tsx` | 60 | 取引履歴サイドパネル |
| `src/components/ui/Button.tsx` | 93 | 汎用ボタン (4バリアント、Framer Motion) |
| `src/components/ui/Card.tsx` | 81 | 汎用カード (4エレベーション) |
| `src/components/ui/Badge.tsx` | 60 | バッジ (7バリアント: success/warning/error/gold/xp等) |
| `src/audio/AudioQueue.ts` | 141 | 優先度付き音声キュー (USER_ACTION > ANNOUNCEMENT > VOICE_EVENT、max 20) |
| `src/audio/useAudioQueue.ts` | 23 | React hook (useSyncExternalStore) |

**デザインシステム**: Material Design 3 Light Theme、50+ CSS変数、Inter/JetBrains Mono

### nginx ルーティング (`nginx.conf`)

| パス | 転送先 |
|------|--------|
| `/` | SPA (index.html) |
| `/api/wallet/` | wallet:8000 |
| `/api/voice/` | voice-service:8000 |
| `/api/` | backend:8000 |
| `/audio/` | voice-service:8000 |

---

## 5. Wallet Service (`services/wallet/`)

**役割**: 複式簿記クレジット経済。タスク報酬、デバイスXP。

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/main.py` | 64 | FastAPIアプリ、起動時DB初期化 + system wallet自動作成 |
| `src/database.py` | 17 | aiosqlite非同期エンジン |
| `src/models.py` | 80 | Wallet, LedgerEntry, Device, SupplyStats |
| `src/schemas.py` | 139 | Pydanticスキーマ (TransactionCreate, WalletResponse, etc.) |
| `src/services/ledger.py` | 168 | `transfer()`: 複式仕訳、冪等性 (reference_id)、デッドロック防止 (ID順ロック) |
| `src/services/xp_scorer.py` | 96 | ゾーンデバイスXP付与、動的報酬乗数 (1.0x-3.0x) |
| `src/routers/wallets.py` | 54 | 残高照会、ウォレット作成 |
| `src/routers/transactions.py` | 80 | 取引履歴、タスク報酬API |
| `src/routers/devices.py` | 67 | デバイス登録/一覧 |
| `src/routers/admin.py` | 47 | 供給統計 |

**経済モデル**:
- system wallet (user_id=0) がクレジット発行 (負残高可)
- タスク完了 → system → user へ transfer (bounty: 500-5000)
- デバイスXP: ゾーン内タスク作成/完了で全アクティブデバイスに付与
- 報酬乗数: `1.0 + (xp/1000) * 0.5` (cap 3.0x)

---

## 6. Edge Firmware (`edge/`)

### SensorSwarm (Hub + Leaf 2階層)

| ディレクトリ | 言語 | 役割 |
|-------------|------|------|
| `edge/lib/swarm/` | MicroPython | 共有ライブラリ: message.py (バイナリプロトコル), hub.py, leaf.py, transport_*.py |
| `edge/swarm/hub-node/` | MicroPython | Hub: WiFi+MQTT→クラウド、ESP-NOW/UART/I2C→Leaf群 |
| `edge/swarm/leaf-espnow/` | MicroPython | Leaf (ESP-NOW): ESP32-C6 用 |
| `edge/swarm/leaf-uart/` | MicroPython | Leaf (UART): Raspberry Pi Pico 用 |
| `edge/swarm/leaf-arduino/` | C++ (PlatformIO) | Leaf (I2C): ATtiny85/84 用 (<2KB RAM) |

**バイナリプロトコル**: 5-245バイト、MAGIC(0x53) + VERSION + MSG_TYPE + LEAF_ID + PAYLOAD + XOR checksum

### レガシーファームウェア

| ディレクトリ | 内容 |
|-------------|------|
| `edge/office/sensor-01/` | MicroPython MCP (BME680 + MH-Z19C CO2) |
| `edge/office/sensor-02/` | BME680/MH-Z19Cドライバー |
| `edge/test-edge/camera-node/` | PlatformIO C++ カメラノード |
| `edge/test-edge/sensor-node/` | PlatformIO C++ センサーノード |

### 診断ツール (`edge/tools/`)
`blink_identify.py`, `diag_i2c.py`, `test_uart.py`, `clean_scan.py` 等13スクリプト

---

## 7. Infrastructure (`infra/`)

### Docker Compose

| ファイル | サービス数 | 用途 |
|---------|-----------|------|
| `docker-compose.yml` | 10 | 本番構成: mosquitto, brain, backend, frontend, voicevox, voice-service, ollama, mock-llm, perception, wallet |
| `docker-compose.edge-mock.yml` | 3 | 仮想構成: virtual-edge + mock-llm + virtual-camera |

### サービスポート

| サービス | ポート | コンテナ名 |
|---------|--------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 8003 | soms-wallet |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 | soms-mqtt |

### Mock/仮想サービス

| ディレクトリ | 行数 | 役割 |
|-------------|------|------|
| `infra/mock_llm/` | ~200 | キーワードベースLLMシミュレータ (FastAPI、OpenAI互換)。tools有無で分岐 |
| `infra/virtual_edge/` | ~500 | SwarmHub + 3 Leaf仮想エミュレータ、MQTTテレメトリ生成 |
| `infra/virtual_camera/` | ~50 | mediamtx + ffmpeg RTSPサーバー |

### テストスクリプト (`infra/scripts/`)

| スクリプト | 内容 |
|-----------|------|
| `e2e_full_test.py` | 7シナリオE2Eテスト: ヘルスチェック、CO2→タスク、温度→音声、オーディオURL、リジェクションストック、タスクライフサイクル、重複防止 |
| `e2e_dedup_test.py` | 重複タスク防止テスト |
| `test_dedup_and_alerts.py` | ユニットテスト: DashboardClientの重複/アラート検出 |
| `integration_test_mock.py` | 簡易モック統合テスト |
| `test_task_scheduling.py` | タスクスケジューリングテスト |
| `test_world_model.py` | WorldModelテスト |
| `test_human_task.py` | ヒューマンタスクテスト |

---

## 8. MQTTトピック体系

```
# センサーテレメトリ (per-channel, {"value": X})
office/{zone}/sensor/{device_id}/{channel}
  例: office/main/sensor/env_01/temperature

# SensorSwarm (Hub経由)
office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}
  例: office/main/sensor/swarm_hub_01.leaf_env_01/temperature

# カメラ
office/{zone}/camera/{camera_id}/status
office/{zone}/activity/{monitor_id}

# MCP制御 (JSON-RPC 2.0)
mcp/{agent_id}/request/call_tool
mcp/{agent_id}/response/{request_id}

# ハートビート
{topic_prefix}/heartbeat  (60秒間隔)
```

---

## 9. Git/未コミット状態

### 直近コミット履歴

```
5a8bdfc add: full E2E integration test — 7 scenarios
98c905c add: wallet service — double-entry ledger
aabc371 refactor: extract AudioQueue with priority-based playback
c9de557 feat: WorldModel motion/door channel support
ff1a5d2 fix: virtual-edge Docker path resolution
b48a458 feat: add SensorSwarm 2-tier sensor network
15da7d4 add: promotional materials
e6291e9 fix: duplicate task prevention and temperature alert
```

### 未コミット変更 (18ファイル)

| ファイル | ステータス | 内容 |
|---------|-----------|------|
| `HANDOFF.md` | M | 作業引継ぎドキュメント更新 |
| `infra/docker-compose.yml` | M | wallet サービス + PostgreSQL追加 |
| `services/dashboard/backend/models.py` | M (staged) | Userモデル更新 |
| `services/dashboard/backend/requirements.txt` | M | wallet連携用依存追加 |
| `services/dashboard/backend/routers/tasks.py` | MM | wallet連携 (staged + unstaged) |
| `services/dashboard/backend/schemas.py` | M (staged) | Userスキーマ更新 |
| `services/dashboard/frontend/nginx.conf` | M | wallet proxy追加 |
| **`services/dashboard/frontend/src/App.tsx`** | **UU** | **マージコンフリクト (要手動解決)** |
| `services/dashboard/frontend/src/components/TaskCard.tsx` | MM | wallet連携 |
| `services/wallet/src/models.py` | M | wallet DB修正 |
| `services/wallet/src/routers/devices.py` | M | デバイスAPI修正 |
| `services/wallet/src/schemas.py` | M | walletスキーマ修正 |
| `services/dashboard/frontend/src/components/UserSelector.tsx` | 新規 | ユーザー選択UI |
| `services/dashboard/frontend/src/components/WalletBadge.tsx` | 新規 | クレジットバッジ |
| `services/dashboard/frontend/src/components/WalletPanel.tsx` | 新規 | 取引履歴パネル |
| `services/dashboard/frontend/tsconfig.app.tsbuildinfo` | 新規 | ビルド成果物 |
| `services/wallet/src/services/xp_scorer.py` | 新規 | XPスコアリング |

**要対応**: `App.tsx` のマージコンフリクト解決

---

## 10. 既知の問題・改善候補

| 優先度 | 項目 | 詳細 |
|--------|------|------|
| **高** | App.tsx マージコンフリクト | wallet stash pop由来。コミット前に解決必須 |
| 中 | users.py スタブ | ハードコードmockデータ→DB連携に要置換 |
| 中 | 受諾音声レイテンシ | ストック化されていない (1-2秒遅延) |
| 低 | axios未使用 | package.jsonに含まれるが使用なし (fetch直接利用) |
| 低 | 認証なし | nginx/API層に認証レイヤーなし (PoC段階) |

---

## 11. アーキテクチャ図

```
                    ┌──────────────────┐
                    │   Ollama / LLM   │
                    │  (qwen2.5:14b)   │
                    └────────┬─────────┘
                             │ OpenAI API
                    ┌────────┴─────────┐
                    │   Brain Service   │
                    │  ReAct Loop (5x)  │
                    │  WorldModel       │
                    │  TaskScheduling   │
                    └──┬───┬───┬───┬───┘
                       │   │   │   │
            ┌──────────┘   │   │   └──────────┐
            ▼              ▼   ▼              ▼
    ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
    │ MQTT Broker  │ │  Dashboard  │ │Voice Service │
    │ (Mosquitto)  │ │  Backend    │ │  + VOICEVOX  │
    └──┬───┬───────┘ │  (FastAPI)  │ └──────────────┘
       │   │         └──────┬──────┘
       │   │                │
       │   │         ┌──────┴──────┐
       │   │         │  Dashboard  │
       │   │         │  Frontend   │◄── nginx ──► Wallet
       │   │         │  (React 19) │              Service
       │   │         └─────────────┘
       │   │
       │   └─────────────────┐
       ▼                     ▼
┌──────────────┐    ┌──────────────┐
│  Edge Devices │    │  Perception  │
│  SwarmHub +   │    │  YOLOv11     │
│  Leaf nodes   │    │  Monitors    │
│  MCP/JSON-RPC │    │  (ROCm GPU)  │
└──────────────┘    └──────────────┘
```

---

## 12. 技術スタック

| レイヤー | 技術 |
|---------|------|
| **LLM** | Ollama + qwen2.5:14b (Q4_K_M), ROCm (AMD RX 9700 RDNA4) |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async), aiosqlite, paho-mqtt >=2.0, Pydantic 2.x, loguru |
| **Frontend** | React 19, TypeScript 5.9, Vite 7.3, Tailwind CSS 4, Framer Motion 12, Lucide Icons |
| **Vision** | Ultralytics YOLOv11 (yolo11s.pt + yolo11s-pose.pt), OpenCV, PyTorch (ROCm) |
| **TTS** | VOICEVOX (speaker_id=47, ナースロボ_タイプT) |
| **Edge** | MicroPython (ESP32/Pico), PlatformIO C++ (ATtiny/ESP32-CAM) |
| **Infra** | Docker Compose, Mosquitto MQTT, nginx, SQLite |
| **通信** | MQTT (テレメトリ), MCP/JSON-RPC 2.0 (デバイス制御), REST (サービス間) |
