# Perception Service — Camera Discovery & Activity Analysis System

## 概要

ESP32-CAMを中心としたLANカメラを自動発見し、人物検出・骨格推定・活動レベル分析を行うリアルタイム監視システム。リソース効率を重視した2-tier推論アーキテクチャと、時間減衰型の階層バッファにより、長時間の姿勢固定検出を実現する。

---

## アーキテクチャ

```
                          ┌─────────────────────────────────────────┐
                          │              main.py                    │
                          │                                         │
                          │  1. YAML設定読込                        │
                          │  2. Singleton初期化 (MQTT, YOLO, Pose)  │
                          │  3. 静的モニター登録                    │
                          │  4. CameraDiscovery.discover()          │
                          │  5. 動的ActivityMonitor生成              │
                          │  6. discovery結果をMQTT配信              │
                          │  7. scheduler.run()                     │
                          └──────────┬──────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
             ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼──────────┐
             │ Occupancy   │  │ Whiteboard │  │ Activity       │
             │ Monitor     │  │ Monitor    │  │ Monitor        │
             │ (MQTT cam)  │  │ (MQTT cam) │  │ (HTTP stream)  │
             └─────────────┘  └────────────┘  └───────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │  2-Tier推論    │
                                              │                │
                                              │ Tier1: YOLO    │
                                              │  person検出    │
                                              │  (全フレーム)  │
                                              │       │        │
                                              │  person有り?   │
                                              │  YES ↓  NO→skip│
                                              │                │
                                              │ Tier2: YOLO    │
                                              │  Pose推定      │
                                              │  (骨格17点)    │
                                              └───────┬────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │ Activity       │
                                              │ Analyzer       │
                                              │                │
                                              │ 階層バッファ   │
                                              │ 姿勢正規化     │
                                              │ 姿勢固定検出   │
                                              └───────┬────────┘
                                                      │
                                                      ▼
                                              MQTT publish
                                        office/{zone}/activity
```

---

## ディレクトリ構造

```
services/perception/
├── Dockerfile
├── requirements.txt
├── config/
│   └── monitors.yaml
└── src/
    ├── main.py                  # エントリーポイント・起動フロー
    ├── scheduler.py             # 並行モニター実行
    ├── camera_discovery.py      # LAN カメラ自動発見
    ├── image_requester.py       # MQTT画像リクエスト (既存)
    ├── yolo_inference.py        # YOLO物体検出 (singleton)
    ├── pose_estimator.py        # YOLO-Pose骨格推定 (singleton)
    ├── activity_analyzer.py     # 階層バッファ + 姿勢分析
    ├── state_publisher.py       # MQTT結果配信
    ├── image_sources/
    │   ├── __init__.py
    │   ├── base.py              # ImageSource ABC + CameraInfo
    │   ├── http_stream.py       # ESP32-CAM MJPEG
    │   ├── mqtt_source.py       # 既存MQTT protocol
    │   ├── rtsp_source.py       # IPカメラ/RTSP
    │   └── factory.py           # protocol→class レジストリ
    └── monitors/
        ├── __init__.py
        ├── base.py              # MonitorBase (image_source対応, ヘルスモニタリング)
        ├── occupancy.py         # OccupancyMonitor (人数カウント)
        ├── whiteboard.py        # WhiteboardMonitor (汚れ検知)
        └── activity.py          # ActivityMonitor (2-tier推論 + 活動分析)
```

---

## コンポーネント詳細

### 1. Camera Discovery (`camera_discovery.py`)

LAN上のカメラを3段階で自動発見する。

**Stage 1: Async TCPポートスキャン** (~10秒)
- 対象ポート: 80, 81, 554, 8554
- `asyncio.open_connection` による非同期並列スキャン
- Semaphore(128) で同時接続数を制限

**Stage 2: URLプローブ** (~30秒)
- ポートが開いているIPに対し候補URL群を試行:
  ```
  http://{ip}:81/
  http://{ip}:81/stream
  http://{ip}/stream
  http://{ip}:8080/?action=stream
  http://{ip}/webcam/?action=stream
  http://{ip}:8000/stream.mjpg
  ```
- `cv2.VideoCapture` で接続 → 1フレーム取得で確認
- 成功したURLで `CameraInfo` を生成

**Stage 3: YOLO検証** (オプション, ~10秒)
- 取得フレームに対して `YOLOInference.infer()` を実行
- 何らかのオブジェクトを検出 → `verified=True`

**設定** (`monitors.yaml`):
```yaml
discovery:
  enabled: true
  network: "192.168.128.0/24"
  timeout: 3.0
  verify_yolo: true
  default_interval_sec: 10.0
  exclude_ips:
    - "192.168.128.1"      # gateway
    - "192.168.128.161"    # server
  zone_map:
    "192.168.128.172": "kitchen"
    "192.168.128.173": "meeting_room_b"
    "192.168.128.177": "desk_area_a"
    "192.168.128.178": "entrance"
```

### 2. ImageSource 抽象化レイヤー (`image_sources/`)

様々なプロトコルのカメラを統一インターフェースで扱う。

```python
class ImageSource(ABC):
    async def capture() -> Optional[np.ndarray]
    async def health_check() -> bool
    async def close()
```

| クラス | プロトコル | 用途 |
|---|---|---|
| `HttpStreamSource` | `http_stream` | ESP32-CAM MJPEG (:81/) |
| `MqttImageSource` | `mqtt` | 既存MQTT request/response |
| `RtspSource` | `rtsp` | IPカメラ (rtsp://) |

`ImageSourceFactory.create(camera_info)` で `protocol` 文字列からインスタンス生成。
`ImageSourceFactory.register()` で実行時にプロトコル追加可能。

### 3. MonitorBase (`monitors/base.py`)

全監視タスクの基底クラス。

**追加機能**:
- `image_source` パラメータ: `None` なら既存MQTTフォールバック
- ヘルスモニタリング: 3回連続失敗 → 30秒バックオフ + 警告ログ

```python
async def request_image(self):
    if self._image_source is not None:
        return await self._image_source.capture()
    # Legacy MQTT fallback
    requester = ImageRequester.get_instance()
    return await requester.request(self.camera_id, self.resolution, self.quality)
```

### 4. ActivityMonitor (`monitors/activity.py`)

**2-Tier推論パイプライン**:

```
フレーム取得
    │
    ▼
Tier 1: YOLO detect (yolo11s.pt, ~3ms)
    │
    ├─ person無し → skip (GPUコスト: ≈0)
    │
    ▼
Tier 2: YOLO pose (yolo11s-pose.pt, ~8ms)
    │
    ▼
ActivityAnalyzer.push()
    │
    ▼
MQTT publish → office/{zone}/activity
```

9台のカメラのうち人物がいるのが2台の場合、Tier 2は2台のみに発動。
推論コストが約1/4.5に削減される。

### 5. ActivityAnalyzer (`activity_analyzer.py`)

#### 階層バッファ (Tiered Pose Buffer)

時間が経過するにつれ解像度を下げながら長期履歴を保持する。

| Tier | 保持期間 | 解像度 | 最大エントリ数 | 内容 |
|---|---|---|---|---|
| Tier 0 (raw) | 60秒 | 全フレーム | ~20 | 生のPoseSnapshot |
| Tier 1 (10s) | 10分 | 10秒/バケット | ~60 | 平均姿勢シグネチャ |
| Tier 2 (1min) | 1時間 | 60秒/バケット | ~60 | 平均姿勢シグネチャ |
| Tier 3 (5min) | 4時間 | 300秒/バケット | ~48 | 平均姿勢シグネチャ |

**合計: ~188 エントリ（最大）で最大4時間の履歴を保持。**

集約タイミング:
- push() のたびに `_maybe_consolidate()` を呼び出し
- 各Tierの resolution 秒が経過するごとに下位Tierのエントリを平均化して上位に追加
- `_evict()` で各Tierの max_age を超えたエントリを削除

#### 姿勢正規化 (Posture Normalisation)

位置・スケール不変な姿勢シグネチャを生成する。

```
入力: COCO 17 keypoints (x, y) + confidence
    │
    ▼
アンカー計算: hip_mid = (left_hip + right_hip) / 2
スケール計算: shoulder_width = ||left_shoulder - right_shoulder||
    │
    ▼
正規化: normed[i] = (keypoints[i] - hip_mid) / shoulder_width
    │
    ▼
出力: (17, 2) 正規化済み姿勢シグネチャ
```

- 低信頼度キーポイント (conf < 0.3) は (0, 0) に設定
- 比較時は両方で非ゼロのキーポイントのみMSEを計算

#### 姿勢固定検出 (Posture Stasis Detection)

現在の姿勢と履歴を比較し、同一姿勢の継続時間を計算する。

```python
def _compute_posture_stasis(self):
    current_sig = self._current_posture_sig()  # 最新フレームの正規化姿勢
    # 全Tierを新しい順に走査
    for entry_ts, entry_sig in self._all_entries_reverse():
        if posture_distance(current_sig, entry_sig) < 0.05:
            earliest_same = entry_ts  # まだ同じ姿勢
        else:
            break  # 姿勢が変わった時点で停止
    duration = now - earliest_same
```

| 継続時間 | posture_status | Brain側の判断例 |
|---|---|---|
| < 10分 | `changing` | 通常状態 |
| 10分~20分 | `mostly_static` | 集中作業中（リマインド抑制） |
| > 20分 | `static` | 長時間同一姿勢（ストレッチ促進） |

#### 短期活動レベル (Short-term Activity)

Tier 0 (直近60秒) のフレーム間キーポイント変位から算出。

```
displacement = Σ ||kp_curr - kp_prev|| / visible_keypoints
activity_level = (displacement / image_diagonal) / dt
```

| activity_level | activity_class | 解釈 |
|---|---|---|
| < 0.002 | `idle` | 静止 |
| 0.002 ~ 0.01 | `low` | 微動（デスクワーク等） |
| 0.01 ~ 0.04 | `moderate` | 軽い活動 |
| > 0.04 | `high` | 活発に動いている |

### 6. PoseEstimator (`pose_estimator.py`)

YOLO11s-Pose モデルのシングルトンラッパー。

```python
persons = pose.estimate(image, conf_threshold=0.4)
# Returns:
# [
#   {
#     "bbox": [x1, y1, x2, y2],
#     "confidence": 0.92,
#     "keypoints": np.ndarray (17, 2),      # (x, y) pixel coords
#     "keypoint_conf": np.ndarray (17,),     # per-keypoint confidence
#   },
#   ...
# ]
```

COCO 17 keypoints:
```
0: nose        1: left_eye     2: right_eye    3: left_ear     4: right_ear
5: left_shoulder  6: right_shoulder  7: left_elbow  8: right_elbow
9: left_wrist    10: right_wrist   11: left_hip   12: right_hip
13: left_knee    14: right_knee    15: left_ankle  16: right_ankle
```

---

## MQTT トピック

| トピック | 発行元 | 内容 |
|---|---|---|
| `office/perception/discovery` | main.py | 発見カメラ一覧 |
| `office/{zone}/occupancy` | OccupancyMonitor | 人数カウント |
| `office/{zone}/whiteboard/status` | WhiteboardMonitor | 汚れ状態 |
| `office/{zone}/activity` | ActivityMonitor | 活動レベル + 姿勢状態 |
| `office/{zone}/tasks/request` | WhiteboardMonitor | タスク生成リクエスト |

### Activity ペイロード

```json
{
  "zone": "entrance",
  "person_count": 1,
  "activity_level": 0.0016,
  "activity_class": "idle",
  "posture_duration_sec": 1205.3,
  "posture_status": "static",
  "buffer_depth": {
    "raw": 20,
    "tier1": 58,
    "tier2": 20,
    "tier3": 4
  },
  "timestamp": 1739421112.0
}
```

### Brain 連携の判断ロジック

| 条件 | Brain の動作 |
|---|---|
| `activity_class == "idle"` + `posture_status == "static"` | ストレッチ促進通知 |
| `activity_class == "low"` + `posture_status == "mostly_static"` | 集中作業中 → リマインド抑制 |
| `activity_class in ["moderate", "high"]` | 通常リマインド頻度 |
| `person_count == 0` | 不在 → リマインド停止 |

---

## Docker 構成

`perception` コンテナは `network_mode: host` で動作し、LAN上のカメラに直接到達する。

```yaml
# infra/docker-compose.yml
perception:
  build: ../services/perception
  container_name: soms-perception
  restart: always
  depends_on:
    - mosquitto
  network_mode: host            # LAN カメラへの直接アクセス
  devices:
    - /dev/kfd:/dev/kfd         # ROCm GPU
    - /dev/dri:/dev/dri
  group_add:
    - video
  security_opt:
    - seccomp:unconfined
  environment:
    - MQTT_BROKER=localhost      # host network なので localhost
    - MQTT_PORT=1883
    - HSA_OVERRIDE_GFX_VERSION=12.0.1
```

---

## YOLOモデル

| モデル | ファイル名 | 用途 | サイズ |
|---|---|---|---|
| YOLO11s (detect) | `yolo11s.pt` | 物体検出 / 人物フィルタ | 18.4MB |
| YOLO11s (pose) | `yolo11s-pose.pt` | 骨格推定 (17 keypoints) | 19.4MB |

**注意**: ultralytics のモデル名は `yolo11s.pt` (旧名 `yolov11s.pt` ではない)。

---

## テスト結果

### カメラ発見テスト (2026-02-13)

192.168.128.0/24 上で **9台のESP32-CAM** を自動発見:

| IP | ゾーン | ストリームURL | YOLO検出結果 |
|---|---|---|---|
| 192.168.128.164 | — | http://...164:81/ | tv, chair x2, bicycle, potted plant, dining table |
| 192.168.128.166 | — | http://...166:81/ | **person x2**, tv x2, chair |
| 192.168.128.167 | — | http://...167:81/ | **person x1** |
| 192.168.128.168 | — | http://...168:81/ | (検出なし) |
| 192.168.128.172 | kitchen | http://...172:81/ | chair x3, refrigerator |
| 192.168.128.173 | meeting_room_b | http://...173:81/ | chair x5, potted plant x2 |
| 192.168.128.174 | — | http://...174:81/ | (検出なし) |
| 192.168.128.177 | desk_area_a | http://...177:81/ | bottle, chair, tv |
| 192.168.128.178 | entrance | http://...178:81/ | (検出なし / タイミングで人物検出) |

### 活動分析テスト (2026-02-13)

8ラウンド x 3秒間隔で実施:

| カメラ | activity_level | activity_class | posture_duration | posture_status | 解釈 |
|---|---|---|---|---|---|
| .166 | 0.0005 | idle | 0s | changing | 静止しているが微動あり |
| .178 (entrance) | 0.0016 | idle | 15.3s | changing | 同一姿勢を維持、蓄積中 |

階層バッファ状態 (24秒後):
```
raw=8  t1=2  t2=1  t3=1
```
→ 長時間運用でtier1→60, tier2→60, tier3→48まで成長し最大4時間カバー。

---

## 設定ファイル

### `config/monitors.yaml`

```yaml
monitors:
  - name: occupancy_meeting_room
    type: OccupancyMonitor
    camera_id: camera_node_01
    zone_name: meeting_room_a
    enabled: true

  - name: whiteboard_meeting_room
    type: WhiteboardMonitor
    camera_id: camera_node_01
    zone_name: meeting_room_a
    enabled: true

discovery:
  enabled: true
  network: "192.168.128.0/24"
  timeout: 3.0
  verify_yolo: true
  default_interval_sec: 10.0
  exclude_ips:
    - "192.168.128.1"
    - "192.168.128.161"
  zone_map:
    "192.168.128.172": "kitchen"
    "192.168.128.173": "meeting_room_b"
    "192.168.128.177": "desk_area_a"
    "192.168.128.178": "entrance"

yolo:
  model: yolo11s.pt
  pose_model: yolo11s-pose.pt
  device: 0

mqtt:
  broker: localhost
  port: 1883
```

---

## 既存コードへの影響

| コンポーネント | 変更内容 |
|---|---|
| `MonitorBase` | `image_source` パラメータ追加、ヘルスモニタリング追加 |
| `OccupancyMonitor` | コンストラクタに `image_source=None` 追加のみ |
| `WhiteboardMonitor` | 同上 |
| `ImageRequester` | 変更なし |
| `StatePublisher` | 変更なし |
| `YOLOInference` | モデル名修正 (`yolov11s.pt` → `yolo11s.pt`) |
| `TaskScheduler` | 変更なし |
