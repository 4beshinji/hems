# Sovereign Urban Intelligence — 都市データ主権構想

**分散型ローカル LLM による都市の情報化アーキテクチャ**

---

## 0. この文書の位置づけ

```
本文書 (CITY_SCALE_VISION.md)     ← 都市規模の構想・計画
  └── docs/SYSTEM_OVERVIEW.md     ← SOMS の技術的全体像
        └── CLAUDE.md             ← 開発者向けリファレンス
```

SOMS (Symbiotic Office Management System) は、本構想の **Phase 0 実験場** である。本文書はその上位にある都市規模のビジョン、データアーキテクチャ、段階的展開計画を定義する。

---

## 1. 問題認識: なぜ都市は情報化されていないのか

### 1.1 現状の構造的欠陥

現代の「スマートシティ」は以下の根本的矛盾を抱えている:

| 表向きの主張 | 実態 |
|-------------|------|
| 「データ駆動の都市経営」 | センサーデータはクラウドベンダーのサーバーに吸い上げられ、都市は自身のデータにアクセスするために API 料金を支払う |
| 「AI による最適化」 | 中央集権的な推論サーバーが全データを処理し、ネットワーク障害で全機能が停止する |
| 「市民のための技術」 | カメラ映像は外部企業のクラウドに保存され、プライバシーの主権は都市にない |
| 「リアルタイム分析」 | データはクラウドへの往復で数百ミリ秒〜秒単位の遅延を持ち、真のリアルタイムではない |

**核心的問題**: データが生成される場所（都市）と処理される場所（クラウド）が分離している。これはデータ主権の喪失であり、都市が自律的に思考する能力の放棄である。

### 1.2 本構想が解決すること

> **都市が自身のデータを、自身の計算資源で、自身の論理で処理する。**
> **データは生成された場所で解釈され、構造化され、価値に変換される。**
> **外部への依存なしに、都市は自律的に「考える」ことができる。**

---

## 2. 基本構想: 分散型都市知能

### 2.1 アーキテクチャ概念

```
                          ┌─────────────────┐
                          │   City Data Hub  │
                          │  (集約・俯瞰)    │
                          └────────┬────────┘
                                   │ 構造化データの集約
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
              │  Core Hub  │ │  Core Hub  │ │  Core Hub  │
              │  (拠点A)   │ │  (拠点B)   │ │  (拠点C)   │
              │  LLM+GPU   │ │  LLM+GPU   │ │  LLM+GPU   │
              └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
                    │              │              │
            ┌───┬───┤        ┌────┤         ┌────┤
            │   │   │        │    │         │    │
           [S] [S] [C]     [S]  [C]       [S]  [S]

  S = Sensor Node (温度/湿度/CO2/気圧/騒音/振動/...)
  C = Camera Node (映像 → エッジ推論 or Core Hub 推論)
```

### 2.2 三層データ処理モデル

都市の生データは三段階で構造化される:

```
Layer 0: 物理世界 (Raw Signal)
  │  センサー電圧値、カメラ RGB ピクセル、音声波形
  │  → 量が膨大、意味不明、保存不要
  ▼
Layer 1: Core Hub (Local Intelligence)
  │  ローカル LLM がリアルタイム解釈
  │  センサーフュージョン、YOLO 推論、イベント検出
  │  → 構造化 JSON、イベントログ、判断記録
  │  → この層でデータの 99% は破棄される (意味だけ抽出)
  ▼
Layer 2: City Data Hub (Aggregation)
  │  複数 Core Hub の構造化データを集約
  │  時空間分析、パターン抽出、都市規模の最適化
  │  → Data Mart / Data Store / Data Lake
  ▼
Layer 3: 洞察と行動 (Insight & Action)
     都市計画への入力、政策提言、資源配分最適化
```

### 2.3 データ主権の原則

| 原則 | 実装 |
|------|------|
| **生データは外に出ない** | 全 Layer 0 データは Core Hub 内で処理・破棄。映像は RAM 上のみ |
| **推論はローカルで完結** | 各 Core Hub が独自の LLM を持ち、自律的に判断可能 |
| **集約は構造化データのみ** | City Data Hub に送られるのは統計値・イベント・判断ログのみ |
| **ネットワーク切断耐性** | 各 Core Hub は孤立状態でも独立動作を継続 |
| **監査可能性** | 全判断にタイムスタンプ付き根拠を記録 |

---

## 3. データアーキテクチャ

### 3.1 データの分類と流れ

```
┌──────────────────────────────────────────────────────────────┐
│                        Core Hub 内部                         │
│                                                              │
│  [Sensor Nodes] ──→ [MQTT Broker] ──→ [WorldModel]         │
│                                         │                    │
│                           ┌─────────────┤                    │
│                           ▼             ▼                    │
│                    [Event Store]   [LLM Brain]               │
│                    (時系列DB)      (ReAct Loop)              │
│                           │             │                    │
│                           ▼             ▼                    │
│                    [Data Lake]    [Action Log]               │
│                    (生イベント)   (判断+根拠)                │
│                           │             │                    │
│                           └──────┬──────┘                    │
│                                  ▼                           │
│                           [Data Mart]                        │
│                           (集約済み)                         │
└──────────────────────────┬───────────────────────────────────┘
                           │ 構造化データのみ
                           ▼
                    [City Data Hub]
                    ┌──────────────────┐
                    │  Data Warehouse  │
                    │  (全拠点統合)    │
                    └──────────────────┘
```

### 3.2 データストア設計

各 Core Hub が保持する三つのデータストア:

#### Data Lake (生イベント蓄積)

**目的**: Core Hub 内で発生した全イベントの時系列保存。未加工だが構造化済み。

```json
// 例: 環境イベント
{
  "timestamp": "2026-02-13T14:23:05+09:00",
  "hub_id": "hub_office_01",
  "zone": "kitchen",
  "event_type": "environment_reading",
  "source": "sensor/env_01/temperature",
  "data": { "value": 28.5, "unit": "celsius" },
  "context": { "occupancy": 3, "window_state": "unknown" }
}

// 例: LLM 判断イベント
{
  "timestamp": "2026-02-13T14:23:08+09:00",
  "hub_id": "hub_office_01",
  "event_type": "llm_decision",
  "trigger": "co2_threshold_exceeded",
  "reasoning": "CO2が1050ppmで3人在室。換気タスクを作成",
  "action": "create_task",
  "parameters": { "title": "換気", "bounty": 1500, "urgency": 3 },
  "world_state_snapshot": { "temperature": 28.5, "co2": 1050, "occupancy": 3 }
}

// 例: 知覚イベント
{
  "timestamp": "2026-02-13T14:23:10+09:00",
  "hub_id": "hub_office_01",
  "event_type": "perception_detection",
  "monitor": "activity_monitor_01",
  "data": {
    "person_count": 3,
    "activity_class": "moderate",
    "posture_status": "mostly_static",
    "posture_duration_sec": 1847
  }
}
```

**保持期間**: 90日 (Core Hub のローカルストレージ容量に依存)
**技術候補**: TimescaleDB, QuestDB, SQLite + 時系列パーティション

#### Data Store (運用状態)

**目的**: 現在の運用状態とアクティブなエンティティの管理。WorldModel の永続化。

```
Tables:
├── zones          # ゾーン定義と現在の状態スナップショット
├── devices        # 登録済みデバイスとヘルスステータス
├── tasks          # タスクライフサイクル (OPEN → COMPLETED)
├── voice_events   # 音声インタラクションログ
├── sensor_config  # センサーキャリブレーション・閾値
└── hub_config     # Core Hub 自体の設定
```

**技術**: SQLite (現行) → PostgreSQL (スケール時)

#### Data Mart (集約・分析用)

**目的**: City Data Hub への送信用に集約された統計データ。人間の意思決定を支援する。

```json
// 例: 1時間ごとの環境サマリ (Core Hub → City Data Hub)
{
  "hub_id": "hub_office_01",
  "period": "2026-02-13T14:00:00/PT1H",
  "zones": {
    "kitchen": {
      "avg_temperature": 24.3,
      "max_co2": 1050,
      "avg_occupancy": 2.8,
      "comfort_index": 0.72,
      "events_count": { "co2_alert": 1, "sedentary_alert": 0 }
    },
    "meeting_room_a": {
      "avg_temperature": 22.1,
      "max_co2": 650,
      "avg_occupancy": 0.0,
      "comfort_index": 0.95,
      "events_count": {}
    }
  },
  "tasks_created": 1,
  "tasks_completed": 1,
  "llm_cycles": 120,
  "device_health": { "online": 5, "offline": 0 }
}
```

**送信頻度**: 1時間ごと (帯域最小化)
**送信プロトコル**: MQTT QoS 1 or HTTPS POST (Hub 間)

### 3.3 データ圧縮率の概算

| 層 | データ量 (1 Core Hub/日) | 備考 |
|----|------------------------|------|
| Layer 0: 生信号 | ~50 GB | カメラ映像 (VGA 3fps) + センサー |
| Layer 1: Event Store | ~500 MB | 構造化 JSON イベント |
| Data Lake | ~500 MB | = Event Store (全量保存) |
| Data Store | ~10 MB | アクティブ状態のみ |
| Data Mart | ~1 MB | 1時間集約 × 24 |
| City Hub 受信量 | ~1 MB/Hub/日 | Data Mart のみ |

**圧縮比**: 生信号 50GB → 外部送信 1MB = **50,000:1**

これが「データ主権」の意味である。都市が外部に送る必要があるデータは、生成されるデータの 0.002% に過ぎない。

---

## 4. Core Hub アーキテクチャ

### 4.1 Core Hub = SOMS の一般化

SOMS (現行オフィスシステム) は Core Hub の最初の実装である。Core Hub を一般化すると:

| SOMS コンポーネント | Core Hub での一般名 | 役割 |
|-------------------|-------------------|------|
| Brain (ReAct Loop) | Local Intelligence Engine | ローカル LLM による自律判断 |
| WorldModel | State Aggregator | センサーフュージョン + 状態管理 |
| Perception (YOLO) | Vision Processor | 映像 → 構造化データ変換 |
| MQTT Broker | Message Bus | Hub 内通信基盤 |
| Dashboard + Voice | Human Interface | 人間との協働チャネル |
| Sanitizer | Safety Layer | 行動制約・安全弁 |
| Tool Executor | Action Dispatcher | 外部デバイス・サービス制御 |
| Task Scheduling | Context-Aware Scheduler | 状況に応じたタスク配信 |

### 4.2 Core Hub ハードウェア要件

| 構成要素 | 最小構成 | 推奨構成 |
|---------|---------|---------|
| GPU | 16GB VRAM (量子化 LLM) | 32GB VRAM (フル推論 + Vision) |
| CPU | 8 コア | 16 コア |
| RAM | 32 GB | 64 GB |
| Storage | 500 GB SSD | 2 TB NVMe |
| Network | 1GbE + WiFi AP | 2.5GbE + 専用 IoT WiFi |
| 形態 | ミニ PC + eGPU | ラックマウント 1U |

**消費電力**: 150W (アイドル) 〜 350W (推論時)
**設置面積**: A4 用紙程度 (ミニ PC 構成時)

### 4.3 Sensor Node 仕様

各 Core Hub に接続される末端ノード:

| ノード種別 | ハードウェア | センサー | 通信 | 電源 |
|-----------|------------|---------|------|------|
| 環境センサー | ESP32-C6 | BME680 + MH-Z19C | WiFi / BLE Mesh | USB 5V / バッテリー |
| カメラノード | ESP32 WROVER / Pi Zero | OV2640 / USB Camera | WiFi | USB 5V / PoE |
| 音響センサー | ESP32 + I2S MEMS | INMP441 マイク | WiFi | USB 5V |
| 振動センサー | ESP32 + ADXL345 | 3軸加速度計 | WiFi / LoRa | バッテリー + ソーラー |
| 屋外環境 | ESP32 + IP67筐体 | BME280 + UV + 雨量 | LoRa / WiFi | ソーラー + バッテリー |

**共通プロトコル**: MCP over MQTT (JSON-RPC 2.0) — SOMS で実証済みの仕様をそのまま適用

---

## 5. City Data Hub アーキテクチャ

### 5.1 役割

City Data Hub は **Core Hub の集約点** であり、自身は生データを処理しない。

```
┌─────────────────────────────────────────────────────┐
│                   City Data Hub                      │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ Data         │  │ Analytics    │  │ Dashboard │ │
│  │ Warehouse    │  │ Engine       │  │ (City)    │ │
│  │              │  │              │  │           │ │
│  │ 全Hub統合    │  │ 時空間分析   │  │ 俯瞰表示  │ │
│  │ 時系列DB     │  │ パターン検出 │  │ 意思決定  │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│                                                      │
│  入力: 各 Core Hub の Data Mart (1MB/Hub/日)        │
│  出力: 都市レポート、異常パターン、資源配分提案      │
└─────────────────────────────────────────────────────┘
```

### 5.2 City Data Hub が解く問い

Core Hub 単独では見えない **都市規模のパターン** を抽出する:

| 問い | データソース | 分析手法 |
|------|------------|---------|
| 「A地区とB地区で同時にCO2が上昇 — 広域の大気汚染か？」 | 複数Hub の環境Mart | 時空間相関分析 |
| 「月曜午前に全オフィスの在室率が急上昇 — 通勤パターンの変化か？」 | 複数Hub の在室Mart | 周期性分析 |
| 「Hub-03 のセンサー精度が劣化 — メンテナンスが必要」 | Hub ヘルスメトリクス | 異常検知 |
| 「夏季のエネルギー消費を地区ごとに最適化」 | 環境 + タスク + デバイスMart | 最適化モデル |
| 「新しい拠点の最適なセンサー配置は？」 | 既存Hub の有効性データ | 推薦システム |

### 5.3 Hub 間通信プロトコル

```
Core Hub ──── MQTT (QoS 1) or HTTPS ────→ City Data Hub
                     │
                     │  ペイロード: Data Mart JSON
                     │  頻度: 1時間ごと
                     │  認証: mTLS (相互TLS)
                     │  暗号化: TLS 1.3
                     │
                     │  ネットワーク障害時:
                     │  → ローカルキューに蓄積
                     │  → 復旧後に一括送信
                     │  → Core Hub の自律動作は継続
```

---

## 6. 段階的展開ロードマップ

### Phase 0: オフィス実験場 (現在)

**SOMS = 単一 Core Hub の実証**

```
[Office] ← 1 Core Hub
  ├── 2-3 Sensor Nodes (ESP32)
  ├── 1 Camera Node
  ├── 1 GPU Server (32GB VRAM)
  ├── Mock LLM / Ollama
  └── Dashboard + Voice
```

**目的**:
- ReAct 認知ループの有効性検証
- MCP over MQTT プロトコルの実戦テスト
- センサーフュージョン + WorldModel の精度検証
- 人間協働 (タスク経済) の行動科学的検証
- データ層 (Event Store → Data Mart) パイプラインの基礎実装

**現在の達成状況**:
- [x] Brain ReAct ループ (5ツール, 最大5反復)
- [x] WorldModel + センサーフュージョン (指数減衰加重平均)
- [x] MCP over MQTT (JSON-RPC 2.0)
- [x] エッジデバイス (MicroPython + C++ 両対応)
- [x] Perception (YOLOv11 物体検出 + 姿勢推定 + 4層活動分析)
- [x] Dashboard (React 19 ゲーミフィケーション UI)
- [x] Voice (VOICEVOX 日本語音声合成)
- [x] 安全機構 (Sanitizer + 憲法的AI)
- [x] 仮想テスト環境 (Mock LLM + Virtual Edge + Virtual Camera)
- [ ] Data Lake / Data Mart パイプライン
- [ ] Docker 起動・統合テスト完了
- [ ] 本番 LLM (Ollama + Qwen2.5) 稼働検証

**Phase 0 完了条件**:
1. 全サービスが Docker で安定稼働 (24時間連続)
2. センサーデータ → LLM 判断 → タスク作成 → 人間完了 の E2E フロー動作
3. Event Store への全イベント記録
4. Data Mart 集約ジョブの自動実行

---

### Phase 1: 拠点拡張 — 複数ゾーン × 単一 Hub

**オフィス内のセンサーノード拡充と Data Lake 実装**

```
[Office] ← 1 Core Hub (強化)
  ├── Zone: Main Room    → 3 Sensor + 1 Camera
  ├── Zone: Kitchen      → 2 Sensor + 1 Camera
  ├── Zone: Meeting A    → 2 Sensor + 1 Camera
  ├── Zone: Meeting B    → 1 Sensor
  ├── Zone: Entrance     → 1 Camera (人流)
  └── Zone: Outdoor      → 1 環境センサー (気象)
```

**主要タスク**:
- Event Store 実装 (TimescaleDB or QuestDB)
- Data Mart 集約パイプライン (1時間バッチ)
- センサーノード量産 (統一ファームウェア, config.json 差し替えのみ)
- カメラ自動検出の本番運用
- LoRa ノード実験 (屋外センサー用)
- WorldModel の多ゾーン同時処理性能最適化
- LLM の多ゾーン判断精度検証

**完了条件**:
1. 10+ センサーノードの同時安定運用
2. Data Lake に 30日分のイベント蓄積
3. Data Mart から意味のある環境レポート生成
4. ゾーン間の相関分析 (例: 「会議室の CO2 上昇 → 主室の窓開け推奨」)

---

### Phase 2: 多拠点展開 — 複数 Core Hub × City Data Hub

**第2の Core Hub を設置し、Hub 間連携を実証**

```
[Office Hub] ──────┐
  ├── 10+ Nodes    │
  └── Local LLM    │     ┌────────────────┐
                   ├────→│ City Data Hub  │
[Remote Hub] ──────┤     │ (集約サーバー)  │
  ├── 5+ Nodes     │     └────────────────┘
  └── Local LLM    │
                   │
[Mobile Hub] ──────┘
  ├── 2-3 Nodes (ポータブル)
  └── Edge LLM (小型 GPU)
```

**主要タスク**:
- City Data Hub の実装 (Data Warehouse + Analytics Dashboard)
- Hub 間通信プロトコル確立 (mTLS, ローカルキュー)
- Hub 登録・認証メカニズム
- Data Mart スキーマの標準化 (全 Hub 共通フォーマット)
- 小型 Core Hub の設計 (Mini PC + eGPU、消費電力 100W 以下)
- ネットワーク分断時の自律動作検証 (72時間孤立テスト)
- Hub 間イベント伝播 (「A拠点で検知した異常をB拠点に通知」)

**完了条件**:
1. 2+ Core Hub が独立に自律動作
2. City Data Hub が全 Hub のデータを統合表示
3. Hub 間の相関分析で単一Hub では見えないパターンを検出
4. ネットワーク切断後の再接続・データ同期が正常動作

---

### Phase 3: 都市展開 — N Core Hub × 分散 City Data Hub

**都市の複数地区に Core Hub を展開**

```
               ┌───────────────────┐
               │  City Dashboard   │
               │  (都市俯瞰)       │
               └────────┬──────────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
    ┌─────┴──────┐ ┌───┴────┐ ┌─────┴──────┐
    │ District A │ │Dist. B │ │ District C │
    │ Data Hub   │ │Data Hub│ │ Data Hub   │
    └─────┬──────┘ └───┬────┘ └─────┬──────┘
          │             │             │
    ┌──┬──┤        ┌──┬─┤        ┌──┬─┤
    │  │  │        │  │ │        │  │ │
   [H][H][H]     [H][H][H]     [H][H][H]

   H = Core Hub (各拠点)
```

**主要タスク**:
- Core Hub のゼロタッチプロビジョニング (設置→自動設定→稼働)
- District Data Hub (地区集約) の中間層設計
- 多段集約: Core Hub → District Hub → City Hub
- センサーノードの大量デプロイ手法 (ファームウェア OTA 更新)
- 都市規模の時空間分析エンジン
- 異種 Core Hub のフェデレーション (異なる LLM モデル間の協調)
- 公開データとの統合 (気象、交通、大気質)

---

### Phase 4: 自己進化 — LLM による自律的システム拡張

**長期ビジョン: システムが自らを改善する**

- LLM がシステムのコードを理解し、新しいセンサータイプへの対応コードを生成
- 新しいイベントパターンの自動検出と新規ルールの提案
- Core Hub 間での「知識共有」: A拠点で学んだパターンをB拠点に展開
- 人間タスクの成功/失敗パターンから最適な依頼方法を学習

---

## 7. SOMS から Core Hub への進化パス

### 7.1 追加が必要なコンポーネント

| コンポーネント | 現状 (SOMS) | Phase 1 | Phase 2 |
|--------------|------------|---------|---------|
| Event Store | なし (WorldModel はメモリのみ) | TimescaleDB 導入 | 同左 + レプリケーション |
| Data Lake | なし | Event Store = Data Lake | 同左 + 保持期間ポリシー |
| Data Mart | なし | 1時間集約バッチジョブ | 標準スキーマ + Hub間共有 |
| Hub 間通信 | なし | N/A | MQTT Bridge or HTTPS |
| Hub 管理 | なし | N/A | 登録・認証・ヘルスチェック |
| OTA 更新 | なし | ESP32 OTA 基盤 | 全ノード一括更新 |
| LoRa 対応 | なし | 実験的導入 | 屋外ノード標準 |

### 7.2 変更が不要なコンポーネント (SOMS の設計が正しかった部分)

| コンポーネント | 理由 |
|--------------|------|
| **MCP over MQTT** | Hub 内通信の標準として Phase 3 までそのまま使える |
| **ReAct 認知ループ** | 各 Core Hub が独立に思考するモデルとして適切 |
| **WorldModel + センサーフュージョン** | ゾーン増加に対してスケールする設計 |
| **憲法的 AI** | Hub ごとに異なるプロンプトで特化可能 |
| **Per-channel テレメトリ** | `{zone}/{device}/{channel}` → `{"value": X}` は普遍的 |
| **config.json + 共通ライブラリ** | ノード量産時の差分設定モデルとして正しい |
| **タスク経済** | 拠点ごとの人間協働インターフェースとして汎用的 |

---

## 8. データ主権の技術的保証

### 8.1 データ分類と処理場所

| データ分類 | 例 | 処理場所 | 保存場所 | 外部送信 |
|-----------|-----|---------|---------|---------|
| **映像** | カメラ RGB フレーム | Core Hub RAM | 保存しない | 不可 |
| **音声** | マイク波形 | Core Hub RAM | 保存しない | 不可 |
| **生テレメトリ** | 温度 23.5℃ | Core Hub | Event Store (90日) | 不可 |
| **LLM 判断ログ** | 「CO2高→タスク作成」 | Core Hub | Event Store (90日) | 不可 |
| **集約統計** | 1時間平均気温 | Core Hub | Data Mart | City Hub へ送信 |
| **タスク記録** | 完了タスク一覧 | Core Hub | Data Store | 匿名化して送信可 |

### 8.2 暗号化とアクセス制御

```
Sensor → Core Hub:  WPA3 (WiFi) + MQTT over TLS
Core Hub 内部:      Docker network isolation + mTLS
Core Hub → City Hub: TLS 1.3 + mTLS (相互認証)
Data at Rest:       AES-256 (Event Store, Data Mart)
```

### 8.3 データ削除権

任意の Core Hub を物理的に撤去すれば、その Hub に関する全生データが消失する。City Data Hub には集約統計しか残らない。これは **物理的なデータ主権** を保証する。

---

## 9. 生データから洞察までの変換例

### 例: 「都市の呼吸パターン」の発見

```
Phase 0 (SOMS) で観測:
  - オフィスの CO2 は 9:00 に急上昇、12:00 に低下、13:00 に再上昇、18:00 に低下
  - 人数変動と強い相関
  → 単一拠点の環境モニタリングとして有用

Phase 2 で観測:
  - Hub-A (オフィス街): CO2 ピーク 9:00, 13:00
  - Hub-B (商業施設): CO2 ピーク 11:00, 15:00, 19:00
  - Hub-C (住宅街): CO2 ピーク 7:00, 20:00
  → 各拠点の生活リズムが Data Mart から読み取れる

Phase 3 で発見:
  - City Data Hub が全 Hub の CO2 パターンを時空間分析
  - 「人の流れ」が可視化される: 住宅街(朝) → オフィス街(日中) → 商業施設(夕方) → 住宅街(夜)
  - 大気質の悪化パターン: 特定の風向きで地区Aの CO2 が異常上昇
  → 都市計画 (換気設備配置、緑地計画) への入力データとなる
```

**この洞察を得るために外部クラウドに送ったデータ**: 各 Hub の1時間平均 CO2 値のみ (数バイト/Hub/時間)

---

## 10. 想定される領域特化 Core Hub

Core Hub のソフトウェアは共通だが、接続するセンサーとシステムプロンプト (憲法) を変えることで領域特化する:

| Hub 種別 | センサー構成 | LLM の専門知識 | タスク例 |
|---------|------------|--------------|---------|
| **オフィス Hub** (SOMS) | 温湿度, CO2, カメラ | 快適性, 健康, 生産性 | 換気, 清掃, 備品補充 |
| **農業 Hub** | pH, EC, 水温, 照度 | 水耕栽培, 作物管理 | 養液調整, 収穫 |
| **水槽 Hub** | 水温, pH, TDS | 魚類飼育, 水質管理 | 給餌, 水換え |
| **店舗 Hub** | 人流カメラ, 温湿度 | 顧客行動, 在庫管理 | 品出し, 陳列変更 |
| **公共施設 Hub** | 騒音, 振動, 気象 | 安全管理, 設備保全 | 点検, 修繕 |
| **屋外環境 Hub** | 気象, 大気質, UV | 環境モニタリング | 警報, データ記録 |

全 Hub が同じ MCP over MQTT プロトコルと Data Mart スキーマを共有するため、City Data Hub は **異種 Hub のデータを統一的に集約** できる。

---

## 11. 成功指標

### Phase 0 (SOMS)

| 指標 | 目標値 |
|------|-------|
| 連続稼働時間 | 24時間以上 |
| センサー → タスク作成の E2E レイテンシ | < 10秒 |
| LLM の適切な判断率 | > 80% (人間評価) |
| 誤ったタスク作成率 | < 10% |
| デバイス再接続成功率 | > 95% |

### Phase 1

| 指標 | 目標値 |
|------|-------|
| 同時接続センサーノード数 | 10+ |
| Data Lake イベント記録漏れ率 | < 0.1% |
| Data Mart 集約からの洞察生成数 | 月5件以上 |

### Phase 2

| 指標 | 目標値 |
|------|-------|
| Hub 間通信の信頼性 | 99.9% |
| ネットワーク切断後の自律動作 | 72時間 |
| City Data Hub でのクロス Hub 分析精度 | 有意な相関を3件以上検出 |

### Phase 3

| 指標 | 目標値 |
|------|-------|
| 都市内 Core Hub 数 | 10+ |
| 外部クラウドへのデータ送信量 | 0 bytes |
| 都市計画への入力として採用 | 1件以上 |

---

## 付録 A: 用語定義

| 用語 | 定義 |
|------|------|
| **Core Hub** | ローカル LLM + GPU を持つ自律的な処理拠点。SOMS はその最初の実装 |
| **Sensor Node** | Core Hub に接続される末端デバイス (ESP32 等)。計算能力は最小限 |
| **City Data Hub** | 複数 Core Hub の集約データを統合分析するサーバー |
| **Data Lake** | Core Hub 内の全イベントの時系列保存。生に近い構造化データ |
| **Data Store** | 運用中のアクティブ状態を管理するデータベース |
| **Data Mart** | 集約・要約された分析用データ。Hub 外への送信対象 |
| **Data Sovereignty** | データが生成された場所で処理・保管される権利と能力 |
| **MCP over MQTT** | AI ツール呼び出し (JSON-RPC 2.0) を MQTT 上で実装したプロトコル |
| **ReAct Loop** | Think → Act → Observe の認知サイクル |
| **Constitutional AI** | LLM の行動を言語による原則で制約するアプローチ |

## 付録 B: 関連文書

| 文書 | 内容 |
|------|------|
| `docs/SYSTEM_OVERVIEW.md` | SOMS (Phase 0) の技術的全体像 |
| `docs/architecture/kick-off.md` | 初期構想・技術研究報告書 |
| `docs/architecture/detailed_design/` | 各サブシステムの詳細設計 (7文書) |
| `CLAUDE.md` | 開発者向けクイックリファレンス |
| `HANDOFF.md` | 直近の作業引き継ぎ |
