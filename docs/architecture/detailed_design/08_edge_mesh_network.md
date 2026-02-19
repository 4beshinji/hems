# 08. Edge Mesh Network — 枝葉 (Eda/Ha) Architecture

## 1. Overview

現在の SensorSwarm アーキテクチャ（Hub + Leaf の 2 層構成）には構造的な限界がある:

1. **Standalone デバイス (MCPDevice) が deep sleep 不可** — MCP コマンド受信に常時 WiFi+MQTT 接続が必要
2. **スリープ中の Leaf へのコマンドが消失** — キューイングもリトライもなし
3. **Brain にデバイスの省電力状態の概念がない** — 全デバイス一律 10 秒タイムアウト
4. **マルチホップ中継が不可能** — Leaf は直接 Hub に到達しなければならない
5. **LAN 外デプロイに対応できない** — リモートサイトの仕組みがない

本設計は、デバイスネットワークを **4 階層**（生枝 / 枯枝 / 葉 / 遠隔地ノード）に再設計し、これらの問題を根本的に解決する。名称は日本語の樹木構造に由来する。

**スコープ**: アーキテクチャ設計 + プロトコル仕様の策定。コード実装は次フェーズ。

## 2. Network Topology

```
                         ┌─────────────────────────┐
                         │     Brain (LLM)          │
                         │  WorldModel              │
                         │  DeviceRegistry (NEW)    │
                         │  MCPBridge (enhanced)    │
                         └────────────┬─────────────┘
                                      │ MQTT (mosquitto:1883)
                    ┌─────────────────┼──────────────────────┐
                    │                 │                       │
           ┌────────┴────────┐ ┌─────┴──────┐       ┌───────┴────────┐
           │  生枝 (Nama-eda) │ │ 生枝 #2    │       │  Remote Node   │
           │  WiFi+MQTT+MCP  │ │            │       │  RPi+4G/LTE    │
           │  USB/PoE 常時給電│ │            │       │  Solar+Battery │
           └──┬──────────┬───┘ └────────────┘       │  Local MQTT    │
              │          │                           └──┬──────────┬──┘
      ESP-NOW │    UART  │                     ESP-NOW  │    BLE   │
              │          │                              │          │
     ┌────────┴───┐   ┌──┴──────┐              ┌───────┴──┐  ┌───┴───┐
     │ 枯枝       │   │ 葉      │              │ 枯枝     │  │ 葉    │
     │(Kare-eda)  │   │ (Ha)    │              │          │  │       │
     │ Battery    │   │ UART有線│              │ Battery  │  │ nRF54 │
     │ ESP-NOW    │   └─────────┘              └──┬──────┘  └───────┘
     │ Store&Fwd  │                               │
     └──┬─────┬───┘                          UART │
        │     │                                   │
   BLE  │     │ ESP-NOW                      ┌────┴───┐
        │     │                              │ 葉     │
   ┌────┴──┐ ┌┴──────────┐                  │ ATtiny │
   │ 葉    │ │ 枯枝 #2   │                  └────────┘
   │ nRF54 │ │ (中継)     │
   └───────┘ └──┬─────┬──┘
                │     │
           I2C  │     │ ESP-NOW
           ┌────┴──┐  ┌┴─────┐
           │ 葉    │  │ 葉   │
           │ATtiny │  │ESP32 │
           └───────┘  └──────┘
```

データは常に上流（Brain 方向）へ流れ、コマンドは下流へ配送される。枯枝はマルチホップ中継とバッファリングを担い、生枝が MQTT ゲートウェイとして機能する。

## 3. Device Classification

| 区分 | Type ID | 給電 | LAN 接続 | 通信方式 | 主な役割 |
|------|---------|------|----------|---------|---------|
| 生枝 (Nama-eda) | `0x10` | 有線 (USB/PoE) | WiFi+MQTT | MCP (JSON-RPC 2.0) | LAN ゲートウェイ、子機集約、重い処理 |
| 枯枝 (Kare-eda) | `0x20` | バッテリー or 有線 | なし | ESP-NOW / BLE / UART | 中継、バッファリング、ローカル集約 |
| 葉 (Ha) | `0x30` | バッテリー | なし | 上位枝へのトランスポート | センサ読取 → 報告 → deep sleep |
| 遠隔地 (Remote) | `0x40` | ソーラー+蓄電池 | 4G/LTE (間欠) | HTTPS バッチ同期 | オフライン自律 + 定期 Brain 同期 |

### 3.1 Naming Convention

**デバイス ID**: `{device_type}_{location}_{seq}`

| Device Type | Example ID |
|-------------|------------|
| 生枝 | `namaeda_room_01` |
| 枯枝 | `kareda_hall_01` |
| 葉 | `ha_door_01` |
| 遠隔地 | `remote_roof_01` |

**MQTT device_id**: ドット区切りで経路を表現 — `namaeda_room_01.kareda_hall_01.ha_door_01`

既存の WorldModel はドット区切り device_id を透過的に処理しており（SensorSwarm と同じ方式）、変更不要。

### 3.2 Device Characteristics

**生枝 (Nama-eda)**:
- 既存の MCPDevice + SwarmHub の合成体
- 常時給電・常時接続により MCP コマンドを即座に受信可能
- 配下の枯枝/葉のツリー全体を MQTT ハートビートで Brain に報告
- 子機へのコマンドキューイングを担当

**枯枝 (Kare-eda)**:
- バッテリー駆動で WiFi/MQTT 不要
- ESP-NOW による上流接続、配下の葉/枯枝を集約
- Store-and-Forward バッファリング（上流断時にデータを保持）
- マルチホップ中継ノードとして機能

**葉 (Ha)**:
- 最小電力のセンサノード（既存 SwarmLeaf の改良版）
- 起床 → 計測 → 送信 → deep sleep のサイクルに特化
- コマンド受信はウェイク時のみ（上位枝がキュー管理）

**遠隔地 (Remote)**:
- Raspberry Pi Zero 2W + 4G/LTE による LAN 外デプロイ
- ローカル MQTT ブローカーで配下デバイスを管理
- HTTPS バッチ同期で Brain と間欠接続
- YAML ルールによるローカル自律判定

## 4. Binary Protocol Extension

### 4.1 Existing Message Types (Unchanged)

既存メッセージタイプは完全に維持する。参照: `edge/lib/swarm/message.py`

| Type | Value | Direction | Description |
|------|-------|-----------|-------------|
| `MSG_SENSOR_REPORT` | `0x01` | Leaf → Hub | Sensor telemetry data |
| `MSG_HEARTBEAT` | `0x02` | Leaf → Hub | Periodic liveness signal |
| `MSG_WAKE_NOTIFY` | `0x03` | Leaf → Hub | Wake notification |
| `MSG_REGISTER` | `0x04` | Leaf → Hub | Initial registration |
| `MSG_COMMAND` | `0x80` | Hub → Leaf | Control command |
| `MSG_CONFIG` | `0x81` | Hub → Leaf | Configuration update |
| `MSG_TIME_SYNC` | `0x82` | Hub → Leaf | Time synchronization |
| `MSG_ACK` | `0xFE` | Both | Acknowledgement |
| `MSG_WAKE` | `0xFF` | Hub → Leaf | Wake signal |

### 4.2 New Message Types (0x10–0x18)

空き範囲 `0x10`–`0x1F` に新メッセージタイプを追加:

| Type | Value | Direction | Purpose |
|------|-------|-----------|---------|
| `MSG_RELAY` | `0x10` | Any | マルチホップ中継ラッパー |
| `MSG_ROUTE_DISCOVER` | `0x11` | Upstream | 枯枝がルート探索 |
| `MSG_ROUTE_ANNOUNCE` | `0x12` | Downstream | 生枝/枯枝がルート広告 |
| `MSG_QUEUE_STATUS` | `0x13` | Upstream | コマンドキュー状態報告 |
| `MSG_POWER_REPORT` | `0x14` | Upstream | 詳細電力状態 |
| `MSG_REGISTER_V2` | `0x15` | Upstream | 拡張デバイス登録 |
| `MSG_SYNC_REQUEST` | `0x16` | Remote → Brain | 同期要求 |
| `MSG_SYNC_RESPONSE` | `0x17` | Brain → Remote | 同期応答 |
| `MSG_BUFFERED_BATCH` | `0x18` | Upstream | バッファ済みデータ一括送信 |

### 4.3 MSG_RELAY (0x10) — Multi-Hop Relay

マルチホップ中継のためのラッパーフレーム。内部に元のフレーム全体を格納する。

```
Standard frame header:
  [MAGIC 0x53][VERSION 0x01][0x10][sender_id: 1B]

Relay-specific payload:
  [hop_count: 1B]          現在のホップ数（各中継で+1）
  [ttl: 1B]                最大ホップ数（各中継で-1、0で破棄）
  [origin_id: 1B]          元の送信者 ID
  [dest_id: 1B]            宛先 ID（0xFF = 上流/Brain 方向）
  [sequence: 2B u16LE]     origin 毎のシーケンス番号（重複排除用）
  [inner_frame: NB]        元のフレーム全体（MAGIC から checksum まで）

Standard frame footer:
  [XOR checksum: 1B]
```

**設計制約**:
- リレーフレームはネストしない（二重ラップ禁止）— `inner_frame` の `msg_type` が `0x10` の場合は破棄
- 各中継ノードは最近 16 件の `(origin_id, sequence)` をリングバッファで保持し重複排除
- `ttl` の初期値は最大 8 — 現実的なデプロイで 8 ホップ超は想定しない
- `ttl = 0` のフレームは即座に破棄

**オーバーヘッド分析**: リレー payload は 8 バイト（hop_count ~ sequence）+ inner_frame のサイズ。外側フレームヘッダ 4B + checksum 1B を加えると、30B のセンサレポートは合計 43B（ESP-NOW 250B 制限内に十分余裕あり）。

### 4.4 MSG_REGISTER_V2 (0x15) — Extended Registration

既存 `MSG_REGISTER` (0x04) の拡張版。新デバイスはこちらを使用し、既存デバイスは旧フォーマットのまま動作する。

```
[hw_type: 1B]              HW_ESP32=0x01, HW_NRF54=0x02, HW_ATTINY=0x03, HW_PICO=0x04
[device_type: 1B]          0x10=生枝, 0x20=枯枝, 0x30=葉, 0x40=遠隔地
[power_mode: 1B]           0x00=ALWAYS_ON, 0x01=LIGHT_SLEEP, 0x02=DEEP_SLEEP, 0x03=ULTRA_LOW
[cap_count: 1B]
[capabilities: cap_count B] 既存 capability type コード (0x01–0x82)
[relay_capable: 1B]        0x00=no, 0x01=yes
[max_children: 1B]         このノードが受け入れ可能な子機数
[sleep_interval_sec: 2B u16LE]  スリープ間隔（秒）
[battery_capacity_mah: 2B u16LE] バッテリー容量 (0 = 有線給電)
```

後方互換: Hub は `MSG_REGISTER` (0x04) と `MSG_REGISTER_V2` (0x15) の両方を受け付ける。旧フォーマットで登録されたデバイスは `device_type=0x30` (葉), `power_mode=DEEP_SLEEP` とみなす。

### 4.5 MSG_ROUTE_ANNOUNCE (0x12) — Route Advertisement

生枝/枯枝がブロードキャストする勾配ルーティング用の広告メッセージ。

```
[device_type: 1B]          0x10=生枝, 0x20=枯枝
[hops_to_mqtt: 1B]         MQTT ブローカーまでのホップ数（生枝=0, 枯枝=+1ずつ）
[available_slots: 1B]      受け入れ可能な子機残数
[rssi: 1B signed]          受信信号強度 (dBm, signed int8)
[power_mode: 1B]           0x00=ALWAYS_ON, 0x01=LIGHT_SLEEP, 0x02=DEEP_SLEEP, 0x03=ULTRA_LOW
```

### 4.6 MSG_ROUTE_DISCOVER (0x11) — Route Discovery

枯枝/葉が親ノードを探索するためのリクエスト。

```
[device_type: 1B]          送信者のデバイスタイプ
[hw_type: 1B]              ハードウェアタイプ
[required_transport: 1B]   0x00=any, 0x01=ESP-NOW, 0x02=BLE, 0x03=UART
```

受信した生枝/枯枝は `MSG_ROUTE_ANNOUNCE` で応答する。

### 4.7 MSG_QUEUE_STATUS (0x13) — Command Queue Status

枯枝が上流に報告するコマンドキューの状態。

```
[queued_count: 1B]         キュー内のコマンド数
[oldest_age_sec: 2B u16LE] 最古のキューエントリの経過秒数
[target_ids: NB]           キュー対象の leaf_id 一覧（各 1B, queued_count 分）
```

### 4.8 MSG_POWER_REPORT (0x14) — Power State

デバイスの詳細な電力状態を報告する。

```
[power_mode: 1B]            0x00=ALWAYS_ON, 0x01=LIGHT_SLEEP, 0x02=DEEP_SLEEP, 0x03=ULTRA_LOW
[battery_mv: 2B u16LE]      バッテリー電圧 (mV)
[battery_pct: 1B]            バッテリー残量 (0-100%)
[solar_mv: 2B u16LE]         ソーラーパネル電圧 (パネルなし=0)
[sleep_interval_sec: 2B u16LE]  現在のスリープ間隔
[awake_time_ms: 2B u16LE]    直近の稼働時間 (ms)
[next_wake_epoch: 4B u32LE]  次回起床の UNIX epoch
```

### 4.9 MSG_BUFFERED_BATCH (0x18) — Buffered Data Batch

接続回復時にバッファ済みセンサデータを一括送信する。

```
[batch_count: 1B]              バッチ内のレコード数（最大 ~15）
[origin_id: 1B]                データの元デバイス ID
For each reading:
  [timestamp_offset: 2B u16LE]   送信時刻からの経過秒数（負のオフセット）
  [channel: 1B]                  チャネルタイプ (CH_TEMPERATURE 等)
  [value: 4B float LE]           センサ値
```

**サイズ分析**: ヘッダ 2B + レコードあたり 7B。10 件で 72B、15 件で 107B。いずれも 1 ESP-NOW フレーム (250B) に収まる。

## 5. Gradient Routing

フラッディング（バッテリー浪費）でも明示的ルートテーブル（脆弱で管理が煩雑）でもなく、**勾配ルーティング (Gradient Routing)** を採用する。

### 5.1 Gradient Formation

1. 生枝が `MSG_ROUTE_ANNOUNCE` を定期ブロードキャスト (`hops_to_mqtt = 0`)
2. 受信した枯枝は自身の `hops_to_mqtt = 受信値 + 1` を記録し、再ブロードキャスト
3. ネットワーク全体で「MQTT に最も近い方向」を知る**勾配**が自然に形成される
4. **上流データ**: 各ノードは `hops_to_mqtt` が自身より小さい親方向へ送信
5. **下流コマンド**: 各ノードは子テーブル（登録済みの子機リスト）を使って配送

### 5.2 Parent Selection Score

複数の候補ノードから親を選ぶスコア関数:

```
score = (8 - hops_to_mqtt) * 100
      + available_slots * 10
      + (rssi + 100)           # rssi は通常 -90〜-30 dBm
      + (power_mode == ALWAYS_ON ? 50 : 0)
```

最もスコアの高いノードを親として選択する。

### 5.3 Route Announce Interval

| Device Type | Announce Interval | 理由 |
|-------------|------------------|------|
| 生枝 | 60 秒 | 常時給電、頻繁な広告が可能 |
| 枯枝 (有線給電) | 60 秒 | 電力制約なし |
| 枯枝 (バッテリー) | 300 秒 | 電力節約 |

### 5.4 Self-Healing

**親ノード死亡検出**:
1. 送信した MSG_SENSOR_REPORT / MSG_RELAY に対する MSG_ACK が 3 回連続で無応答（90 秒）
2. `DISCONNECTED` 状態に遷移
3. `MSG_ROUTE_DISCOVER` をブロードキャストし、代替親を探索
4. 応答した `MSG_ROUTE_ANNOUNCE` からスコア最高の親に切り替え

**ルート再評価**:
- 30 分ごとに受動的に `MSG_ROUTE_ANNOUNCE` を評価
- 現在の親スコアの **1.5 倍以上**のルートが見つかった場合のみ切り替え
- ヒステリシスにより不要な切り替えを防止

### 5.5 Routing Example

```
namaeda_room_01 (hops=0) ──ESP-NOW──▶ kareda_hall_01 (hops=1) ──ESP-NOW──▶ kareda_stair_01 (hops=2)
                                                                             │
                                                                        BLE  │
                                                                             ▼
                                                                       ha_temp_04 (leaf)

ha_temp_04 の上流パス:
  ha_temp_04 → kareda_stair_01 → kareda_hall_01 → namaeda_room_01 → MQTT → Brain
```

## 6. Command Queuing

### 6.1 Problem

現行設計では、スリープ中のデバイスへのコマンドは MCP 10 秒タイムアウトで失敗する。Brain は「配送不可能」と「オフライン」の区別ができない。

### 6.2 Solution

スリープ中デバイスへのコマンドは、**最も近い常時稼働の祖先**（生枝 or 有線枯枝）でキューイングする:

```
Brain → MCP → namaeda_room_01 → kareda_hall_01 → kareda_stair_01:
  「ha_temp_04 に set_interval(120) を送って」

kareda_stair_01: ha_temp_04 はスリープ中
  → コマンドをローカルキューに保存
  → ACK を上流に返送

kareda_hall_01 → namaeda_room_01 → MQTT → Brain:
  {"status": "queued", "target": "ha_temp_04", "estimated_delivery_sec": 285}

(285 秒後) ha_temp_04 がウェイク → MSG_SENSOR_REPORT 送信
  → kareda_stair_01: ウェイク検知 → キュー済みコマンドを配送
  → ha_temp_04: コマンド処理 → MSG_ACK 返送

kareda_stair_01 → ... → Brain:
  {"status": "delivered", "target": "ha_temp_04", "command": "set_interval"}
```

Brain は即座に「キュー済み」応答を受け取るため、MCP タイムアウト問題が解決される。

### 6.3 Queue Constraints

| Parameter | Value | 理由 |
|-----------|-------|------|
| 最大キューサイズ / ノード | 16 コマンド | RTC メモリ制約 |
| コマンド最大保持時間 | 1 時間 | 古すぎるコマンドは意味をなさない |
| キュー満杯時の応答 | `{"status": "queue_full"}` | Brain が代替手段を検討可能 |
| 同一デバイスへの重複コマンド | 最新のみ保持 | 古い set_interval を新しい set_interval で上書き |

### 6.4 Queue Status Reporting

枯枝は `MSG_QUEUE_STATUS` を 5 分間隔で上流に送信し、生枝がまとめて MQTT ハートビートに含める。Brain の DeviceRegistry がキュー状態を追跡する。

## 7. Store-and-Forward Buffering

### 7.1 Disconnection Handling

枯枝が上流接続を失った場合の段階的対応:

| Phase | 条件 | 動作 |
|-------|------|------|
| **CONNECTED** | 通常運用 | データを即座に上流転送 |
| **DISCONNECTED** | ACK 無応答 3 回 (90 秒) | ローカル循環バッファに保存開始 |
| **RECONNECTING** | 5 分間隔で再発見 | `MSG_ROUTE_DISCOVER` ブロードキャスト（バックオフ増加） |
| **ULTRA_LOW** | 1 時間孤立 | 15 分ごとの発見のみ、子機にもスリープ延長指示 |

### 7.2 Circular Buffer

- **ストレージ**: RTC メモリ (4KB) — deep sleep でも保持される
- **容量**: 約 400 件のセンサレコード（レコードあたり ~10B）
- **溢れ時**: 最古のデータを上書き（新しいデータが常に優先）
- **回復時**: `MSG_BUFFERED_BATCH` で一括アップロード（15 件/フレーム × 必要回数）

### 7.3 Recovery Sequence

```
1. 枯枝が代替親を発見 → MSG_REGISTER_V2 で再登録
2. MSG_BUFFERED_BATCH × N 回 でバッファ済みデータを送信
3. 各バッチは ACK 確認してから次を送信
4. 全送信完了後 → CONNECTED 状態に復帰
5. 通常のリアルタイム転送を再開
```

## 8. Remote Node Architecture

### 8.1 Hardware

| Component | Specification | 役割 |
|-----------|--------------|------|
| Raspberry Pi Zero 2W | ARM Cortex-A53, 512MB RAM | メインプロセッサ |
| SIM7600 4G HAT | LTE Cat.4 | インターネット接続 |
| ESP32-C6 | ESP-NOW radio | ローカルメッシュへの RF ブリッジ |
| Solar Panel | 6V 3W | 充電 |
| 18650 Battery | 3.7V 3000mAh | 蓄電 |

### 8.2 Software Stack

```
edge/remote/
├── edge_agent.py        # メインループ: 収集 → ローカル判定 → 同期
├── sync_client.py       # HTTPS バッチ同期 (gzip JSON)
├── rule_engine.py       # YAML ベースのローカル判定ルール
├── buffer_db.py         # SQLite バッファ (数週間分保持可能)
├── esp32_bridge.py      # シリアル通信で ESP32 ESP-NOW ハブと連携
├── local_mqtt.py        # ローカル Mosquitto 管理
└── config/
    ├── edge_rules.yaml  # ローカル自律ルール
    ├── devices.yaml     # 配下デバイス定義
    └── sync.yaml        # 同期設定
```

**動作サイクル**:
1. ESP32 ブリッジ経由で配下デバイスからデータ収集
2. ローカル MQTT ブローカーに publish（WorldModel と同じトピック形式）
3. `rule_engine.py` がローカルルールを評価（LLM 不要）
4. SQLite バッファにデータ蓄積
5. 同期間隔（デフォルト 15 分）で Brain に HTTPS バッチ送信
6. 緊急アラート時は即時同期をトリガー

### 8.3 Sync Protocol (HTTPS)

**Remote → Brain** (`POST /api/remote-sync/`):

```json
{
  "node_id": "remote_roof_01",
  "last_sync_epoch": 1739700000,
  "readings": [
    {
      "device_id": "ha_soil_01",
      "channel": "soil_moisture",
      "value": 42.3,
      "epoch": 1739700100
    },
    {
      "device_id": "ha_soil_01",
      "channel": "temperature",
      "value": 18.7,
      "epoch": 1739700100
    }
  ],
  "device_states": {
    "kareda_garden_01": {"online": true, "battery_pct": 78},
    "ha_soil_01": {"online": true, "battery_pct": 45}
  },
  "alerts": [
    {"type": "low_battery", "device": "ha_soil_01", "battery_mv": 2200}
  ]
}
```

**Brain → Remote**:

```json
{
  "commands": [
    {"target": "ha_soil_01", "command": "set_interval", "args": {"seconds": 120}}
  ],
  "config_updates": {
    "alert_thresholds": {"soil_moisture_low": 30}
  },
  "next_sync_interval_sec": 900
}
```

Brain 側の Dashboard Backend が受信 → ローカル MQTT にリパブリッシュ → WorldModel が通常通り処理する。

### 8.4 Local Autonomy

YAML ルールで LLM を必要としない簡易判定を実行:

```yaml
# config/edge_rules.yaml
rules:
  - name: soil_moisture_alert
    condition:
      channel: soil_moisture
      operator: "<"
      threshold: 30
    action:
      type: alert
      priority: high
      trigger_immediate_sync: true

  - name: battery_low_warning
    condition:
      channel: battery_mv
      operator: "<"
      threshold: 2500
    action:
      type: alert
      priority: medium
      trigger_immediate_sync: false
```

緊急ルールが発火した場合は次回同期を待たずに即時同期を実行する。

## 9. Brain-Side Changes

### 9.1 DeviceRegistry (New: `services/brain/src/device_registry.py`)

全デバイスのメタデータを一元管理するレジストリ。

**責務**:
- デバイス属性の管理: device_type, power_mode, capabilities, battery, parent/children 関係
- 生枝ハートビートから子機ツリー全体を自動構築（各デバイスが個別に MQTT 接続する必要なし）
- デバイス状態の追跡と遷移管理

**デバイス状態遷移**:

```
         ┌──────────────────────────────────────────┐
         │                                          │
         ▼                                          │
    ┌─────────┐  heartbeat   ┌─────────┐  power   ┌┴────────┐
    │ online  │◄────────────│sleeping │◄────────│ stale   │
    │         │──────────────▶│         │         │         │
    └─────────┘  sleep_report └─────────┘         └─────────┘
         │                                          ▲
         │ no heartbeat (5 min)                     │ no heartbeat (2 min)
         └──────────────────────────────────────────┘
         │
         │ no heartbeat (15 min)
         ▼
    ┌─────────┐
    │ offline │
    └─────────┘
```

| State | 条件 | 意味 |
|-------|------|------|
| `online` | ハートビートまたはデータ受信あり | 正常稼働中 |
| `sleeping` | `MSG_POWER_REPORT` で sleep 報告済み | 計画的スリープ中 |
| `stale` | 2 分間応答なし | 不明 (一時的な通信問題の可能性) |
| `offline` | 15 分間応答なし | オフライン |

**ツリー構築**: 生枝のハートビートに子機一覧を含めることで、Brain は 1 つの MQTT メッセージから配下ツリー全体を把握する:

```json
{
  "status": "online",
  "device_id": "namaeda_room_01",
  "device_type": "namaeda",
  "uptime_sec": 86400,
  "children": {
    "kareda_hall_01": {
      "device_type": "kareda",
      "power_mode": "ALWAYS_ON",
      "battery_pct": null,
      "hops": 1,
      "children": {
        "ha_temp_01": {"device_type": "ha", "power_mode": "DEEP_SLEEP", "battery_pct": 78, "hops": 2},
        "ha_door_01": {"device_type": "ha", "power_mode": "DEEP_SLEEP", "battery_pct": 92, "hops": 2}
      },
      "queue_status": {"queued_count": 1, "targets": ["ha_temp_01"]}
    },
    "ha_pir_01": {
      "device_type": "ha",
      "power_mode": "LIGHT_SLEEP",
      "battery_pct": 65,
      "hops": 1
    }
  }
}
```

### 9.2 Adaptive Timeout (MCPBridge Enhancement)

現行の一律 10 秒タイムアウトをデバイス状態に応じて動的に調整する:

| Device State | Timeout | 理由 |
|-------------|---------|------|
| 生枝 (直接) | 10 秒 | 現行と同じ、常時接続 |
| 枯枝経由 (+N hops) | 10 + 2N 秒 | 各ホップの中継遅延を考慮 |
| LIGHT_SLEEP デバイス | 10 + 2N + 5 秒 | ウェイク遅延を加算 |
| DEEP_SLEEP デバイス | 15 秒 | 「キュー済み」応答を待つ（実配送ではない） |

MCPBridge が `call_tool()` 実行時に DeviceRegistry を参照してタイムアウトを決定する。DEEP_SLEEP デバイスへのコマンドは、中間の常時稼働ノードからの `{"status": "queued"}` 応答を待つだけなので 15 秒で十分。

### 9.3 New LLM Tool: `get_device_status`

デバイスネットワークの状態をツリー形式で返す新しいツール:

```json
{
  "name": "get_device_status",
  "description": "デバイスネットワークの状態を取得する。オフライン、低バッテリー、通信エラーなどの問題を確認できる。",
  "parameters": {
    "type": "object",
    "properties": {
      "zone_id": {
        "type": "string",
        "description": "ゾーン ID (省略時: 全ゾーン)"
      }
    },
    "required": []
  }
}
```

**応答例**:
```
namaeda_room_01: online (子機 4 台中 3 台稼働)
  ├── kareda_hall_01: online, 有線給電, queue: 1 cmd
  │   ├── ha_temp_01: sleeping (次回起動: 240 秒後)
  │   └── ha_door_01: online, battery 92%
  ├── ha_pir_01: online, battery 65%
  └── kareda_stair_01: offline (10 分間応答なし) ⚠

remote_roof_01: last_sync 14 分前 (正常)
  ├── kareda_garden_01: online, battery 78%
  └── ha_soil_01: online, battery 45% ⚠ (低バッテリー)
```

### 9.4 WorldModel Extension

`get_llm_context()` の出力にデバイス健康サマリーセクションを追加する:

```
### デバイス状態
- namaeda_room_01: online (子機 4 台中 3 台稼働)
- kareda_hall_01.ha_door_01: sleeping (次回起動: 240 秒後)
- remote_roof_01: last_sync 14 分前 (正常)
- kareda_stair_01: offline (10 分間応答なし) ⚠
```

デバイスが全て正常な場合は `全デバイス正常稼働中` の 1 行のみ表示し、LLM コンテキストを節約する。

### 9.5 System Prompt Addition

`system_prompt.py` にデバイスネットワーク認識のガイダンスを追加:

```
## デバイスネットワーク
- デバイスには生枝（常時接続）、枯枝（中継）、葉（スリープ中心）、遠隔地（間欠接続）の4種類がある
- sleeping 状態のデバイスへのコマンドはキューイングされ、次回ウェイク時に配送される
- offline デバイスへのコマンドは失敗する — get_device_status で状態を確認してから送信すること
- 低バッテリーデバイスがある場合は create_task で交換タスクを検討すること
```

### 9.6 ToolExecutor Enhancement

`_handle_device_command()` にキュー済み応答の処理を追加:

```python
# 既存: 成功/失敗の2パターン
# 追加: "queued" ステータスの処理
if result.get("status") == "queued":
    estimated = result.get("estimated_delivery_sec", "不明")
    return {
        "status": "queued",
        "message": f"コマンドはキューに追加されました。配送予定: 約{estimated}秒後",
        "target": result.get("target")
    }
```

## 10. Migration Path

### 10.1 Existing Class Mapping

| 既存クラス | 新しい位置づけ | 変更内容 |
|-----------|-------------|---------|
| `MCPDevice` (`edge/lib/soms_mcp.py`) | 生枝の基盤 (変更なし) | heartbeat に `device_type` と `children` ツリーを追加 |
| `SwarmHub` (`edge/lib/swarm/hub.py`) | 生枝のコンポーネント (変更なし) | 枯枝子機を認識する拡張、MSG_RELAY 処理追加 |
| `SwarmLeaf` (`edge/lib/swarm/leaf.py`) | 葉の基盤 | ウェイク時コマンドキュー処理追加 |
| (新規) | 枯枝 `KaredaDevice` | リレー、バッファリング、ルート発見、コマンドキュー |
| (新規) | 遠隔地 `RemoteNode` | RPi Python アプリ |

### 10.2 Backward Compatibility

- **既存デバイス**: ファームウェア更新なしで動作継続
- **旧 MSG_REGISTER (0x04)**: 引き続き受け付ける。登録されたデバイスは `device_type=0x30` (葉), `power_mode=DEEP_SLEEP` として DeviceRegistry に格納
- **既存 MQTT トピック**: 完全に維持。新デバイスも同じ `office/{zone}/sensor/{device_id}/{channel}` 形式を使用
- **MCPBridge**: 新しいタイムアウトロジックは DeviceRegistry にエントリがないデバイスに対して現行の 10 秒をフォールバックとして使用
- **WorldModel**: ドット区切り device_id の既存処理をそのまま活用

## 11. New File Structure

```
docs/architecture/detailed_design/
  08_edge_mesh_network.md              ← 本設計ドキュメント

edge/lib/eda/                          ← NEW: Eda メッシュライブラリ
  __init__.py
  namaeda.py                           # 生枝クラス (MCPDevice + SwarmHub 合成)
  kareda.py                            # 枯枝クラス (リレー、バッファ、ルート発見)
  ha.py                                # 葉クラス (改良版 SwarmLeaf)
  routing.py                           # 勾配ルーティング、ルートテーブル
  relay.py                             # MSG_RELAY エンコード/デコード、重複排除
  command_queue.py                     # スリープ中デバイスへのコマンドキュー
  buffer.py                            # Store-and-forward 循環バッファ
  power.py                             # 電力レポート、バッテリー推定

edge/eda/                              ← NEW: 新アーキテクチャのファームウェア
  namaeda-node/main.py + config.json
  kareda-node/main.py + config.json
  ha-node/main.py + config.json

edge/remote/                           ← NEW: 遠隔地ノード (RPi)
  edge_agent.py
  sync_client.py
  rule_engine.py
  buffer_db.py
  esp32_bridge.py
  local_mqtt.py
  config/
    edge_rules.yaml
    devices.yaml
    sync.yaml

services/brain/src/
  device_registry.py                   ← NEW
  mcp_bridge.py                        ← MODIFIED (適応型タイムアウト)
  tool_registry.py                     ← MODIFIED (get_device_status 追加)
  tool_executor.py                     ← MODIFIED (キュー済み応答対応)
  world_model/world_model.py           ← MODIFIED (デバイス健康監視)
  world_model/data_classes.py          ← MODIFIED (DeviceNetworkState 追加)
  system_prompt.py                     ← MODIFIED (デバイス状態コンテキスト)

services/dashboard/backend/routers/
  remote_sync.py                       ← NEW (POST /api/remote-sync/)

infra/virtual_edge/src/
  virtual_kareda.py                    ← NEW
  virtual_remote.py                    ← NEW
  main.py                              ← MODIFIED (枯枝・遠隔地エミュレータ追加)
```

## 12. Implementation Phases

本設計の実装は以下の 4 フェーズで段階的に進行する:

### Phase 1: Protocol + Brain Foundation
- `edge/lib/swarm/message.py` にメッセージタイプ 0x10–0x18 を追加
- `services/brain/src/device_registry.py` を新規実装
- MCPBridge に適応型タイムアウトを実装
- `tool_registry.py` に `get_device_status` を追加
- WorldModel にデバイス健康サマリーを追加

### Phase 2: Kare-eda + Routing + Command Queue
- `edge/lib/eda/kareda.py` — 枯枝クラスの実装
- `edge/lib/eda/routing.py` — 勾配ルーティング
- `edge/lib/eda/relay.py` — MSG_RELAY 処理
- `edge/lib/eda/command_queue.py` — コマンドキューイング
- `edge/lib/eda/buffer.py` — Store-and-Forward バッファ
- `edge/lib/eda/ha.py` — 改良版葉クラス
- `edge/lib/eda/namaeda.py` — 生枝クラス

### Phase 3: Remote Node
- `edge/remote/` — 遠隔地ノードアプリ一式
- `services/dashboard/backend/routers/remote_sync.py` — 同期エンドポイント
- nginx ルーティング追加 (`/api/remote-sync/`)

### Phase 4: Virtual Emulators + Integration Test
- `infra/virtual_edge/src/virtual_kareda.py` — 仮想枯枝
- `infra/virtual_edge/src/virtual_remote.py` — 仮想遠隔地
- 統合テストスクリプト（マルチホップ中継、バッファリング回復、コマンドキュー配送）

## 13. Design Decisions Summary

| Decision | Choice | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| ルーティング方式 | 勾配ルーティング | フラッディング、明示的ルートテーブル | バッテリー効率と自己修復のバランス |
| コマンドキュー位置 | 最寄りの常時稼働祖先 | Brain 側キュー、全ノード分散キュー | レイテンシ最小化 + メモリ効率 |
| 遠隔地同期 | HTTPS バッチ (gzip JSON) | MQTT over 4G, WebSocket | ファイアウォール貫通性 + 帯域効率 |
| メッセージタイプ配置 | 0x10–0x18 (空き範囲) | 0x05–0x0F, 0x90–0x9F | 将来の Leaf→Hub/Hub→Leaf タイプ追加余地を残す |
| 親選択ヒステリシス | 1.5 倍スコア差 | 固定閾値, なし | 頻繁な親切り替えによるバッテリー浪費を防止 |
| バッファストレージ | RTC メモリ (4KB) | SPIFFS, 外部 EEPROM | deep sleep 耐性 + 書き込み速度 |
