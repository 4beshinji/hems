# 04. テスト手順

このドキュメントでは、テストエッジデバイスの統合テスト手順を説明します。

---

## 1. テスト環境の準備

### 1.1 必要なコンポーネント

| コンポーネント | 状態 | 確認方法 |
| :--- | :--- | :--- |
| **MQTTブローカー** | 起動中 | `sudo systemctl status mosquitto` |
| **センサーノード** | 接続中 | シリアルモニタで確認 |
| **カメラノード** | 接続中 | シリアルモニタで確認 |
| **ネットワーク** | 同一LAN | 全デバイスが同じWi-Fiに接続 |

### 1.2 MQTT クライアントツール

テスト用に以下のツールをインストール：

```bash
# Linux/macOS
sudo apt install mosquitto-clients  # or brew install mosquitto

# Windows
# https://mosquitto.org/download/
```

---

## 2. 基本テスト

### 2.1 接続確認テスト

#### ステップ1: MQTTトピックの監視

```bash
mosquitto_sub -h localhost -t '#' -v
```

> **説明**: すべてのMQTTメッセージをリアルタイムで表示します。

#### ステップ2: センサーノードの稼働確認

**期待される出力（10秒ごと）:**
```
office/meeting_room_a/sensor/sensor_node_01/temperature 24.56
office/meeting_room_a/sensor/sensor_node_01/humidity 45.23
office/meeting_room_a/sensor/sensor_node_01/pressure 1013.25
office/meeting_room_a/sensor/sensor_node_01/gas 123.45
office/sensor/sensor_node_01/status {"device_id":"sensor_node_01",...}
```

✅ **合格基準**: 10秒ごとにデータが更新される

#### ステップ3: カメラノードのステータス確認

**期待される出力（30秒ごと）:**
```
office/camera/camera_node_01/status {"device_id":"camera_node_01","status":"online",...}
```

✅ **合格基準**: 30秒ごとにステータスメッセージが届く

---

### 2.2 センサーデータ精度テスト

#### ステップ1: 基準値の確認

センサーノードの周囲温度を温度計で測定し、MQTTで受信した値と比較：

```bash
mosquitto_sub -h localhost -t 'office/meeting_room_a/sensor/+/temperature'
```

✅ **合格基準**: 実測値との誤差が ±2°C 以内

#### ステップ2: 応答性テスト

センサーに息を吹きかけて、温度・湿度の変化を観察：

```bash
mosquitto_sub -h localhost -t 'office/meeting_room_a/sensor/+/temperature' -t 'office/meeting_room_a/sensor/+/humidity'
```

✅ **合格基準**: 10秒以内に変化が反映される

---

### 2.3 カメラキャプチャテスト

#### ステップ1: レスポンストピックの監視

別のターミナルで：

```bash
mosquitto_sub -h localhost -t 'mcp/camera_node_01/response/#' -v
```

#### ステップ2: キャプチャコマンド送信

```bash
mosquitto_pub -h localhost \
  -t 'mcp/camera_node_01/request/capture_image' \
  -m '{"jsonrpc":"2.0","method":"capture_image","id":"test-001"}'
```

#### ステップ3: レスポンス確認

**期待される出力:**
```json
mcp/camera_node_01/response/test-001 {
  "jsonrpc": "2.0",
  "id": "test-001",
  "result": {
    "image_size": 45678,
    "format": "jpeg",
    "resolution": "UXGA"
  }
}
```

✅ **合格基準**: 5秒以内にレスポンスが返る

---

## 3. ストレステスト

### 3.1 連続キャプチャテスト

10回連続でカメラをトリガー：

```bash
for i in {1..10}; do
  mosquitto_pub -h localhost \
    -t 'mcp/camera_node_01/request/capture_image' \
    -m "{\"jsonrpc\":\"2.0\",\"method\":\"capture_image\",\"id\":\"test-$i\"}"
  sleep 2
done
```

✅ **合格基準**: すべてのレスポンスが正常に返る

### 3.2 長時間稼働テスト

24時間稼働させ、以下を確認：

```bash
# ログ監視スクリプト（例）
mosquitto_sub -h localhost -t '#' -v | tee mqtt_log_$(date +%Y%m%d).txt
```

✅ **合格基準**:
- メモリリークなし（`free_heap`が減少し続けない）
- 再起動なし
- Wi-Fi/MQTT切断と自動再接続が正常

---

## 4. 統合テスト

### 4.1 模擬シナリオ: 温度アラート

温度が閾値を超えたら通知を出すシミュレーション。

#### テストスクリプト (Python)

```python
#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json

THRESHOLD_TEMP = 26.0

def on_message(client, userdata, msg):
    if "temperature" in msg.topic:
        temp = float(msg.payload.decode())
        print(f"Temperature: {temp}°C")
        if temp > THRESHOLD_TEMP:
            print(f"⚠️ ALERT: Temperature exceeds {THRESHOLD_TEMP}°C!")

client = mqtt.Client()
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.subscribe("office/+/sensor/+/temperature")
client.loop_forever()
```

**実行:**
```bash
python3 test_alert.py
```

**テスト方法**: センサーを温める（手で握る、ドライヤーなど）

✅ **合格基準**: 閾値超過時にアラートが表示される

---

### 4.2 模擬シナリオ: 人感検知とカメラトリガー

（将来拡張用）PIRセンサーが人を検知したらカメラを自動撮影。

---

## 5. データログとモニタリング

### 5.1 Grafana + InfluxDBでの可視化（オプション）

長期的なデータ分析のため、MQTTデータをInfluxDBに保存し、Grafanaでグラフ化できます。

**クイックセットアップ:**

```bash
# InfluxDB
docker run -d -p 8086:8086 influxdb:2.7

# Telegraf (MQTT → InfluxDB ブリッジ)
# telegraf.confに以下を追加:
# [[inputs.mqtt_consumer]]
#   servers = ["tcp://localhost:1883"]
#   topics = ["office/#"]

# Grafana
docker run -d -p 3000:3000 grafana/grafana
```

---

## 6. トラブルシューティング

### 6.1 センサーデータが届かない

**確認項目:**
1. シリアルモニタでエラーログを確認
2. Wi-Fi接続状態（`WiFi.RSSI()`）
3. MQTTブローカー接続（`mqtt.connected()`）

**解決方法:**
```bash
# センサーノードのログ確認
pio device monitor --baud 115200
```

### 6.2 カメラ画像が取得できない

**確認項目:**
1. PSRAMが認識されているか（シリアルログ）
2. カメラ初期化エラーの有無
3. リクエストJSONの形式が正しいか

**デバッグ:**
```bash
# カメラノードのログ
pio device monitor --baud 115200

# JSONフォーマット検証
echo '{"jsonrpc":"2.0","method":"capture_image","id":"test"}' | jq .
```

---

## 7. 性能ベンチマーク

### 7.1 レイテンシ測定

MQTTリクエスト送信から応答受信までの時間を測定：

```bash
# タイムスタンプ付きログ
mosquitto_sub -h localhost -t 'mcp/#' -v --pretty-print | ts '[%Y-%m-%d %H:%M:%S]'
```

**目標値:**
- センサーテレメトリ: 10秒間隔
- カメラレスポンス: < 3秒

### 7.2 スループット測定

```bash
# メッセージカウント
mosquitto_sub -h localhost -t '#' | wc -l
```

---

## 8. 次のステップ

テストが完了したら、以下の拡張を検討してください：

1. **追加センサーの統合**: PIR、照度センサーなど
2. **エッジAI**: カメラノードでのローカル物体検出（ESP32-S3のAI拡張機能）
3. **OTA更新**: ファームウェアの無線アップデート
4. **セキュリティ**: MQTT over TLS、認証の追加

---

## 9. まとめ

| テスト項目 | 状態 |
| :--- | :--- |
| ✅ センサーノード接続 | |
| ✅ カメラノード接続 | |
| ✅ センサーデータ精度 | |
| ✅ カメラキャプチャ | |
| ✅ ストレステスト | |
| ✅ 統合シナリオ | |

すべてのテストに合格したら、本番環境への展開準備が整いました！
