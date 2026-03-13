"""
HEMS Perception Service — Camera-based person detection + activity tracking.

Captures frames from MCP/stream cameras, runs YOLOv11s-pose inference,
classifies posture/activity, and publishes to MQTT for Brain consumption.

Optional VLM (Vision Language Model) integration via Ollama for richer
scene understanding with adaptive frequency scheduling.
"""
import asyncio
import time

import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from loguru import logger
from typing import Optional

from config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS,
    CAMERAS, POSE_MODEL, CONFIDENCE_THRESHOLD,
    PROCESS_INTERVAL, LOG_LEVEL,
    VLM_ENABLED, VLM_OLLAMA_URL, VLM_LIGHT_MODEL, VLM_HEAVY_MODEL,
    VLM_BASE_INTERVAL, VLM_MIN_INTERVAL, VLM_MAX_INTERVAL,
    VLM_BOOST_DURATION, VLM_TIMEOUT, VLM_MAX_TOKENS, VLM_IMAGE_MAX_SIZE,
    LLM_MODEL,
)
from mqtt_publisher import MQTTPublisher
from detector import Detector
from activity_tracker import ActivityTracker
from camera_manager import CameraManager

# Module-level state
mqtt_pub: MQTTPublisher | None = None
detector: Detector | None = None
camera_mgr: CameraManager | None = None
trackers: dict[str, ActivityTracker] = {}
_tasks: list[asyncio.Task] = []

# VLM state (initialized only when VLM_ENABLED)
vlm_analyzer = None  # VLMAnalyzer | None
vlm_scheduler = None  # VLMScheduler | None
_vlm_session: aiohttp.ClientSession | None = None

# State tracking for YOLO event detection → VLM scheduler notification
_prev_state: dict[str, dict] = {}  # {cam_id: {person_count, posture, activity_level}}

logger.remove()
logger.add(lambda msg: print(msg, end=""), level=LOG_LEVEL, format="{time:HH:mm:ss} | {level:<7} | {message}")


def _detect_events(cam_id: str, zone: str, person_count: int,
                   posture: str, activity_level: float) -> None:
    """Compare current YOLO state with previous, notify VLM scheduler on changes."""
    if not vlm_scheduler:
        return

    prev = _prev_state.get(cam_id, {})

    # Person count changed (enter/leave)
    prev_count = prev.get("person_count", -1)
    if prev_count != -1 and prev_count != person_count:
        vlm_scheduler.notify_event("person_count_changed", {
            "zone": zone, "prev": prev_count, "current": person_count,
        })

    # Posture changed
    prev_posture = prev.get("posture", "unknown")
    if prev_posture != "unknown" and posture != "unknown" and prev_posture != posture:
        vlm_scheduler.notify_event("posture_changed", {
            "zone": zone, "prev": prev_posture, "current": posture,
        })

    # Activity spike (jump > 0.3)
    prev_activity = prev.get("activity_level", 0.0)
    if abs(activity_level - prev_activity) > 0.3:
        vlm_scheduler.notify_event("activity_spike", {
            "zone": zone, "prev": prev_activity, "current": activity_level,
        })

    _prev_state[cam_id] = {
        "person_count": person_count,
        "posture": posture,
        "activity_level": activity_level,
    }


async def _processing_loop():
    """Main capture → detect → track → publish loop."""
    while True:
        try:
            if camera_mgr and detector and detector.loaded and mqtt_pub:
                frames = await camera_mgr.capture_all()

                for cam_id, frame in frames.items():
                    cam = camera_mgr.cameras.get(cam_id)
                    if not cam:
                        continue

                    zone = cam.zone

                    # Detect persons + keypoints
                    result = detector.detect(frame)

                    # Publish occupancy — 5-part topic: office/{zone}/camera/{cam_id}/status
                    mqtt_pub.publish(
                        f"office/{zone}/camera/{cam_id}/status",
                        {"person_count": result.person_count},
                    )

                    # Update activity tracker (use primary detection keypoints)
                    if cam_id not in trackers:
                        trackers[cam_id] = ActivityTracker()

                    tracker = trackers[cam_id]
                    primary_kps = None
                    if result.detections:
                        primary_kps = result.detections[0].keypoints

                    state = tracker.update(primary_kps, result.timestamp)

                    # Publish activity — 4-part topic: office/{zone}/activity/{cam_id}
                    mqtt_pub.publish(
                        f"office/{zone}/activity/{cam_id}",
                        {
                            "activity_level": state.activity_level,
                            "activity_class": state.activity_class,
                            "posture": state.posture,
                            "posture_duration_sec": state.posture_duration_sec,
                            "posture_status": state.posture_status,
                        },
                    )

                    # Notify VLM scheduler of state changes
                    _detect_events(
                        cam_id, zone, result.person_count,
                        state.posture, state.activity_level,
                    )

        except Exception as e:
            logger.error(f"Processing loop error: {e}")

        await asyncio.sleep(PROCESS_INTERVAL)


async def _vlm_processing_loop():
    """VLM analysis loop — runs at adaptive intervals set by scheduler."""
    global _vlm_session

    # Wait for camera manager and detector to be ready
    while not (camera_mgr and detector and detector.loaded and mqtt_pub):
        await asyncio.sleep(5)

    logger.info(
        f"VLM loop started (light={VLM_LIGHT_MODEL}, heavy={VLM_HEAVY_MODEL}, "
        f"interval={VLM_BASE_INTERVAL}s)"
    )

    _vlm_session = aiohttp.ClientSession()

    try:
        while True:
            try:
                if vlm_scheduler and vlm_scheduler.should_run_now():
                    await _run_vlm_cycle()
            except Exception as e:
                logger.error(f"VLM loop error: {e}")

            await asyncio.sleep(5)  # Check scheduler every 5s
    finally:
        if _vlm_session:
            await _vlm_session.close()
            _vlm_session = None


async def _run_vlm_cycle():
    """Execute one VLM analysis cycle."""
    if not (vlm_analyzer and vlm_scheduler and camera_mgr and mqtt_pub and _vlm_session):
        return

    # Check for on-demand request
    on_demand = vlm_scheduler.pop_on_demand()
    tier = vlm_scheduler.current_tier

    # Determine target zone/prompt
    target_zone = on_demand.zone if on_demand else ""
    custom_prompt = on_demand.prompt if on_demand else ""

    # Heavy tier: signal brain to enter rule-only mode
    is_heavy = tier == "heavy"
    if is_heavy:
        mqtt_pub.publish("hems/perception/vlm/model_swap", {
            "status": "heavy_loading",
            "model": vlm_analyzer.heavy_model,
        })
        logger.info(f"VLM heavy tier: model_swap signal sent (model={vlm_analyzer.heavy_model})")

    try:
        # Capture frames from cameras
        frames = await camera_mgr.capture_all()
        if not frames:
            vlm_scheduler.record_run(interesting=False)
            return

        any_interesting = False

        for cam_id, frame in frames.items():
            cam = camera_mgr.cameras.get(cam_id)
            if not cam:
                continue

            zone = cam.zone

            # Filter by target zone if on-demand specifies one
            if target_zone and zone != target_zone:
                continue

            result = await vlm_analyzer.analyze(
                frame=frame,
                session=_vlm_session,
                prompt=custom_prompt or None,
                mode="general",
                tier=tier,
                zone=zone,
            )

            if result.get("error"):
                logger.warning(f"VLM analysis error ({zone}): {result['error']}")
                continue

            # Publish result
            mqtt_pub.publish(f"hems/perception/vlm/{zone}", result)

            # Check if result was interesting (has anomalies or objects)
            if result.get("anomalies") or result.get("objects"):
                any_interesting = True

            logger.info(
                f"VLM [{tier}] {zone}: {result.get('description', '')[:80]}... "
                f"({result.get('elapsed_ms', 0)}ms)"
            )

        vlm_scheduler.record_run(interesting=any_interesting)

    finally:
        # Heavy tier: unload model and signal brain to resume
        if is_heavy:
            await vlm_analyzer._unload_model(vlm_analyzer.heavy_model, _vlm_session)
            mqtt_pub.publish("hems/perception/vlm/model_swap", {
                "status": "ready",
                "model": vlm_analyzer.heavy_model,
            })
            logger.info("VLM heavy tier: model unloaded, model_swap ready signal sent")

    # Publish scheduler status (retained)
    _publish_vlm_status()


def _publish_vlm_status():
    """Publish current VLM scheduler status to MQTT."""
    if not (vlm_scheduler and mqtt_pub):
        return
    status = vlm_scheduler.get_status()
    status.update({
        "enabled": True,
        "light_model": VLM_LIGHT_MODEL,
        "heavy_model": VLM_HEAVY_MODEL,
    })
    mqtt_pub.publish("hems/perception/vlm/status", status, retain=True)


async def _bridge_status_loop():
    """Publish bridge status every 60 seconds."""
    while True:
        if mqtt_pub and camera_mgr:
            status = {
                "connected": True,
                "cameras": len(camera_mgr.cameras),
                "cameras_active": camera_mgr.active_count,
                "model_loaded": detector.loaded if detector else False,
            }
            if VLM_ENABLED:
                status["vlm_enabled"] = True
                status["vlm_mode"] = vlm_scheduler.mode if vlm_scheduler else "disabled"
            mqtt_pub.publish(
                "hems/perception/bridge/status",
                status,
                retain=True,
            )
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_pub, detector, camera_mgr, vlm_analyzer, vlm_scheduler

    # MQTT
    mqtt_pub = MQTTPublisher(MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
    try:
        mqtt_pub.connect()
    except Exception as e:
        logger.error(f"MQTT connect failed: {e}")
        mqtt_pub = None

    # Camera manager
    camera_mgr = CameraManager(mqtt_pub)
    if mqtt_pub:
        mqtt_pub.set_message_callback(camera_mgr.handle_mqtt_message)

    for cam_cfg in CAMERAS:
        camera_mgr.add_camera(cam_cfg)

    await camera_mgr.start_all()

    # Detector (load models in background to not block startup)
    detector = Detector(
        pose_model_name=POSE_MODEL,
        confidence=CONFIDENCE_THRESHOLD,
    )

    async def _load_models():
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, detector.load_models)

    _tasks.append(asyncio.create_task(_load_models()))

    # VLM initialization (only when enabled)
    if VLM_ENABLED:
        from vlm_analyzer import VLMAnalyzer
        from vlm_scheduler import VLMScheduler

        vlm_analyzer = VLMAnalyzer(
            ollama_url=VLM_OLLAMA_URL,
            light_model=VLM_LIGHT_MODEL,
            heavy_model=VLM_HEAVY_MODEL,
            timeout=VLM_TIMEOUT,
            max_tokens=VLM_MAX_TOKENS,
            max_image_size=VLM_IMAGE_MAX_SIZE,
        )
        vlm_scheduler = VLMScheduler(
            base_interval=VLM_BASE_INTERVAL,
            min_interval=VLM_MIN_INTERVAL,
            max_interval=VLM_MAX_INTERVAL,
            boost_duration=VLM_BOOST_DURATION,
        )
        _tasks.append(asyncio.create_task(_vlm_processing_loop()))
        logger.info(
            f"VLM enabled (light={VLM_LIGHT_MODEL}, heavy={VLM_HEAVY_MODEL}, "
            f"ollama={VLM_OLLAMA_URL})"
        )
    else:
        logger.info("VLM disabled (VLM_ENABLED=false)")

    # Start processing loops
    _tasks.append(asyncio.create_task(_processing_loop()))
    _tasks.append(asyncio.create_task(_bridge_status_loop()))

    cam_count = len(camera_mgr.cameras)
    logger.info(f"Perception Service started (cameras={cam_count}, model={POSE_MODEL})")

    yield

    # Shutdown
    for t in _tasks:
        t.cancel()
    if _vlm_session:
        await _vlm_session.close()
    await camera_mgr.stop_all()
    if mqtt_pub:
        mqtt_pub.disconnect()
    logger.info("Perception Service stopped")


app = FastAPI(title="HEMS Perception", lifespan=lifespan)


# --- REST Endpoints ---


@app.get("/health")
async def health():
    result = {
        "status": "ok",
        "model_loaded": detector.loaded if detector else False,
        "cameras": len(camera_mgr.cameras) if camera_mgr else 0,
        "cameras_active": camera_mgr.active_count if camera_mgr else 0,
    }
    if VLM_ENABLED:
        result["vlm_enabled"] = True
        result["vlm_mode"] = vlm_scheduler.mode if vlm_scheduler else "disabled"
    return result


@app.get("/api/perception/status")
async def perception_status():
    result = {
        "model": POSE_MODEL,
        "confidence": CONFIDENCE_THRESHOLD,
        "interval": PROCESS_INTERVAL,
        "model_loaded": detector.loaded if detector else False,
        "cameras": len(camera_mgr.cameras) if camera_mgr else 0,
        "cameras_active": camera_mgr.active_count if camera_mgr else 0,
    }
    if VLM_ENABLED and vlm_scheduler:
        result["vlm"] = vlm_scheduler.get_status()
        result["vlm"]["light_model"] = VLM_LIGHT_MODEL
        result["vlm"]["heavy_model"] = VLM_HEAVY_MODEL
    return result


@app.get("/api/perception/cameras")
async def list_cameras():
    if not camera_mgr:
        return {"cameras": []}
    return {
        "cameras": [
            {
                "camera_id": cam_id,
                "zone": cam.zone,
                "type": type(cam).__name__,
                "connected": cam.connected,
            }
            for cam_id, cam in camera_mgr.cameras.items()
        ]
    }


# --- VLM Endpoints ---


class VLMAnalyzeRequest(BaseModel):
    zone_id: Optional[str] = None
    prompt: Optional[str] = None


@app.post("/api/perception/vlm/analyze")
async def vlm_analyze(req: VLMAnalyzeRequest):
    """On-demand VLM analysis (called by brain describe_scene tool). Uses heavy tier."""
    if not VLM_ENABLED or not vlm_scheduler or not vlm_analyzer:
        return {"error": "VLM not enabled", "status": "disabled"}

    request_id = vlm_scheduler.request_on_demand(
        zone=req.zone_id or "",
        prompt=req.prompt or "",
    )

    # Wait for the analysis to complete (max VLM_TIMEOUT + buffer)
    deadline = time.time() + VLM_TIMEOUT + 10
    while time.time() < deadline:
        # The VLM loop will process the on-demand request
        # Check if it's been processed by looking at scheduler state
        if vlm_scheduler._last_run > time.time() - 5 and not vlm_scheduler._on_demand_queue:
            break
        await asyncio.sleep(1)

    return {
        "request_id": request_id,
        "status": "completed" if not vlm_scheduler._on_demand_queue else "pending",
        "scheduler": vlm_scheduler.get_status(),
    }


@app.get("/api/perception/vlm/status")
async def vlm_status():
    """Get VLM scheduler status."""
    if not VLM_ENABLED or not vlm_scheduler:
        return {"enabled": False}

    status = vlm_scheduler.get_status()
    status.update({
        "enabled": True,
        "light_model": VLM_LIGHT_MODEL,
        "heavy_model": VLM_HEAVY_MODEL,
        "ollama_url": VLM_OLLAMA_URL,
    })
    return status
