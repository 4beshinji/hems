"""
Vision/Perception Service
MQTT-based multi-task monitoring system with YOLOv11
"""
import asyncio
import json
import logging
import time
import yaml
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import components
from scheduler import TaskScheduler
from monitors import OccupancyMonitor, WhiteboardMonitor, ActivityMonitor
from image_requester import ImageRequester
from yolo_inference import YOLOInference
from pose_estimator import PoseEstimator
from state_publisher import StatePublisher
from camera_discovery import CameraDiscovery
from image_sources import ImageSourceFactory


async def main():
    logger.info("=== Vision Service Starting ===")

    # Load configuration
    config_path = Path(__file__).parent.parent / "config" / "monitors.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Initialize shared components (env vars override YAML config for Docker)
    mqtt_config = config.get("mqtt", {})
    broker = os.environ.get("MQTT_BROKER", mqtt_config.get("broker", "localhost"))
    port = int(os.environ.get("MQTT_PORT", mqtt_config.get("port", 1883)))

    logger.info(f"MQTT Broker: {broker}:{port}")

    # Initialize singletons
    ImageRequester.get_instance(broker, port)
    publisher = StatePublisher.get_instance(broker, port)

    # Load YOLO models
    yolo_config = config.get("yolo", {})
    model_path = yolo_config.get("model", "yolo11s.pt")
    pose_model_path = yolo_config.get("pose_model", "yolo11s-pose.pt")
    YOLOInference.get_instance(model_path)
    PoseEstimator.get_instance(pose_model_path)

    # Create scheduler
    scheduler = TaskScheduler()

    # Collect static camera IDs to avoid duplicates from discovery
    static_camera_ids = set()

    # Register static monitors from YAML
    for monitor_config in config.get("monitors", []):
        if not monitor_config.get("enabled", True):
            logger.info(f"Skipping disabled monitor: {monitor_config['name']}")
            continue

        monitor_type = monitor_config["type"]
        camera_id = monitor_config["camera_id"]
        zone_name = monitor_config.get("zone_name", "default")

        if monitor_type == "OccupancyMonitor":
            monitor = OccupancyMonitor(camera_id, zone_name)
        elif monitor_type == "WhiteboardMonitor":
            monitor = WhiteboardMonitor(camera_id, zone_name)
        elif monitor_type == "ActivityMonitor":
            monitor = ActivityMonitor(camera_id, zone_name)
        else:
            logger.warning(f"Unknown monitor type: {monitor_type}")
            continue

        scheduler.register_monitor(monitor_config["name"], monitor)
        static_camera_ids.add(camera_id)

    # --- Camera Auto-Discovery ---
    discovery_config = config.get("discovery", {})
    if discovery_config.get("enabled", False):
        logger.info("=== Camera Discovery Starting ===")
        discovery = CameraDiscovery(
            network=discovery_config.get("network", "192.168.128.0/24"),
            timeout=discovery_config.get("timeout", 3.0),
            verify_yolo=discovery_config.get("verify_yolo", True),
            exclude_ips=discovery_config.get("exclude_ips", []),
            zone_map=discovery_config.get("zone_map", {}),
        )

        cameras = await discovery.discover()
        default_interval = discovery_config.get("default_interval_sec", 10.0)

        discovery_results = []
        for cam in cameras:
            # Skip if static config already covers this camera
            if cam.camera_id in static_camera_ids:
                logger.info(f"[Discovery] Skipping {cam.camera_id} (static config exists)")
                continue

            source = ImageSourceFactory.create(cam)
            monitor = ActivityMonitor(
                camera_id=cam.camera_id,
                zone_name=cam.zone_name or cam.camera_id,
                image_source=source,
            )
            monitor.interval_sec = default_interval
            monitor_name = f"discovery_{cam.camera_id}"
            scheduler.register_monitor(monitor_name, monitor)

            discovery_results.append({
                "camera_id": cam.camera_id,
                "protocol": cam.protocol,
                "address": cam.address,
                "zone_name": cam.zone_name,
                "verified": cam.verified,
            })

        # Publish discovery results via MQTT
        await publisher.publish("office/perception/discovery", {
            "cameras": discovery_results,
            "total": len(discovery_results),
            "timestamp": time.time(),
        })
        logger.info(f"=== Discovery Complete: {len(discovery_results)} cameras added ===")

    logger.info("=== Vision Service Ready ===")

    # Start monitoring
    await scheduler.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
