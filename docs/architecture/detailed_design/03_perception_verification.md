# 03. Perception & Monitoring System

## 1. Objective: From Pixels to Semantics
The Perception Layer transforms raw visual data (pixels) into structured information (JSON) that the LLM can reason about. It provides continuous environmental awareness through pluggable monitors.

## 2. Technology Stack
- **Model**: **YOLOv11** (Ultralytics)
  - Object detection: `yolo11s.pt` (Small variant, COCO pretrained)
  - Pose estimation: `yolo11s-pose.pt` (17 COCO keypoints)
- **Hardware**: AMD RX 9700 (RDNA4, ROCm) for GPU inference
  - `HSA_OVERRIDE_GFX_VERSION=12.0.1`
  - Specific device mapping: `/dev/dri/card1` + `/dev/dri/renderD128` (dGPU only)
- **Networking**: `network_mode: host` for direct RTSP camera access
- **Image Sources**: Abstracted via `ImageSourceFactory`
  - `RTSPSource`: RTSP camera streams
  - `MQTTSource`: MQTT-delivered images
  - `HTTPStream`: HTTP streaming sources

## 3. Pre-trained Perception (No Custom Training)
We rely on **standard COCO pretrained weights** to minimize maintenance:
- `person`: Occupancy detection and pose estimation
- `cup`, `bottle`, `chair`: General object detection
- No custom fine-tuning for domain-specific classes (window state, coffee pot, etc.)

## 4. Pluggable Monitor Architecture

### Monitor Base
All monitors extend `MonitorBase` and are configured via `config/monitors.yaml`:

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

### OccupancyMonitor
- YOLO object detection → person count per zone
- Publishes to `office/{zone}/camera/{camera_id}/status`

### WhiteboardMonitor
- Frame differencing for change detection
- Captures snapshots when significant changes are detected

### ActivityMonitor
- **Pose Estimation**: YOLO11s-pose → 17 COCO keypoints per person
- **Tiered Pose Buffer**: 4 tiers with increasing time spans (up to 4 hours, ~188 entries)
- **Posture Normalization**: Scale-invariant pose comparison
- **Prolonged Sitting Detection**: Triggers events when sedentary behavior exceeds thresholds
- **Activity Classification**: Standing, sitting, walking, etc.

## 5. Camera Auto-Discovery
`camera_discovery.py` automatically finds cameras on the local network:

1. **TCP Port Scan**: Async scan of configured network range (e.g., `192.168.128.0/24`)
2. **YOLO Verification**: Attempt to read a frame and run YOLO inference to confirm it's a valid camera
3. **Zone Mapping**: Map discovered IPs to zones using the `zone_map` configuration

## 6. MQTT Publishing
Perception results are published to the MQTT broker:
- Occupancy: `office/{zone}/camera/{camera_id}/status`
- Activity: `office/{zone}/activity/{monitor_id}`

The Brain subscribes to `office/#` and triggers cognitive cycles on state changes.

**Known issue** (H-1): Occupancy publishes `"count"` field but WorldModel expects `"person_count"`.
**Known issue** (H-2): Perception uses 3-part topics but WorldModel parser expects 5-part.

## 7. Task Completion: Trust Model
The system uses a **trust-based** completion model rather than visual verification:

1. Human clicks "Complete" on the dashboard
2. Task is marked as completed immediately
3. If the underlying condition persists (e.g., temperature still rising), the Brain's next cognitive cycle will detect it and may create a new task

There is no `verify_state` tool — tasks are completed on human action without automated visual confirmation.

## 8. Privacy
- **RAM-Only Processing**: Video streams are processed in memory, not persisted to disk
- **No Face Detection/Blurring**: The system detects `person` class (full body) only, not individual faces
- **No Cloud Uploads**: All processing happens on the local server
- **Local Storage**: No images or video are retained beyond the current processing frame

## 9. Configuration
Monitor configuration is YAML-driven (`config/monitors.yaml`), not hardcoded. This allows adding/removing monitors and cameras without code changes.

### Test Scripts
```bash
python3 services/perception/test_activity.py    # Activity analyzer test
python3 services/perception/test_discovery.py   # Camera discovery test
python3 services/perception/test_yolo_detect.py # YOLO detection test
```

See `services/perception/PERCEPTION_SYSTEM.md` for detailed technical documentation of the perception pipeline.
