"""
YOLO object detection on all discovered LAN cameras.
"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import yaml
import cv2
import numpy as np
from ultralytics import YOLO
from camera_discovery import CameraDiscovery
from image_sources import ImageSourceFactory

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
# Suppress noisy ultralytics logs
logging.getLogger("ultralytics").setLevel(logging.WARNING)
logger = logging.getLogger("yolo_detect")


async def main():
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), "config", "monitors.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    dc = config.get("discovery", {})

    # --- Discover cameras ---
    logger.info("Discovering cameras...")
    discovery = CameraDiscovery(
        network=dc.get("network", "192.168.128.0/24"),
        timeout=dc.get("timeout", 3.0),
        verify_yolo=False,
        exclude_ips=dc.get("exclude_ips", []),
        zone_map=dc.get("zone_map", {}),
    )
    cameras = await discovery.discover()
    logger.info(f"Found {len(cameras)} cameras")

    if not cameras:
        logger.error("No cameras found!")
        return

    # --- Load YOLO ---
    logger.info("Loading YOLO11s model...")
    model = YOLO("yolo11s.pt")

    # --- Detect on each camera ---
    logger.info("=" * 70)
    logger.info("Running object detection on each camera...")
    logger.info("=" * 70)

    detected_cameras = []
    empty_cameras = []

    for cam in sorted(cameras, key=lambda c: c.address):
        source = ImageSourceFactory.create(cam)
        try:
            frame = await source.capture()
            if frame is None:
                logger.warning(f"  {cam.camera_id}: CAPTURE FAILED")
                continue

            # Run YOLO
            results = model(frame, verbose=False, conf=0.4)
            detections = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    name = model.names[cls_id]
                    detections.append((name, conf))

            zone_label = f" [{cam.zone_name}]" if cam.zone_name else ""
            ip = cam.address.split("//")[1].split(":")[0]

            if detections:
                det_str = ", ".join(f"{n} ({c:.0%})" for n, c in detections)
                logger.info(f"  {ip}{zone_label}: {det_str}")
                detected_cameras.append((cam, detections))
            else:
                logger.info(f"  {ip}{zone_label}: (nothing detected)")
                empty_cameras.append(cam)

        finally:
            await source.close()

    # --- Summary ---
    logger.info("")
    logger.info("=" * 70)
    logger.info("RESULTS")
    logger.info("=" * 70)
    logger.info(f"Cameras with objects: {len(detected_cameras)}/{len(cameras)}")
    logger.info(f"Cameras empty:        {len(empty_cameras)}/{len(cameras)}")
    logger.info("")

    if detected_cameras:
        logger.info("--- Cameras with detected objects ---")
        for cam, dets in detected_cameras:
            zone_label = f" [{cam.zone_name}]" if cam.zone_name else ""
            ip = cam.address.split("//")[1].split(":")[0]
            # Aggregate by class
            counts = {}
            for name, conf in dets:
                if name not in counts:
                    counts[name] = {"count": 0, "max_conf": 0.0}
                counts[name]["count"] += 1
                counts[name]["max_conf"] = max(counts[name]["max_conf"], conf)
            summary = ", ".join(
                f"{name} x{info['count']} ({info['max_conf']:.0%})"
                for name, info in sorted(counts.items(), key=lambda x: -x[1]["max_conf"])
            )
            logger.info(f"  {ip}{zone_label}: {summary}")

    if empty_cameras:
        logger.info("")
        logger.info("--- Cameras with no objects ---")
        for cam in empty_cameras:
            zone_label = f" [{cam.zone_name}]" if cam.zone_name else ""
            ip = cam.address.split("//")[1].split(":")[0]
            logger.info(f"  {ip}{zone_label}")


if __name__ == "__main__":
    asyncio.run(main())
