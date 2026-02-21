"""
HEMS Perception Service — Camera-based person detection + activity tracking.

Captures frames from MCP/stream cameras, runs YOLOv11s-pose inference,
classifies posture/activity, and publishes to MQTT for Brain consumption.
"""
import asyncio
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI
from loguru import logger

from config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS,
    CAMERAS, POSE_MODEL, CONFIDENCE_THRESHOLD,
    PROCESS_INTERVAL, LOG_LEVEL,
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

logger.remove()
logger.add(lambda msg: print(msg, end=""), level=LOG_LEVEL, format="{time:HH:mm:ss} | {level:<7} | {message}")


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

        except Exception as e:
            logger.error(f"Processing loop error: {e}")

        await asyncio.sleep(PROCESS_INTERVAL)


async def _bridge_status_loop():
    """Publish bridge status every 60 seconds."""
    while True:
        if mqtt_pub and camera_mgr:
            mqtt_pub.publish(
                "hems/perception/bridge/status",
                {
                    "connected": True,
                    "cameras": len(camera_mgr.cameras),
                    "cameras_active": camera_mgr.active_count,
                    "model_loaded": detector.loaded if detector else False,
                },
                retain=True,
            )
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_pub, detector, camera_mgr

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

    # Start processing loops
    _tasks.append(asyncio.create_task(_processing_loop()))
    _tasks.append(asyncio.create_task(_bridge_status_loop()))

    cam_count = len(camera_mgr.cameras)
    logger.info(f"Perception Service started (cameras={cam_count}, model={POSE_MODEL})")

    yield

    # Shutdown
    for t in _tasks:
        t.cancel()
    await camera_mgr.stop_all()
    if mqtt_pub:
        mqtt_pub.disconnect()
    logger.info("Perception Service stopped")


app = FastAPI(title="HEMS Perception", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": detector.loaded if detector else False,
        "cameras": len(camera_mgr.cameras) if camera_mgr else 0,
        "cameras_active": camera_mgr.active_count if camera_mgr else 0,
    }


@app.get("/api/perception/status")
async def perception_status():
    return {
        "model": POSE_MODEL,
        "confidence": CONFIDENCE_THRESHOLD,
        "interval": PROCESS_INTERVAL,
        "model_loaded": detector.loaded if detector else False,
        "cameras": len(camera_mgr.cameras) if camera_mgr else 0,
        "cameras_active": camera_mgr.active_count if camera_mgr else 0,
    }


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
