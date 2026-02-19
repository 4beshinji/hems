# 03. ファームウェアビルド・書き込み

このドキュメントでは、カメラノードとセンサーノードのファームウェアをビルド・書き込みする手順を説明します。

---

## 1. 事前準備

### 1.1 Wi-Fi/MQTT設定の変更

各ノードの `src/main.cpp` ファイルを開き、以下の設定を環境に合わせて変更してください。

**カメラノード**: `camera-node/src/main.cpp`
**センサーノード**: `sensor-node/src/main.cpp`

```cpp
// Wi-Fi設定
const char* WIFI_SSID = "YOUR_WIFI_SSID";      // ← 自分のWi-Fi SSIDに変更
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";  // ← 自分のWi-Fiパスワードに変更

// MQTT設定
const char* MQTT_SERVER = "192.168.1.100";  // ← MQTTブローカーのIPアドレスに変更
```

> **ヒント**: MQTTブローカーがまだ無い場合は、`mosquitto` をインストールしてください：
> ```bash
> # Linux
> sudo apt install mosquitto mosquitto-clients
> sudo systemctl start mosquitto
> 
> # macOS
> brew install mosquitto
> brew services start mosquitto
> ```

---

## 2. センサーノードのビルド・書き込み

### 2.1 プロジェクトディレクトリへ移動

```bash
cd /home/sin/code/gemini/bigbrother/edge/test-edge/sensor-node
```

### 2.2 依存関係のインストール

```bash
pio pkg install
```

**出力例:**
```
Resolving seeed_xiao_esp32s3 dependencies...
Installing adafruit/Adafruit BME680 Library @ ^2.0.0
Installing adafruit/Adafruit Unified Sensor @ ^1.1.0
...
```

### 2.3 ビルド

```bash
pio run
```

**成功時の出力例:**
```
Building in release mode
...
Linking .pio/build/xiao_esp32s3/firmware.elf
Building .pio/build/xiao_esp32s3/firmware.bin
========================= [SUCCESS] Took 23.45 seconds =========================
```

### 2.4 デバイスの接続

1. XIAO ESP32-S3をUSBケーブルでPCに接続
2. デバイスが認識されたか確認：

```bash
pio device list
```

**出力例:**
```
/dev/ttyACM0
------------
Hardware ID: USB VID:PID=303A:1001 SER=B4:0A:7C:12:34:56
Description: USB JTAG/serial debug unit
```

### 2.5 書き込み

```bash
pio run --target upload
```

**オプション: シリアルポートを明示的に指定**
```bash
pio run --target upload --upload-port /dev/ttyACM0
```

**成功時の出力例:**
```
Writing at 0x00010000... (100 %)
Wrote 876544 bytes (438123 compressed) at 0x00010000 in 7.5 seconds
...
Leaving... Hard resetting via RTS pin...
========================= [SUCCESS] Took 12.34 seconds =========================
```

### 2.6 動作確認（シリアルモニタ）

```bash
pio device monitor
```

**期待される出力:**
```
=== Sensor Node Starting ===
Initializing BME680...
BME680 initialized successfully
Connecting to WiFi........
WiFi connected!
IP address: 192.168.1.123
Connecting to MQTT broker... connected!
=== Initialization Complete ===

=== Sensor Readings ===
Temperature: 24.56 °C
Humidity: 45.23 %
Pressure: 1013.25 hPa
Gas: 123.45 kOhms
Telemetry published
```

**終了方法**: `Ctrl+C`

---

## 3. カメラノードのビルド・書き込み

### 3.1 プロジェクトディレクトリへ移動

```bash
cd /home/sin/code/gemini/bigbrother/edge/test-edge/camera-node
```

### 3.2 依存関係のインストール

```bash
pio pkg install
```

### 3.3 ビルド

```bash
pio run
```

> **注意**: カメラノードはコードサイズが大きいため、ビルドに時間がかかる場合があります（1〜2分）。

### 3.4 デバイスの接続

1. Freenove ESP32 WROVER v3.0をUSBケーブルでPCに接続
2. デバイス確認：

```bash
pio device list
```

**出力例:**
```
/dev/ttyUSB0
------------
Hardware ID: USB VID:PID=10C4:EA60 SER=01234567
Description: CP2102 USB to UART Bridge Controller
```

### 3.5 書き込み

```bash
pio run --target upload
```

**書き込みエラーが発生した場合:**

Freenove ESP32 WROVERは、書き込み時に手動でブートモードにする必要がある場合があります：

1. ボード上の **BOOT** ボタンを押しながら
2. **RST** (リセット) ボタンを押す
3. **RST** を離す
4. **BOOT** を離す
5. 再度 `pio run --target upload` を実行

### 3.6 動作確認（シリアルモニタ）

```bash
pio device monitor --baud 115200
```

**期待される出力:**
```
=== Camera Node Starting ===
Initializing camera...
PSRAM found, using high resolution
Camera initialized successfully
Connecting to WiFi........
WiFi connected!
IP address: 192.168.1.124
Connecting to MQTT broker... connected!
Subscribed to: mcp/camera_node_01/request/capture_image
=== Initialization Complete ===
Status published
```

---

## 4. トラブルシューティング

### 4.1 ビルドエラー

**エラー:** `fatal error: Adafruit_BME680.h: No such file or directory`

**解決策:**
```bash
pio pkg install
```

### 4.2 書き込みエラー

**エラー:** `A fatal error occurred: Failed to connect to ESP32`

**解決策:**
1. USBケーブルがデータ転送対応か確認
2. 別のUSBポートを試す
3. ドライバをインストール (Windows/macOS)
4. 手動ブートモード (上記3.5参照)

**エラー:** `Permission denied: '/dev/ttyUSB0'`

**解決策 (Linux):**
```bash
sudo chmod 666 /dev/ttyUSB0
# または恒久的に
sudo usermod -a -G dialout $USER
# 再ログインが必要
```

### 4.3 Wi-Fi接続失敗

**症状:** `WiFi connection failed!` が表示され、デバイスが再起動を繰り返す

**解決策:**
1. `src/main.cpp` のSSID/パスワードが正しいか確認
2. Wi-Fiが2.4GHz帯か確認（5GHz非対応）
3. ルーターをESP32に近づける

### 4.4 MQTT接続失敗

**症状:** `MQTT connection failed!` が表示される

**解決策:**
1. ブローカーのIPアドレスが正しいか確認
2. ブローカーが起動しているか確認：
   ```bash
   # Linux
   sudo systemctl status mosquitto
   
   # Test with mosquitto_sub
   mosquitto_sub -h localhost -t '#' -v
   ```
3. ファイアウォール設定を確認

---

## 5. MQTT テスト

### 5.1 センサーデータの確認

別のターミナルで以下を実行：

```bash
mosquitto_sub -h localhost -t 'office/#' -v
```

**期待される出力:**
```
office/meeting_room_a/sensor/sensor_node_01/temperature 24.56
office/meeting_room_a/sensor/sensor_node_01/humidity 45.23
office/meeting_room_a/sensor/sensor_node_01/pressure 1013.25
office/meeting_room_a/sensor/sensor_node_01/gas 123.45
```

### 5.2 カメラへのコマンド送信

```bash
mosquitto_pub -h localhost \
  -t 'mcp/camera_node_01/request/capture_image' \
  -m '{"jsonrpc":"2.0","method":"capture_image","id":"test-123"}'
```

**カメラノードのシリアル出力:**
```
Message received on topic: mcp/camera_node_01/request/capture_image
Capturing image...
Image captured: 45678 bytes
Response sent to: mcp/camera_node_01/response/test-123
```

---

## 6. ファームウェアの更新

コードを変更した場合：

```bash
# 1. ビルド
pio run

# 2. 書き込み
pio run --target upload

# 3. モニタ
pio device monitor
```

**ワンライナー:**
```bash
pio run --target upload && pio device monitor
```

---

## 7. 次のステップ

ファームウェアの書き込みが完了したら、[04_testing.md](04_testing.md) でシステム全体のテスト手順を確認してください。
