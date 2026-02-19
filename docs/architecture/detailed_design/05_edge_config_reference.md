# Edge config.json Reference

`unified-node` ファームウェアの `config.json` スキーマリファレンス。

## 基本構造

```json
{
  "device_id": "env_01",
  "zone": "main",
  "wifi_ssid": "SSID",
  "wifi_password": "PASSWORD",
  "mqtt_broker": "192.168.x.x",
  "mqtt_port": 1883,
  "report_interval": 30,
  "board": "xiao_esp32_c6",
  "sensors": [...]
}
```

## フィールド一覧

### 必須フィールド

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `device_id` | string | MQTT デバイス識別子。WorldModel で一意 |
| `zone` | string | 所属ゾーン (`main`, `meeting_room_a` 等) |
| `wifi_ssid` | string | WiFi SSID |
| `wifi_password` | string | WiFi パスワード |
| `mqtt_broker` | string | MQTT ブローカーの IP アドレス |

### オプションフィールド

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `mqtt_port` | int | `1883` | MQTT ポート |
| `report_interval` | int | `30` | テレメトリ送信間隔（秒） |
| `board` | string | `"esp32_devkitc"` | ボード名（ピンマッピング解決用） |
| `sensors` | array | `[]` | センサ構成の配列 |
| `topic_prefix` | string | `"office/{zone}/sensor/{device_id}"` | MQTT トピックプレフィックス（通常変更不要） |

## `board` 一覧

| 値 | ボード | I2C (SDA/SCL) | UART1 (TX/RX) | DHT | PIR | LED |
|----|--------|---------------|---------------|-----|-----|-----|
| `esp32_devkitc` | ESP32-DevKitC-32E | 21/22 | 17/16 | 4 | 13 | 2 |
| `xiao_esp32_c6` | Seeed XIAO ESP32-C6 | 23/22 | 1/0 | 2 | 3 | 15 |
| `xiao_esp32_s3` | Seeed XIAO ESP32-S3 | 5/6 | 43/44 | 1 | 2 | 21 |
| `xiao_esp32_c3` | Seeed XIAO ESP32-C3 | 6/7 | 21/20 | 4 | 5 | -1 |
| `esp32_cam` | AI Thinker ESP32-CAM | 14/15 | 1/3 | 13 | 12 | 33 |

LED = `-1` はオンボード LED なし。

## `sensors` 配列

各要素は以下の構造を持つ:

```json
{"type": "<sensor_type>", "bus": "<bus_type>", ...options}
```

### センサタイプ

#### I2C センサ (`bus: "i2c"`)

| type | センサ | チャンネル | I2C アドレス | オプション |
|------|--------|-----------|------------|-----------|
| `bme680` | BME680 | temperature, humidity, pressure, gas_resistance | 0x77 / 0x76 | `address` |
| `sht31` | SHT31 | temperature, humidity | 0x44 / 0x45 | `address` |
| `sht30` | SHT30 | temperature, humidity | 0x44 / 0x45 | `address` |
| `bh1750` | BH1750 | illuminance | 0x23 / 0x5C | `address` |

**`address` オプション**:
- `"auto"` (デフォルト) — I2C スキャンで既知アドレスから自動検出
- `0x77` / `0x44` 等 — 明示的にアドレスを指定

```json
{"type": "bme680", "bus": "i2c", "address": "auto"}
{"type": "bh1750", "bus": "i2c", "address": "0x5C"}
```

#### UART センサ (`bus: "uart"`)

| type | センサ | チャンネル | オプション |
|------|--------|-----------|-----------|
| `mhz19c` | MH-Z19C CO2 | co2 | `uart_id`, `tx_pin`, `rx_pin` |

**オプション**:
- `uart_id` (デフォルト: `1`) — UART バス番号
- `tx_pin` / `rx_pin` — ピンオーバーライド（省略時はボード定義を使用）

```json
{"type": "mhz19c", "bus": "uart", "uart_id": 1}
{"type": "mhz19c", "bus": "uart", "tx_pin": 17, "rx_pin": 16}
```

初期化時にプローブ読み取りを実行。応答がなければスキップ。

#### GPIO センサ (`bus: "gpio"`)

| type | センサ | チャンネル | オプション |
|------|--------|-----------|-----------|
| `dht22` | DHT22 (AM2302) | temperature, humidity | `pin` |
| `dht11` | DHT11 | temperature, humidity | `pin` |
| `pir` | HC-SR501 / AM312 | motion | `pin` |

**`pin` オプション**: GPIO ピン番号。省略時はボード定義の `dht_pin` / `pir_pin` を使用。

```json
{"type": "dht22", "bus": "gpio", "pin": 4}
{"type": "pir", "bus": "gpio", "pin": 13}
```

## ピンオーバーライド

ボード定義のデフォルトピンを使用せず、個別に指定できる:

```json
{
  "board": "esp32_devkitc",
  "sensors": [
    {"type": "bme680", "bus": "i2c", "address": "auto"},
    {"type": "mhz19c", "bus": "uart", "tx_pin": 25, "rx_pin": 26},
    {"type": "dht22", "bus": "gpio", "pin": 15}
  ]
}
```

UART/GPIO の `pin` 指定はセンサごとに独立。I2C バスのピンはボード定義に従う（全 I2C センサ共通）。

## エラーハンドリング

- `sensors` が空配列 `[]` → ベア MCP ノード（heartbeat のみ、ツール登録あり）
- I2C デバイス未検出 → そのセンサをスキップ、他は継続
- UART プローブ失敗 → そのセンサをスキップ
- DHT 読み取り失敗 → 初期化は成功、`read_all()` 時にスキップ
- 全センサ失敗 → ノードは動作継続（`get_status` で空データ返却）

## MQTT トピック

`publish_sensor_data()` は `read_all()` の結果を per-channel で配信:

```
office/{zone}/sensor/{device_id}/temperature   → {"value": 22.1}
office/{zone}/sensor/{device_id}/humidity       → {"value": 45.2}
office/{zone}/sensor/{device_id}/co2            → {"value": 420}
office/{zone}/sensor/{device_id}/pressure       → {"value": 1013.2}
office/{zone}/sensor/{device_id}/gas_resistance → {"value": 50000}
office/{zone}/sensor/{device_id}/illuminance    → {"value": 350.5}
office/{zone}/sensor/{device_id}/motion         → {"value": 1}
```

WorldModel は各チャンネルを自動的に `EnvironmentData` / `OccupancyData` にマッピング。

## config_examples

`edge/office/unified-node/config_examples/` にティアごとのテンプレートを用意:

| ファイル | Tier | 構成 |
|----------|------|------|
| `tier1_devkitc_dht22.json` | 1 | ESP32-DevKitC + DHT22 |
| `tier1_c3_dht22.json` | 1 | XIAO ESP32-C3 + DHT22 |
| `tier2_c6_bme680_mhz19.json` | 2 | XIAO ESP32-C6 + BME680 + MH-Z19C |
| `tier2_full.json` | 2 | Tier2 + PIR + BH1750 |
| `tier3_hub_sensors.json` | 3 | SwarmHub + ローカルセンサ |
