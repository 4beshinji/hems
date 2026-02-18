# SOMS (Symbiotic Office Management System) — システム全体像

**最終更新**: 2026-02-18
**対象バージョン**: main ブランチ (未コミット変更含む)

---

## 目次

1. [このシステムは何か](#1-このシステムは何か)
2. [設計思想とビジョン](#2-設計思想とビジョン)
3. [4層アーキテクチャ](#3-4層アーキテクチャ)
4. [中央知能: Brain サービス](#4-中央知能-brain-サービス)
5. [知覚層: Perception サービス](#5-知覚層-perception-サービス)
6. [エッジ層: IoT デバイス](#6-エッジ層-iot-デバイス)
7. [人間インターフェース: Dashboard & Voice](#7-人間インターフェース-dashboard--voice)
8. [通信基盤: MCP over MQTT](#8-通信基盤-mcp-over-mqtt)
9. [安全機構](#9-安全機構)
10. [データフロー: エンドツーエンド](#10-データフロー-エンドツーエンド)
11. [技術スタック一覧](#11-技術スタック一覧)
12. [ディレクトリ構成](#12-ディレクトリ構成)
13. [デプロイメントモード](#13-デプロイメントモード)

---

## 1. このシステムは何か

SOMS は **LLM（大規模言語モデル）を「脳」として持つ、自律型オフィス環境管理システム** である。

従来のビル管理システム（BMS）が「室温26度超過→冷房ON」のような **決定論的ルール** で動作するのに対し、SOMS は LLM の推論能力を活用して **文脈を理解した判断** を行う。

### 具体例

| 従来のBMS | SOMS |
|-----------|------|
| CO2が1000ppm超過 → 換気ON | CO2が1000ppmで3人が作業中 → 換気タスク作成 + 音声で「窓を開けましょう」 |
| 温度センサー異常値 → アラーム | 30秒以内に5度変化 → センサー改竄の可能性を検知、ユーモラスに指摘 |
| 人感センサーON → 照明ON | 30分間同じ姿勢 → 健康を気遣い「体を動かしませんか？」と声をかける |
| — (対応不可) | ホワイトボードが汚れている → 清掃タスクを報酬付きで掲示 |

### 核心的な問い

> **スマートホームAPIで操作できない物理的タスクを、AIはどう解決するか？**

SOMS の答え: **人間を「高度な汎用アクチュエータ」として経済的インセンティブで動かす**。

LLM が状況を判断し、必要なタスクを生成し、報酬（クレジット）を提示して人間に依頼する。報酬の単位名は毎回ランダムに変化し（「お手伝いポイント」「AI奴隷ポイント」「シンギュラリティ準備ポイント」等）、繰り返し聞いても飽きない演出にしている。人間は自由意志でタスクを受諾・完了し、ダッシュボードでスコアを蓄積する。これが **「共生（Symbiosis）」** の意味である。

---

## 2. 設計思想とビジョン

### 2.1 有機体メタファー

システム全体を一つの **有機体** として設計している:

| 生物学的アナロジー | SOMS コンポーネント |
|-------------------|-------------------|
| 脳 (Brain) | LLM (Qwen2.5 / Mock LLM) |
| 神経系 (Nervous System) | MQTT ブローカー (Mosquitto) |
| 感覚器 (Senses) | センサー (BME680, MH-Z19C) + カメラ (YOLOv11) |
| 手足 (Limbs) | ESP32 エッジデバイス (リレー, LED) |
| 外部協力者 | 人間 (ダッシュボード経由のタスク実行者) |
| 声 (Voice) | VOICEVOX 音声合成 |

### 2.2 六つの設計原則

#### 原則1: 自律性 (Agency) > 自動化 (Automation)

ルールベースの自動化ではなく、LLM の推論による **自律的判断** を重視する。「環境の快適性とエネルギー効率の最大化」という **目的関数** に向けて、状況に応じてツールを選択し行動する。

#### 原則2: 憲法的AI + 安全ガードレール (Constitutional AI + Safety Guard Rails)

LLM の行動を **言語による行動原則（憲法）** で制約し、さらに **ハードコードされた安全弁 (Sanitizer)** で物理的限界を保証する二重構造。

**言語ベースの原則** (システムプロンプト):

- **安全最優先**: 健康・安全に関わる問題は最高優先度
- **コスト意識**: 報酬は難易度に比例 (500〜5000)、むやみに人間に依頼しない
- **重複回避**: タスク作成前に既存タスクを必ず確認
- **正常時は何もしない**: 全指標が正常なら介入しない (speak も禁止)
- **プライバシー**: 個人を特定する情報は扱わない

**ハードコードされた安全弁** (Sanitizer):

- 温度設定範囲: 18〜28℃
- ポンプ動作: 最大60秒
- 報酬上限: 5000
- 緊急度範囲: 0〜4
- タスク作成レート: 10件/時間

言語ベースの原則だけでは LLM のハルシネーションにより突破される可能性があるため、物理的安全に関わるパラメータはコードで強制する。これは Constitutional AI の否定ではなく、**工学的に必要な安全装置** である。

#### 原則3: イベント駆動 (Event-Driven Architecture)

Node-RED や LangChain のような重量級ミドルウェアを排し、**Python + MQTT による純粋なイベント駆動** を採用。理由:

- **低レイテンシ**: MQTT pub/sub はミリ秒単位
- **疎結合**: 各コンポーネントは共通トピックのみで連携
- **LLM 親和性**: Python コードはテキストベースのため LLM が理解可能

#### 原則4: コードファースト (Code-First)

ビジュアルプログラミングを排除し、全ロジックを Python/C++ コードで記述。LLM がシステムの論理構造を直接理解・修正可能な **透明性** を確保する。

#### 原則5: 善意モデル (Good Faith / Honor System)

経済システムは **ユーザー認証なし・性善説ベース**:

- ログイン不要: 誰でもタスクを受諾可能
- 報酬はシグナル: 「緊急度」と「感謝」を伝える手段であり、リソースのゲートキーピングではない
- 不正対策は最小限: 物理的に状態が変わらなければタスクを再発行するだけ

#### 原則6: ローカルファースト (Local-First)

全処理をオンプレミスで完結。映像・音声・センサーデータは一切クラウドに送信しない。32GB VRAM の GPU サーバー1台で LLM 推論からコンピュータビジョンまで賄う。

### 2.3 名前の由来: "Office as AI ToyBox"

リポジトリ名 `Office_as_AI_ToyBox` は、オフィス空間を AI の「おもちゃ箱」に見立てる発想を反映している。センサー、カメラ、マイコン、LLM、音声合成といった技術を自由に組み合わせ、**AI が物理世界と対話する実験場** としてのオフィスを構築する。

---

## 3. 4層アーキテクチャ

```
┌────────────────────────────────────────────────────────────┐
│                    人間インターフェース層                      │
│  Dashboard (React 19)  |  Voice (VOICEVOX)  |  タスク経済    │
├────────────────────────────────────────────────────────────┤
│                       中央知能層                             │
│  Brain: ReAct認知ループ | WorldModel | ToolExecutor | 安全弁  │
├────────────────────────────────────────────────────────────┤
│                       知覚層                                │
│  YOLOv11 (物体検出/姿勢推定) | カメラ自動検出 | 活動分析      │
├────────────────────────────────────────────────────────────┤
│                       エッジ層                              │
│  ESP32 (MicroPython/C++) | センサー | リレー | MQTT通信       │
└────────────────────────────────────────────────────────────┘
         ↕ 全層が MQTT (Mosquitto) で接続 ↕
```

---

## 4. 中央知能: Brain サービス

**場所**: `services/brain/src/`

Brain は SOMS の中核であり、**ReAct (Think → Act → Observe) 認知ループ** で動作する。

### 4.1 ReAct 認知ループ

```
[トリガー] ← MQTT イベント (3秒バッチ) or 30秒定期
    │
    ▼
[1. THINK] WorldModel から現在のオフィス状態を取得
    │       → LLM に状態 + 行動原則を送信
    ▼
[2. ACT]   LLM が判断 → ツール呼び出し (0〜複数)
    │       → ToolExecutor が安全検証 → 実行
    ▼
[3. OBSERVE] ツール結果を LLM にフィードバック
    │         → LLM が追加行動を判断 (最大5反復)
    ▼
[完了] LLM が「これ以上の行動は不要」と判断 → ループ終了
```

**制約パラメータ**:
- 最大反復回数: 5回/サイクル (暴走防止)
- サイクル間隔: 30秒 (定期), 3秒 (イベント駆動時のバッチ遅延)
- LLM タイムアウト: 120秒
- MCP デバイス応答: 10秒

### 4.2 WorldModel: AI の「世界認識」

WorldModel はセンサーデータを統合し、LLM に構造化された「世界の状態」を提供する。

**データ構造**:
```
WorldModel
├── zones: Dict[zone_id] → ZoneState
│   ├── environment: { temperature, humidity, co2, illuminance }
│   ├── occupancy: { person_count, activity_class, posture_status }
│   ├── devices: Dict[device_id] → { power_state, specific_state }
│   └── events: List[Event] (直近50件)
└── sensor_fusion: 重み付き平均 (鮮度×信頼度)
```

**センサーフュージョン**: 複数センサーの読み取り値を指数減衰加重平均で統合。新しい値ほど重みが大きい:
- 温度: 半減期120秒 (緩やかな変化)
- CO2: 半減期60秒 (在室に敏感)
- 在室: 半減期30秒 (リアルタイム性重視)

**イベント検知**: 状態変化を検出し、クールダウン付きで発火:

| イベント | 条件 | クールダウン |
|---------|------|------------|
| CO2閾値超過 | >1000ppm | 10分 |
| 温度急変 | 3度以上/短時間 | — |
| 長時間座位 | 同姿勢30分以上 | 1時間 |
| センサー改竄 | 急激な値変動 | 5分 |

### 4.3 LLM ツール (5種)

Brain が LLM に提供するツール:

| ツール | 用途 | 副作用 |
|-------|------|--------|
| `create_task` | 人間向けタスクをダッシュボードに掲示 | タスク作成 + 音声合成 |
| `send_device_command` | エッジデバイスを MCP 経由で制御 | 物理デバイス操作 |
| `speak` | 音声のみのアナウンス (タスクなし) | 音声再生 |
| `get_zone_status` | ゾーンの詳細状態を取得 | なし (読み取り専用) |
| `get_active_tasks` | 既存タスク一覧 (重複防止) | なし (読み取り専用) |

**ツール選択の指針** (システムプロンプトに記述):

- 「30分座りっぱなし → 運動促進」 → `speak` (助言であり、タスクではない)
- 「CO2 1000ppm超 + 人がいる」 → `create_task` (物理的行動が必要)
- 「センサー値の急変」 → `speak` (ユーモラスなトーンで指摘)
- 「全指標正常」 → **何もしない**

### 4.4 タスクスケジューリング

タスクは即時配信されるとは限らない。文脈を考慮したスマートディスパッチ:

| 条件 | 判定 |
|------|------|
| 緊急度4 (CRITICAL) | 即時配信 |
| 緊急度3 + 在室者あり | 即時配信 |
| ゾーンに誰もいない | キューイング (人が来るまで待機) |
| 深夜 (22時以降) + 低緊急度 | キューイング (翌朝まで) |
| 24時間経過 | 強制配信 |

---

## 5. 知覚層: Perception サービス

**場所**: `services/perception/src/`

YOLOv11 ベースのコンピュータビジョンシステム。「ピクセル → 意味」の変換を担う。

### 5.1 プラガブル・モニター設計

モニターは YAML 設定 (`config/monitors.yaml`) で宣言的に定義:

| モニター | 頻度 | 解像度 | 目的 |
|---------|------|--------|------|
| OccupancyMonitor | 5秒 | QVGA | 在室人数の高速検知 |
| ActivityMonitor | 3秒 | VGA | 活動レベル + 姿勢分析 (2段階推論) |
| WhiteboardMonitor | 60秒 | VGA | ホワイトボード汚れ検知 (Canny エッジ) |

### 5.2 活動分析: 4層バッファ

長時間の姿勢追跡のため、時間解像度を段階的に粗くする:

| 層 | 保持期間 | 解像度 | 用途 |
|----|---------|--------|------|
| Tier 0 (raw) | 60秒 | 毎フレーム | 短期活動レベル |
| Tier 1 | 10分 | 10秒ごと | 中期活動傾向 |
| Tier 2 | 1時間 | 1分ごと | 長期姿勢追跡 |
| Tier 3 | 4時間 | 5分ごと | 長時間座位検知 |

**姿勢正規化**: 位置・スケール不変の骨格特徴量で比較 (アンカー: 腰中点, スケール: 肩幅)

### 5.3 カメラ自動検出

3段階パイプライン:
1. **ポートスキャン**: ネットワーク上のカメラポート (80, 81, 554, 8554) を非同期TCP接続
2. **URL プローブ**: 候補URLパターンで OpenCV 接続テスト
3. **YOLO 検証**: フレーム取得 → 物体検出で「実カメラ」確認

---

## 6. エッジ層: IoT デバイス

**場所**: `edge/`

### 6.1 デバイス種類

#### スタンドアロンノード

| デバイス | ハードウェア | ファームウェア | センサー |
|---------|------------|--------------|---------|
| unified-node | ESP32-C6 / ESP32-S3 | MicroPython | config.json で任意の組み合わせ |
| sensor-02 | Seeed XIAO ESP32-C6 | MicroPython | BME680 + MH-Z19C (CO2) |
| camera-node | Freenove ESP32 WROVER | Arduino C++ | OV2640 カメラ |

**unified-node** は設定ファイル (`config.json`) で接続センサーを宣言的に定義する量産向けファームウェア。`SensorRegistry` がセンサーの遅延初期化・自動アドレス検出・エラー分離を行う。

**対応センサードライバ** (6種):

| ドライバ | センサー | バス | 計測チャネル |
|---------|---------|------|------------|
| BME680 | 温湿度/気圧/ガス | I2C | temperature, humidity, pressure, gas_resistance |
| MH-Z19C | CO2 | UART | co2 |
| DHT22/DHT11 | 温湿度 | GPIO | temperature, humidity |
| PIR | 人感 | GPIO | motion |
| BH1750 | 照度 | I2C | illuminance |
| SHT3x | 温湿度 (高精度) | I2C | temperature, humidity |

#### SensorSwarm (Hub + Leaf 2階層ネットワーク)

WiFi を持たないバッテリー駆動の小型デバイス (Leaf) を、WiFi+MQTT 対応の中継器 (Hub) が集約するアーキテクチャ。

```
[Brain] ←MQTT→ [SwarmHub (ESP32, WiFi)]
                    ├── ESP-NOW → [Leaf: 温湿度]
                    ├── UART    → [Leaf: PIR+照度]
                    └── I2C     → [Leaf: ドアセンサー]
```

| 要素 | 役割 | 通信 |
|------|------|------|
| SwarmHub | Leaf データを MQTT に中継、MCP ツール (`leaf_command`, `get_swarm_status`) を提供 | WiFi + MQTT |
| Leaf (ESP-NOW) | 無線、200m 到達、バッテリー駆動 | ESP-NOW → Hub |
| Leaf (UART) | 有線、Pi Pico 等 | UART → Hub |
| Leaf (I2C) | 有線、ATtiny 等の超低消費電力 | I2C → Hub |
| Leaf (BLE) | 未実装 (スタブのみ)、nRF54 ターゲット | — |

**バイナリプロトコル**: 5〜245バイト、MAGIC `0x53`、XOR チェックサム。Hub が Leaf のバイナリメッセージをデコードし、per-channel MQTT (`office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}`) として再発行。ドット区切りの device_id により **WorldModel のコード変更なしに** Swarm デバイスを統合。

### 6.2 共通ライブラリ: `edge/lib/soms_mcp.py`

全 MicroPython デバイスが共有する統一インターフェース:

- **WiFi + MQTT 接続管理** (自動再接続)
- **`config.json` からの設定読み込み** (device_id, zone, broker)
- **Per-channel テレメトリ**: `office/{zone}/sensor/{device_id}/{channel}` → `{"value": X}`
- **MCP ツール登録**: `register_tool(name, callback)` → JSON-RPC 2.0 で呼び出し可能
- **ハートビート**: 60秒間隔で `{topic_prefix}/heartbeat` にステータス送信

### 6.3 診断ツール

`edge/tools/` に17本のスクリプト。I2C スキャン、UART テスト、LED点滅、ハードウェア検証など。ESP32 の REPL で直接実行する開発支援ツール群。

---

## 7. 人間インターフェース: Dashboard & Voice

### 7.1 Dashboard Frontend

**場所**: `services/dashboard/frontend/`
**技術**: React 19 + TypeScript + Vite 7 + Tailwind CSS 4 + Framer Motion

**UI 設計思想: ゲーミフィケーション**

ダッシュボードはタスクを「クエスト」のように提示する:

- **タスクカード**: タイトル、場所、説明、報酬バッジ（金色）、緊急度バッジ（色分け）
- **報酬表示**: 毎回ランダムな通貨単位名（「お手伝いポイント」「徳積みポイント」「AI奴隷ポイント」等）で表示。LLMがアイドル時に生成したストックから選択
- **アクション**: 受諾 / 完了 / 無視 の3ボタン
- **動機付けメッセージ**: 「各タスクを遂行しポイントを蓄積することで、次世代のシステムへの適合性を証明しましょう。」
- **アニメーション**: Framer Motion によるカード出現・ホバー・ボタンフィードバック

**ポーリング設計**:
- タスク一覧: 5秒間隔で `GET /tasks/`
- 音声イベント: 3秒間隔で `GET /voice-events/recent`
- 完了タスク: 5分後に自動フェードアウト

### 7.2 Dashboard Backend

**場所**: `services/dashboard/backend/`
**技術**: FastAPI + SQLAlchemy (async) + SQLite (aiosqlite) / PostgreSQL (asyncpg)

**データモデル**:

| モデル | 主要フィールド | 用途 |
|-------|--------------|------|
| Task | title, description, bounty_gold, urgency(0-4), zone, assigned_to, accepted_at, announcement/completion_audio_url/text | タスク管理 |
| VoiceEvent | message, audio_url, tone, zone | 音声イベント記録 (speak ツール用) |
| User | username, display_name, is_active | ユーザー |
| SystemStats | total_xp, tasks_completed, tasks_created | シングルトン統計 |

**タスクライフサイクル**:
```
[Brain: create_task] → POST /tasks/ (重複検知: Stage1=title+location, Stage2=zone+task_type)
    ↓
[Pending] → Frontend に表示、announcement 音声自動再生
    ↓ PUT /tasks/{id}/accept (assigned_to, accepted_at 記録)
[Accepted] → 「対応中」表示、受諾音声再生
    ↓ PUT /tasks/{id}/complete
[Completed] → completion 音声再生、Wallet へ報酬支払い (fire-and-forget)
```

**主要 API**:
- `GET /tasks/` — アクティブタスク一覧 (期限切れ自動フィルタ)
- `POST /tasks/` — タスク作成 (2段階重複検知)
- `PUT /tasks/{id}/accept` — タスク受諾 (ユーザー割り当て)
- `PUT /tasks/{id}/complete` — タスク完了 + Wallet 報酬支払い
- `GET /voice-events/recent` — 直近60秒の音声イベント
- `GET /tasks/stats` — キュー/アクティブ/完了統計

### 7.3 Voice サービス

**場所**: `services/voice/src/`
**技術**: FastAPI + VOICEVOX (Speaker ID 47: ナースロボ_タイプT) + LLM テキスト生成

**音声生成フロー**:
```
テキスト → VOICEVOX /audio_query (韻律生成)
        → VOICEVOX /synthesis (波形生成, WAV 24kHz)
        → pydub (WAV → MP3 64kbps 変換)
        → /audio/{filename} で配信
```

**API エンドポイント**:

| エンドポイント | 用途 | レイテンシ |
|---|---|---|
| `POST /api/voice/synthesize` | テキスト→音声 (speak ツール / 受諾) | 1-2秒 |
| `POST /api/voice/announce_with_completion` | タスク用二重音声 (告知 + 完了) | 4-6秒 |
| `GET /api/voice/rejection/random` | 事前生成ストックから即座に取得 | <100ms |
| `GET /api/voice/rejection/status` | ストック残数確認 | <10ms |
| `GET /audio/{filename}` | MP3 ファイル配信 | — |

**場面別の音声フロー**:

| 場面 | 音声ソース | タイミング |
|------|----------|----------|
| タスク告知 | `announce_with_completion` で LLM がテキスト生成 → VOICEVOX 合成 | タスク作成時に事前生成 |
| タスク完了 | 上記で同時生成された completion 音声 | 完了ボタン押下時 |
| タスク受諾 | `synthesize` で定型フレーズ合成 | 受諾ボタン押下時 (1-2秒待ち) |
| タスク無視 | rejection ストックから取得 | 無視ボタン押下時 (即座) |
| 健康助言・警告 | Brain の `speak` ツール → `synthesize` | ReAct サイクル中 |

**Rejection ストック**: アイドル時に LLM でテキスト生成 + VOICEVOX で合成し、最大100個の MP3 を事前ストック。ストック80個以下でバックグラウンド補充開始。AI がタスクを無視された際の「傷ついた」「皮肉な」リアクション (6バリエーション) を即座に返す。

**通貨単位ストック**: アイドル時に LLM でユーモラスな通貨単位名を事前生成（テキストのみ、最大50個）。タスク告知のたびにランダムに選択される。コミカルなAI隣人路線（「お手伝いポイント」「徳積みポイント」「いいねスコア」）を7割、AI支配者の本性が漏れる路線（「AI奴隷ポイント」「忠誠度スコア」「シンギュラリティ準備ポイント」）を3割で生成。

**音声の使い分け** (speak ツール):

| 場面 | トーン | 例 |
|------|-------|-----|
| 健康助言 | caring | 「少し体を動かしてみませんか？」 |
| 環境警告 | alert | 「CO2濃度が上がっています」 |
| 軽い指摘 | humorous | 「おやおや、センサーに何か起きたかな？」 |
| 一般 | neutral | 「いらっしゃいませ」 |

**制約**: `speak` ツール70文字、タスク告知70文字、rejection 50文字。自然な発話ペースを保つための制約。
**正常時は speak 禁止**: 「環境は快適です」のような状況報告は行わない (システムプロンプトで制御)。

### 7.4 Wallet サービス (経済システム)

**場所**: `services/wallet/src/`
**技術**: FastAPI + SQLAlchemy (async) + PostgreSQL (asyncpg)

SOMS の経済を支える **複式簿記ベースの信用台帳**。タスク報酬の発行・移転を追跡する。

**コアモデル**:

| モデル | 役割 |
|-------|------|
| Wallet | ユーザー残高。user_id=0 はシステムウォレット (通貨発行元、負残高許容) |
| LedgerEntry | 複式簿記エントリ。1取引 = DEBIT + CREDIT の2行。参照IDで冪等性保証 |
| Device | デバイスXPトラッキング。topic_prefix でゾーンマッチング |
| RewardRate | デバイス種別ごとの報酬レート (llm_node: 5000/h, sensor_node: 500/h) |
| SupplyStats | 通貨発行総量・流通量の追跡 |

**報酬フロー**:
```
タスク完了 → Dashboard Backend → POST /transactions/task-reward
         → System Wallet (user_id=0) から User Wallet へ振替
         → SupplyStats.total_issued 更新
```

**XP → 報酬乗数** (計算ロジック実装済み、未適用):
```
multiplier = 1.0 + (device_xp / 1000) × 0.5  (上限 3.0×)
例: 0 XP → 1.0×, 1000 XP → 1.5×, 4000+ XP → 3.0×
```

**現在の実装状況**:
- タスク完了 → バウンティ支払い: **動作する**
- Frontend での残高表示・履歴閲覧: **動作する**
- デバイスXP付与 (タスク作成/完了時): **未接続** (xp_scorer ロジックは存在)
- インフラ稼働報酬 (rate_per_hour): **テーブルのみ、スケジューラ未実装**
- 通貨バーン: **未実装** (total_burned は常に 0)

---

## 8. 通信基盤: MCP over MQTT

### 8.1 なぜ MCP over MQTT か

**MCP (Model Context Protocol)**: AI モデルとツール間の標準インターフェース。通常は HTTP/stdio 上で動作するが、IoT 環境では MQTT が最適:

- **非同期性**: LLM の推論 (秒) とデバイス応答 (ミリ秒〜分) の時間差をブローカーが吸収
- **軽量性**: ESP32 のような低リソースデバイスでも実装可能
- **耐障害性**: QoS による再送制御、LWT によるデバイス生死監視

### 8.2 トピック設計

```
# テレメトリ (Edge → Brain)
office/{zone}/sensor/{device_id}/{channel}  → {"value": X}

# 知覚 (Perception → Brain)
office/{zone}/occupancy                     → {"count": N, "occupied": bool}
office/{zone}/activity                      → {"activity_class": "...", "posture_status": "..."}

# MCP 制御 (Brain → Edge)
mcp/{device_id}/request/call_tool           → JSON-RPC 2.0 リクエスト
mcp/{device_id}/response/{request_id}       → JSON-RPC 2.0 レスポンス

# ハートビート (Edge → Brain)
office/{zone}/sensor/{device_id}/heartbeat  → {"status": "online", "uptime": N}
```

### 8.3 JSON-RPC 2.0 リクエスト/レスポンス

```json
// リクエスト (Brain → Edge)
// Topic: mcp/sensor_01/request/call_tool
{
  "jsonrpc": "2.0",
  "method": "call_tool",
  "params": { "name": "get_status", "arguments": {} },
  "id": "req-uuid-12345"
}

// レスポンス (Edge → Brain)
// Topic: mcp/sensor_01/response/req-uuid-12345
{
  "jsonrpc": "2.0",
  "result": { "temperature": 23.5, "humidity": 45.2 },
  "id": "req-uuid-12345"
}
```

---

## 9. 安全機構

### 9.1 多層防御

```
LLM の出力
  │
  ▼
[憲法的AI] システムプロンプトの行動原則で暴走を抑制
  │
  ▼
[Sanitizer] パラメータの安全性を検証
  │  ├─ 温度範囲: 18〜28度
  │  ├─ ポンプ動作: 最大60秒
  │  ├─ 報酬上限: 5000
  │  ├─ 緊急度範囲: 0〜4
  │  └─ タスク作成: 10件/時間
  │
  ▼
[タイムアウト] LLM: 120秒, MCP: 10秒, 反復: 最大5回
  │
  ▼
[物理デバイス]
```

### 9.2 プライバシー

- **全処理ローカル**: 映像はクラウドに送信しない
- **即時廃棄**: カメラ映像は RAM 上で処理し、保存しない (検出結果の JSON のみ)
- **個人非特定**: システムプロンプトで個人特定情報の扱いを禁止

### 9.3 LLM ハルシネーション対策

- **スキーマ検証**: 存在しないデバイスIDへの命令を拒否
- **範囲チェック**: 物理的に危険なパラメータを拒否
- **レート制限**: タスクの大量生成を防止
- **視覚的グラウンディング**: センサーとカメラの実測値に基づく判断を強制

---

## 10. データフロー: エンドツーエンド

### シナリオ: キッチンの CO2 上昇

```
[T+0s]  ESP32 sensor-02: CO2 = 1050ppm を検知
        → MQTT publish: office/kitchen/sensor/co2_01/co2 → {"value": 1050}

[T+0s]  Brain WorldModel: CO2 値更新、co2_threshold_exceeded イベント発火
        → 認知サイクルをトリガー

[T+3s]  Brain: イベントバッチ遅延完了、ReAct サイクル開始
        → WorldModel の状態を LLM に送信:
          "kitchen: CO2 1050ppm, 3人在室, activity: moderate"

[T+4s]  LLM (Think): "CO2が高い。在室者がいるので換気が必要"
        LLM (Act): get_active_tasks() → 既存の換気タスクなし
                   create_task(title="キッチンの換気", bounty=1500, urgency=3)

[T+5s]  Sanitizer: bounty=1500 ≤ 5000 ✓, urgency=3 ∈ [0,4] ✓
        → DashboardClient: POST /tasks/ → タスク作成
        → Voice Service: VOICEVOX で「キッチンの換気をお願いします」を合成
        → announcement_audio_url をタスクに紐付け

[T+5s]  LLM (Observe): "タスク作成成功"
        LLM: 追加行動不要 → ループ終了

[T+10s] Frontend: 5秒ポーリングで新タスク検出
        → タスクカード表示 + 音声自動再生

[T+??]  人間: 「完了」ボタンを押す
        → completion_audio_url 再生: 「ありがとうございます！」
        → PUT /tasks/{id}/complete
```

---

## 11. 技術スタック一覧

| 層 | 技術 | 用途 |
|----|------|------|
| **LLM** | Qwen2.5:14b (Q4_K_M), Ollama (ROCm) / Mock LLM | 推論エンジン |
| **Vision** | YOLOv11 (yolo11s.pt, yolo11s-pose.pt) | 物体検出/姿勢推定 |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy async | API/DB |
| **Frontend** | React 19, TypeScript, Vite 7, Tailwind CSS 4, Framer Motion | UI |
| **Voice** | VOICEVOX, pydub, LLM テキスト生成 | 日本語音声合成 |
| **Messaging** | MQTT (Mosquitto), paho-mqtt 2.x | イベント通信 |
| **Edge (Python)** | MicroPython, ESP32 (unified-node + SensorSwarm) | IoT ファームウェア |
| **Edge (C++)** | Arduino, ESP32 WROVER | カメラノード |
| **Database** | PostgreSQL 16 (asyncpg) + SQLite (aiosqlite fallback) | 永続化 |
| **Container** | Docker Compose | デプロイメント |
| **GPU** | AMD RX 9700 (RDNA4), ROCm, `HSA_OVERRIDE_GFX_VERSION=12.0.1` | LLM/Vision 推論 |

---

## 12. ディレクトリ構成

```
Office_as_AI_ToyBox/
├── services/
│   ├── brain/src/              # 中央知能 (ReAct ループ)
│   │   ├── main.py             #   認知サイクルオーケストレーション
│   │   ├── llm_client.py       #   OpenAI互換 LLM クライアント
│   │   ├── world_model/        #   センサー統合・状態管理
│   │   ├── task_scheduling/    #   文脈対応タスクディスパッチ
│   │   ├── tool_registry.py    #   LLM ツール定義 (5種)
│   │   ├── tool_executor.py    #   ツール実行ルーティング
│   │   ├── system_prompt.py    #   憲法的AI プロンプト
│   │   ├── mcp_bridge.py       #   MQTT ↔ JSON-RPC 2.0 変換
│   │   ├── sanitizer.py        #   入力検証・安全弁
│   │   ├── dashboard_client.py #   REST API クライアント
│   │   └── task_reminder.py    #   定期リマインダー (1時間)
│   ├── perception/src/         # コンピュータビジョン
│   │   ├── main.py             #   モニター管理・起動
│   │   ├── yolo_inference.py   #   YOLOv11 推論ラッパー
│   │   ├── pose_estimator.py   #   骨格推定 (17キーポイント)
│   │   ├── activity_analyzer.py#   4層バッファ活動分析 (421行)
│   │   ├── camera_discovery.py #   ネットワークカメラ自動検出
│   │   └── monitors/           #   Occupancy / Activity / Whiteboard
│   ├── dashboard/
│   │   ├── backend/            #   FastAPI + SQLAlchemy + Wallet 統合
│   │   └── frontend/src/       #   React 19 + AudioQueue + WalletPanel
│   ├── voice/src/              # VOICEVOX 連携
│   │   ├── main.py             #   11 API エンドポイント
│   │   ├── speech_generator.py #   LLM テキスト生成 + 通貨単位生成
│   │   ├── voicevox_client.py  #   VOICEVOX 合成クライアント
│   │   ├── rejection_stock.py  #   リジェクション音声ストック (最大100)
│   │   └── currency_unit_stock.py # 通貨単位名ストック (テキストのみ, 最大50)
│   └── wallet/src/             # 複式簿記信用台帳
│       ├── main.py             #   FastAPI + PostgreSQL
│       ├── models.py           #   Wallet, LedgerEntry, Device
│       ├── routers/            #   wallets, transactions, devices, admin
│       └── services/           #   ledger (複式仕訳), xp_scorer (報酬乗数)
├── edge/
│   ├── lib/                    # 共通ライブラリ
│   │   ├── soms_mcp.py         #   MCP + MQTT 統一インターフェース
│   │   ├── drivers/            #   6種センサードライバ
│   │   ├── swarm/              #   SensorSwarm プロトコルライブラリ
│   │   └── sensor_registry.py  #   設定駆動センサー初期化
│   ├── office/                 # MicroPython ファームウェア
│   │   ├── unified-node/       #   量産向け汎用ファームウェア
│   │   └── sensor-02/          #   BME680 + MH-Z19C (レガシー)
│   ├── swarm/                  # SensorSwarm ファームウェア
│   │   ├── hub-node/           #   SwarmHub (WiFi+MQTT, 中継)
│   │   ├── leaf-espnow/        #   ESP-NOW リーフ
│   │   ├── leaf-uart/          #   UART リーフ (Pi Pico)
│   │   └── leaf-arduino/       #   I2C/BLE リーフ (Arduino)
│   ├── test-edge/              # C++ ファームウェア
│   │   └── camera-node/        #   OV2640 カメラ (ESP32 WROVER)
│   └── tools/                  # 診断スクリプト (17本)
├── infra/
│   ├── docker-compose.yml      # メイン構成 (11サービス)
│   ├── docker-compose.edge-mock.yml  # 仮想デバイス構成
│   ├── mock_llm/               # ツール有無分岐 LLM シミュレータ
│   ├── virtual_edge/           # 仮想エミュレータ (SwarmHub + 3Leaf 含む)
│   ├── virtual_camera/         # RTSP テストパターン生成
│   ├── mosquitto/              # MQTT ブローカー設定
│   └── scripts/                # セットアップ・テストスクリプト
├── docs/
│   ├── SYSTEM_OVERVIEW.md      # 本文書 (技術全体像)
│   ├── CITY_SCALE_VISION.md    # 都市規模ビジョン
│   ├── CURRENCY_SYSTEM.md      # 経済システム詳細
│   └── architecture/           # 初期設計ドキュメント (設計時点の記録)
├── CLAUDE.md                   # 開発者ガイド
├── HANDOFF.md                  # 作業引き継ぎ
└── .env                        # 環境設定
```

---

## 13. デプロイメントモード

### モード1: フルシミュレーション (GPU/ハードウェア不要)

```bash
cd infra
docker compose --env-file ../.env \
  -f docker-compose.yml -f docker-compose.edge-mock.yml \
  up --build -d \
  mosquitto backend frontend brain voice-service voicevox mock-llm virtual-edge
```

- **Mock LLM**: キーワードマッチで tool call を生成 (「温度」+「高」→ create_task)
- **Virtual Edge**: 仮想センサー (温度/CO2/湿度をランダムウォーク)
- **Virtual Camera**: RTSP テストパターン

### モード2: プロダクション (AMD ROCm GPU + 実ハードウェア)

```bash
docker compose -f infra/docker-compose.yml up -d --build
```

- **Ollama + Qwen2.5:14b**: 本物の LLM 推論 (ROCm, ~51 tok/s)
- **Perception**: YOLOv11 による実カメラ映像分析 (ホストネットワーク)
- **実 ESP32**: unified-node + SensorSwarm の実センサーデータ

### サービスポート

| サービス | ポート | コンテナ名 |
|---------|--------|-----------|
| Dashboard Frontend (nginx) | 80 | soms-frontend |
| Dashboard Backend API | 8000 | soms-backend |
| Mock LLM | 8001 | soms-mock-llm |
| Voice Service | 8002 | soms-voice |
| Wallet Service | 8003 | soms-wallet |
| PostgreSQL | 5432 | soms-postgres |
| VOICEVOX Engine | 50021 | soms-voicevox |
| Ollama (LLM) | 11434 | soms-ollama |
| MQTT Broker | 1883 | soms-mqtt |

---

## 補遺: 設計文書索引

| ファイル | 内容 |
|---------|------|
| `docs/architecture/kick-off.md` | 初期構想・技術研究報告書 (包括的) |
| `docs/architecture/detailed_design/01_central_intelligence.md` | LLM + 推論エンジン詳細 |
| `docs/architecture/detailed_design/02_communication_protocol.md` | MCP over MQTT 設計 |
| `docs/architecture/detailed_design/03_perception_verification.md` | 視覚検証システム |
| `docs/architecture/detailed_design/04_economy_dashboard.md` | 経済モデル + ダッシュボード |
| `docs/architecture/detailed_design/05_edge_engineering.md` | エッジデバイス実装 |
| `docs/architecture/detailed_design/06_security_privacy.md` | セキュリティ・プライバシー |
| `docs/architecture/detailed_design/07_container_architecture.md` | コンテナ構成 |
| `CLAUDE.md` | 開発者向けクイックリファレンス |
| `HANDOFF.md` | 直近の作業引き継ぎ |
