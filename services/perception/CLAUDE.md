# services/perception/

Camera-based person detection + posture/activity tracking + optional VLM scene analysis. Extends parent `hems/CLAUDE.md`.

## Perception (Camera Detection + Activity Tracking + VLM Scene Analysis)

Camera-based person detection and posture/activity tracking using RTMO
(MMPose, Apache-2.0) run via rtmlib on ONNX Runtime — no torch — with optional
VLM (Vision Language Model) integration via Ollama for scene understanding.

- **perception**: Docker service with RTMO pose inference pipeline (rtmlib/ONNX)
  - Captures frames from MCP (ESP32 MQTT) or stream (RTSP/HTTP) cameras
  - Single-pass person detection + skeleton keypoint extraction
  - Posture classification (standing/sitting/lying/walking) from COCO 17 keypoints
  - Activity level (0.0-1.0) with EMA smoothing + tiered pose buffer
  - Publishes to `hems/sensors/{zone}/camera/{cam_id}/status` and `hems/sensors/{zone}/activity/{cam_id}`
- **VLM integration** (optional, requires `--profile ollama` + `VLM_ENABLED=true`):
  - Default strategy A — single-model unification: both light & heavy tiers reuse the chat brain (`gemma4:e4b-it-q8_0`, vision+thinking-capable). Saves a model swap and ~3 GB of VRAM. `vlm_analyzer` sends `think: false` so Gemma's thinking trace doesn't eat the response budget.
  - Strategy B (separate small VLMs) still supported by overriding `VLM_LIGHT_MODEL` / `VLM_HEAVY_MODEL` (e.g. `moondream` / `minicpm-v`).
  - Adaptive frequency: 30min routine → event-boosted (1-5min) → quiet decay (up to 2hr)
  - Event-triggered boost: RTMO detects person enter/leave → heavy VLM for detailed analysis
  - Model swap coordination (only relevant under strategy B with a different heavy model): heavy VLM evicts brain LLM; brain falls back to rule-based mode during swap (~10-30s)
  - On-demand analysis via brain `describe_scene` tool
  - Publishes to `hems/perception/vlm/{zone}`, `hems/perception/vlm/status`, `hems/perception/vlm/model_swap`
- **Deploy**: Configure cameras in `HEMS_PERCEPTION_CAMERAS` env var (JSON array)
- **Profile**: `docker compose --profile perception up -d --build`
- **Model cache**: The RTMO weights are baked into `/app/.cache/rtmlib`; Compose mounts the persistent cache at `/app/.cache`
- **Brain integration**: WorldModel receives occupancy + activity + VLM scene data via MQTT, Rule Engine triggers sedentary alerts, sleep detection, and VLM anomaly alerts
- **Brain tools** (profile `perception`): `get_perception_status`, `describe_scene` (VLM on-demand), `list_scene_objects`, `get_scene_timeline`, `list_cameras`, `get_vlm_status`, `get_activity_history`
- **Privacy**: RAM-only processing, no image storage, person class only (no face recognition), all local
- **GPU**: RTMO runs on the onnxruntime **CPU EP by default** (perception's 5s cadence makes CPU sufficient; GPU load belongs to the VLM/Ollama path). GPU ONNX EPs (CUDA/ROCm) are an advanced opt-in, not wired. `HEMS_PERCEPTION_DEVICE=cpu|cuda`.
- **License**: RTMO + rtmlib + bundled ONNX weights are all Apache-2.0 (replaced the former AGPL ultralytics backend). Attribution in `services/perception/NOTICE`.

Configure in `.env`:
```bash
PERCEPTION_BRIDGE_URL=http://perception:8000
HEMS_PERCEPTION_CAMERAS=[{"device_id":"cam01","zone":"living_room","type":"mcp"}]
# VLM (requires --profile ollama)
VLM_ENABLED=true
# Strategy A (default): reuse chat brain — no extra pull, no swap.
# VLM_LIGHT_MODEL=gemma4:e4b-it-q8_0
# VLM_HEAVY_MODEL=gemma4:e4b-it-q8_0
# Strategy B: separate small VLMs (uncomment and pull via `ollama pull`).
# VLM_LIGHT_MODEL=moondream
# VLM_HEAVY_MODEL=minicpm-v
```
