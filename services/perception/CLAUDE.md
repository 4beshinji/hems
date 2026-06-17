# services/perception/

Camera-based person detection + posture/activity tracking + optional VLM scene analysis. Extends parent `hems/CLAUDE.md`.

## Perception (Camera Detection + Activity Tracking + VLM Scene Analysis)

Camera-based person detection and posture/activity tracking using YOLOv11s-pose,
with optional VLM (Vision Language Model) integration via Ollama for scene understanding.

- **perception**: Docker service with YOLOv11s-pose inference pipeline
  - Captures frames from MCP (ESP32 MQTT) or stream (RTSP/HTTP) cameras
  - Single-pass person detection + skeleton keypoint extraction
  - Posture classification (standing/sitting/lying/walking) from COCO 17 keypoints
  - Activity level (0.0-1.0) with EMA smoothing + tiered pose buffer
  - Publishes to `hems/sensors/{zone}/camera/{cam_id}/status` and `hems/sensors/{zone}/activity/{cam_id}`
- **VLM integration** (optional, requires `--profile ollama` + `VLM_ENABLED=true`):
  - Default models: `moondream` (light/routine) and `minicpm-v` (heavy/event-triggered)
  - Adaptive frequency: 30min routine → event-boosted (1-5min) → quiet decay (up to 2hr)
  - Event-triggered boost: YOLO detects person enter/leave → heavy VLM for detailed analysis
  - Model swap coordination: when heavy VLM runs it evicts the brain LLM; a model-swap notification is always published on `hems/perception/vlm/model_swap`, and the brain falls back to rule-based mode during swap (~10-30s)
  - On-demand analysis via brain `describe_scene` tool
  - Publishes to `hems/perception/vlm/{zone}`, `hems/perception/vlm/status`, `hems/perception/vlm/model_swap`
- **Deploy**: Configure cameras in `HEMS_PERCEPTION_CAMERAS` env var (JSON array)
- **Profile**: `docker compose --profile perception up -d --build`
- **Startup with VLM**: `docker compose --profile perception --profile ollama up -d --build`
- **Brain integration**: WorldModel receives occupancy + activity + VLM scene data via MQTT, Rule Engine triggers sedentary alerts, sleep detection, and VLM anomaly alerts
- **Brain tools** (profile `perception`): `get_perception_status`, `describe_scene` (VLM on-demand), `list_scene_objects`, `get_scene_timeline`, `list_cameras`, `get_vlm_status`, `get_activity_history`
- **Privacy**: RAM-only processing, no image storage, person class only (no face recognition), all local
- **GPU**: Optional GPU acceleration (auto-detected by `gpu_setup.py`), CPU fallback

Configure in `.env`:
```bash
PERCEPTION_BRIDGE_URL=http://perception:8000
HEMS_PERCEPTION_CAMERAS=[{"device_id":"cam01","zone":"living_room","type":"mcp"}]
# HEMS_PERCEPTION_MODEL is defined in config.py but currently unused.
# VLM (requires --profile ollama)
VLM_ENABLED=false
VLM_LIGHT_MODEL=moondream
VLM_HEAVY_MODEL=minicpm-v
VLM_BASE_INTERVAL=1800
VLM_MAX_INTERVAL=7200
VLM_BOOST_DURATION=300
VLM_MAX_TOKENS=256
VLM_IMAGE_MAX_SIZE=512
```
