"""
Integration test: tiered buffer + posture stasis detection.

1. Discover cameras, filter for persons
2. Run pose estimation over multiple rounds
3. Show tiered buffer growth and posture analysis
"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import yaml
import numpy as np
from ultralytics import YOLO
from camera_discovery import CameraDiscovery
from image_sources import ImageSourceFactory
from pose_estimator import PoseEstimator
from activity_analyzer import ActivityAnalyzer

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logging.getLogger("ultralytics").setLevel(logging.WARNING)
logger = logging.getLogger("test_activity")

ROUNDS = 8
INTERVAL = 3.0


async def main():
    config_path = os.path.join(os.path.dirname(__file__), "config", "monitors.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    dc = config.get("discovery", {})

    # --- Discover ---
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

    # --- Load models ---
    detect_model = YOLO("yolo11s.pt")
    pose = PoseEstimator.get_instance("yolo11s-pose.pt")

    # --- Tier 1: Person scan ---
    logger.info("=" * 70)
    logger.info("TIER 1: Person detection")
    logger.info("=" * 70)

    person_cameras = []
    sources = {}

    for cam in sorted(cameras, key=lambda c: c.address):
        source = ImageSourceFactory.create(cam)
        sources[cam.camera_id] = (cam, source)
        frame = await source.capture()
        if frame is None:
            continue

        results = detect_model(frame, verbose=False, conf=0.5)
        person_count = sum(
            1 for r in results for box in r.boxes
            if detect_model.names[int(box.cls[0])] == "person"
        )

        ip = cam.address.split("//")[1].split(":")[0]
        zone = f" [{cam.zone_name}]" if cam.zone_name else ""
        if person_count > 0:
            logger.info(f"  {ip}{zone}: {person_count} person(s) -> POSE")
            person_cameras.append(cam)
        else:
            logger.info(f"  {ip}{zone}: skip")

    if not person_cameras:
        logger.info("No persons found.")
        for _, source in sources.values():
            await source.close()
        return

    # --- Tier 2: Pose + Activity over rounds ---
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"TIER 2: Pose estimation — {len(person_cameras)} cam(s), {ROUNDS} rounds x {INTERVAL}s")
    logger.info("=" * 70)

    analyzers = {}
    for cam in person_cameras:
        analyzers[cam.camera_id] = ActivityAnalyzer(frame_size=(800, 600))

    for rnd in range(1, ROUNDS + 1):
        logger.info(f"\n--- Round {rnd}/{ROUNDS} ---")
        for cam in person_cameras:
            _, source = sources[cam.camera_id]
            frame = await source.capture()
            if frame is None:
                continue

            h, w = frame.shape[:2]
            analyzer = analyzers[cam.camera_id]
            analyzer._diag = float(np.hypot(w, h))

            persons = pose.estimate(frame, conf_threshold=0.4)
            ip = cam.address.split("//")[1].split(":")[0]
            zone = f" [{cam.zone_name}]" if cam.zone_name else ""

            if persons:
                analyzer.push(persons)
                result = analyzer.analyze()
                depth = result["buffer_depth"]
                logger.info(
                    f"  {ip}{zone}: {len(persons)} person(s) | "
                    f"activity={result['activity_level']:.4f} ({result['activity_class']}) | "
                    f"posture={result['posture_status']} ({result['posture_duration_sec']:.0f}s) | "
                    f"buf=[raw:{depth['raw']} t1:{depth['tier1']} t2:{depth['tier2']} t3:{depth['tier3']}]"
                )
            else:
                logger.info(f"  {ip}{zone}: pose found 0 persons")

        if rnd < ROUNDS:
            await asyncio.sleep(INTERVAL)

    # --- Final summary ---
    logger.info("")
    logger.info("=" * 70)
    logger.info("FINAL ANALYSIS")
    logger.info("=" * 70)

    for cam in person_cameras:
        result = analyzers[cam.camera_id].analyze()
        ip = cam.address.split("//")[1].split(":")[0]
        zone = f" [{cam.zone_name}]" if cam.zone_name else ""
        depth = result["buffer_depth"]
        logger.info(
            f"  {ip}{zone}:\n"
            f"    activity_level:       {result['activity_level']:.4f} ({result['activity_class']})\n"
            f"    posture_duration_sec: {result['posture_duration_sec']:.1f}\n"
            f"    posture_status:       {result['posture_status']}\n"
            f"    buffer_depth:         raw={depth['raw']} t1={depth['tier1']} t2={depth['tier2']} t3={depth['tier3']}"
        )

    for _, source in sources.values():
        await source.close()
    logger.info("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
