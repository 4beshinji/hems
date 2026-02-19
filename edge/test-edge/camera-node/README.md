# Camera Node - Freenove ESP32 WROVER v3.0

リクエスト駆動型の画像サーバー実装。

## 機能

- **動的解像度**: QVGA (320x240) 〜 UXGA (1600x1200)
- **MQTT通信**: リクエスト受信 → 画像キャプチャ → Base64送信
- **ステートレス**: メモリ効率を重視した設計

## ビルド方法

### 1. 設定変更

`src/main.cpp` の以下の行を環境に合わせて変更：

```cpp
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* MQTT_SERVER = "192.168.1.100";  // MQTTブローカーのIP
```

### 2. ビルド

```bash
cd edge/test-edge/camera-node
pio run
```

### 3. 書き込み

```bash
# 自動検出
pio run --target upload

# ポート指定
pio run --target upload --upload-port /dev/ttyUSB0
```

### 4. シリアルモニタ

```bash
pio device monitor
```

## MQTTプロトコル

### リクエスト受信

**トピック**: `mcp/camera_node_01/request/capture`

**ペイロード**:
```json
{
  "id": "req-abc123",
  "resolution": "VGA",
  "quality": 10
}
```

### レスポンス送信

**トピック**: `mcp/camera_node_01/response/{request_id}`

**ペイロード**:
```json
{
  "id": "req-abc123",
  "image": "<base64-encoded-jpeg>",
  "width": 640,
  "height": 480,
  "size_bytes": 12345,
  "format": "jpeg"
}
```

### ステータス送信

**トピック**: `office/camera/camera_node_01/status`

**ペイロード**:
```json
{
  "device_id": "camera_node_01",
  "status": "online",
  "uptime_sec": 12345,
  "free_heap": 123456,
  "wifi_rssi": -45
}
```

## テスト方法

### 1. MQTTブローカー起動

```bash
mosquitto -v
```

### 2. ステータス確認

```bash
mosquitto_sub -h localhost -t 'office/camera/+/status' -v
```

### 3. 画像リクエスト送信

```bash
mosquitto_pub -h localhost -t 'mcp/camera_node_01/request/capture' \
  -m '{"id":"test-001","resolution":"QVGA","quality":15}'
```

### 4. レスポンス受信

```bash
mosquitto_sub -h localhost -t 'mcp/camera_node_01/response/#' -v
```

## トラブルシューティング

### カメラ初期化失敗

```
Camera init failed: 0x20001
```

→ カメラモジュールの接続を確認

### MQTT接続失敗

→ ブローカーのIPアドレスとポートを確認

### メモリ不足

→ PSRAM が有効になっているか確認（起動時のログに `PSRAM: YES` と表示される）
