"""
Integration test: Camera Discovery → ImageSource → Capture
Run from host (not Docker) to verify LAN camera access.
"""
import asyncio
import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import yaml
from camera_discovery import CameraDiscovery
from image_sources import ImageSourceFactory, CameraInfo
import cv2
import numpy as np

# Logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_discovery")


async def test_discovery():
    """Test Phase 1: Camera auto-discovery on the LAN."""
    config_path = os.path.join(os.path.dirname(__file__), "config", "monitors.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    dc = config.get("discovery", {})
    discovery = CameraDiscovery(
        network=dc.get("network", "192.168.128.0/24"),
        timeout=dc.get("timeout", 3.0),
        verify_yolo=False,  # Skip YOLO for speed — test separately
        exclude_ips=dc.get("exclude_ips", []),
        zone_map=dc.get("zone_map", {}),
    )

    logger.info("=" * 60)
    logger.info("STAGE 1: Running camera discovery (no YOLO)...")
    logger.info("=" * 60)

    t0 = time.time()
    cameras = await discovery.discover()
    elapsed = time.time() - t0

    logger.info(f"Discovery completed in {elapsed:.1f}s — found {len(cameras)} camera(s)")
    for cam in cameras:
        logger.info(f"  {cam.camera_id} | {cam.protocol} | {cam.address} | zone={cam.zone_name}")

    return cameras


async def test_image_source(cameras: list):
    """Test Phase 2: ImageSourceFactory → capture a frame from each camera."""
    logger.info("=" * 60)
    logger.info("STAGE 2: Testing ImageSource capture...")
    logger.info("=" * 60)

    results = []
    for cam in cameras:
        source = ImageSourceFactory.create(cam)
        try:
            t0 = time.time()
            frame = await source.capture()
            elapsed = time.time() - t0

            if frame is not None:
                h, w = frame.shape[:2]
                logger.info(f"  OK  {cam.camera_id} — {w}x{h} in {elapsed:.2f}s")
                results.append((cam, frame))
            else:
                logger.warning(f"  FAIL {cam.camera_id} — capture returned None ({elapsed:.2f}s)")
        except Exception as e:
            logger.error(f"  ERR  {cam.camera_id} — {e}")
        finally:
            await source.close()

    return results


async def test_health_check(cameras: list):
    """Test Phase 3: health_check on each source."""
    logger.info("=" * 60)
    logger.info("STAGE 3: Testing health_check...")
    logger.info("=" * 60)

    for cam in cameras:
        source = ImageSourceFactory.create(cam)
        try:
            healthy = await source.health_check()
            status = "HEALTHY" if healthy else "UNHEALTHY"
            logger.info(f"  {status}  {cam.camera_id}")
        except Exception as e:
            logger.error(f"  ERR     {cam.camera_id} — {e}")
        finally:
            await source.close()


async def test_yolo_verify(cameras: list):
    """Test Phase 4: YOLO verification on discovered cameras."""
    logger.info("=" * 60)
    logger.info("STAGE 4: YOLO verification...")
    logger.info("=" * 60)

    try:
        from yolo_inference import YOLOInference
        yolo = YOLOInference.get_instance("yolov11s.pt")
    except Exception as e:
        logger.warning(f"YOLO init failed (expected if no GPU/model): {e}")
        logger.info("Skipping YOLO verification")
        return

    for cam in cameras:
        source = ImageSourceFactory.create(cam)
        try:
            frame = await source.capture()
            if frame is None:
                logger.warning(f"  SKIP  {cam.camera_id} — no frame")
                continue
            detections = yolo.infer(frame, conf_threshold=0.4)
            if detections:
                names = [d["class"] for d in detections[:5]]
                logger.info(f"  VERIFIED  {cam.camera_id} — {names}")
            else:
                logger.info(f"  NO OBJECTS  {cam.camera_id}")
        except Exception as e:
            logger.error(f"  ERR  {cam.camera_id} — {e}")
        finally:
            await source.close()


async def main():
    logger.info("=== Camera Discovery Integration Test ===")
    logger.info(f"Host IP: 192.168.128.74")

    # Stage 1: Discovery
    cameras = await test_discovery()
    if not cameras:
        logger.error("No cameras found! Check network connectivity.")
        return

    # Stage 2: ImageSource capture
    results = await test_image_source(cameras)

    # Stage 3: Health check
    await test_health_check(cameras)

    # Stage 4: YOLO (optional)
    await test_yolo_verify(cameras)

    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Cameras discovered: {len(cameras)}")
    logger.info(f"Frames captured:    {len(results)}")
    for cam, frame in results:
        h, w = frame.shape[:2]
        logger.info(f"  {cam.camera_id}: {w}x{h} zone={cam.zone_name or '(none)'}")

    logger.info("=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
