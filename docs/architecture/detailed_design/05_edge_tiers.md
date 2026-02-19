# Edge Device Tier System

エッジデバイスの構成をティア（段階）制で定義する。ユーザーは予算・用途に応じて適切なティアを選択し、`unified-node` ファームウェアの `config.json` を書き換えるだけで運用を開始できる。

## Tier 一覧

| Tier | 構成 | 予算目安 | 用途 |
|------|------|----------|------|
| 1 | ESP32×1 + DHT22 | ~¥2,500 | 最小限の温湿度モニタリング |
| 2 | XIAO ESP32-C6 + BME680 + MH-Z19C + PIR | ~¥8,000 | 本格的環境計測（温湿度・気圧・VOC・CO2・人感） |
| 3 | SwarmHub + Leaf×3~5 + カメラ | ~¥15,000 | 分散センシング（複数ポイント・有線/無線混在） |
| 4 | マルチゾーン (Tier3×2~3 + リレー + IR) | ~¥35,000 | フルオフィス自動制御 |

## Tier 詳細

### Tier 1 — 最小構成

**対象**: 初めてのセットアップ、単一デスク監視、プロトタイピング

- **ボード**: ESP32-DevKitC-32E または XIAO ESP32-C3
- **センサ**: DHT22 (温度・湿度)
- **電源**: USB給電
- **測定項目**: temperature, humidity

```json
{
  "board": "esp32_devkitc",
  "sensors": [
    {"type": "dht22", "bus": "gpio", "pin": 4}
  ]
}
```

**WorldModel への影響**: `environment.temperature` と `environment.humidity` が更新される。CO2/照度は null のまま。

### Tier 2 — 本格環境計測

**対象**: 会議室、作業エリアの環境管理

- **ボード**: XIAO ESP32-C6 (WiFi 6, BLE 5.3, コンパクト)
- **センサ**:
  - BME680 (温度・湿度・気圧・VOC/ガス抵抗)
  - MH-Z19C (NDIR CO2)
  - PIR (HC-SR501 / AM312)
  - BH1750 (照度、オプション)
- **測定項目**: temperature, humidity, pressure, gas_resistance, co2, motion, illuminance

```json
{
  "board": "xiao_esp32_c6",
  "sensors": [
    {"type": "bme680", "bus": "i2c", "address": "auto"},
    {"type": "mhz19c", "bus": "uart", "uart_id": 1},
    {"type": "pir", "bus": "gpio", "pin": 3},
    {"type": "bh1750", "bus": "i2c", "address": "auto"}
  ]
}
```

**WorldModel への影響**: 全環境フィールドが利用可能。CO2 > 1000ppm で `co2_threshold_exceeded` イベント、PIR で `occupancy` 更新。

### Tier 3 — 分散センシング

**対象**: 広い部屋、複数測定ポイントが必要な環境

- **構成**: SwarmHub (ESP32-DevKitC) + SwarmLeaf×3~5 + USBカメラ or ESP32-CAM
- **通信**: ESP-NOW (無線、最大 250B/フレーム) or UART (有線)
- **Hub ローカルセンサ**: SHT31 + BH1750 + PIR（`sensors` キー）
- **Leaf センサ**: DHT22、土壌水分、水位など

Hub は Leaf のセンサデータを `office/{zone}/sensor/{hub_id}.{leaf_id}/{channel}` で MQTT にブリッジ。WorldModel は `.` 区切りの device_id を透過的に処理。

### Tier 4 — フルオフィス自動制御

**対象**: マルチゾーンのオフィス全体

- **構成**: Tier3 ×2~3ゾーン + リレーモジュール (照明/HVAC) + IR送信機 (エアコン)
- **Brain**: 全ゾーンの状態を統合し、LLM が最適制御を判断
- **制御**: `send_device_command` MCP ツールでリレー on/off、IR コマンド送信

## アップグレードパス

### Tier 1 → Tier 2

1. BME680 ブレイクアウトを I2C (SDA/SCL) に接続
2. config.json の `sensors` に `{"type": "bme680", "bus": "i2c", "address": "auto"}` を追加
3. DHT22 はそのまま残してもよいし、BME680 に置き換えてもよい
4. 必要に応じて MH-Z19C を UART 接続して CO2 計測を追加

### Tier 2 → Tier 3

1. SwarmHub 用の ESP32-DevKitC を追加
2. `edge/swarm/hub-node/` ファームウェアを書き込み
3. Leaf ノードを ESP-NOW or UART で接続
4. 既存の Tier 2 ノードはそのまま独立運用を継続

### Tier 3 → Tier 4

1. 2つ目のゾーンに Tier 3 セットを配置
2. リレーモジュール付き ESP32 を追加（`send_device_command` 対応）
3. Brain の system_prompt がマルチゾーン判断を自動化

## 決定マトリクス

| 条件 | 推奨 Tier |
|------|-----------|
| 予算 < ¥3,000 | Tier 1 |
| CO2 計測が必要 | Tier 2 以上 |
| 10m² 超の空間 | Tier 3 以上 |
| 照明/空調制御が必要 | Tier 4 |
| まず試したい | Tier 1 → 段階的に拡張 |
