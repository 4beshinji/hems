"""
Camera Discovery — network scan + URL probe + optional YOLO verification.
"""
import asyncio
import ipaddress
import logging
import time
from typing import Dict, List, Optional

import cv2
import numpy as np

from image_sources.base import CameraInfo

logger = logging.getLogger(__name__)

# Candidate URL patterns per port (ported from verify_cameras.py)
_CANDIDATE_URLS: List[str] = [
    "http://{ip}:81/",
    "http://{ip}:81/stream",
    "http://{ip}/stream",
    "http://{ip}:8080/?action=stream",
    "http://{ip}/webcam/?action=stream",
    "http://{ip}:8000/stream.mjpg",
]

# Ports to probe during the initial TCP scan
_SCAN_PORTS = [80, 81, 554, 8554]


class CameraDiscovery:
    """Three-stage camera discovery: port scan → URL probe → YOLO verify."""

    def __init__(
        self,
        network: str = "192.168.128.0/24",
        timeout: float = 3.0,
        verify_yolo: bool = True,
        exclude_ips: Optional[List[str]] = None,
        zone_map: Optional[Dict[str, str]] = None,
    ):
        self.network = ipaddress.ip_network(network, strict=False)
        self.timeout = timeout
        self.verify_yolo = verify_yolo
        self.exclude_ips = set(exclude_ips or [])
        self.zone_map = zone_map or {}

    async def discover(self) -> List[CameraInfo]:
        """Run full discovery pipeline. Returns list of discovered cameras."""
        logger.info(f"[Discovery] Scanning {self.network} ...")

        # Stage 1: async TCP port scan
        reachable = await self._port_scan()
        logger.info(f"[Discovery] Port scan found {len(reachable)} reachable hosts")

        # Stage 2: URL probe (blocking cv2 calls in executor)
        cameras = await self._url_probe(reachable)
        logger.info(f"[Discovery] URL probe found {len(cameras)} streams")

        # Stage 3: optional YOLO verification
        if self.verify_yolo and cameras:
            cameras = await self._yolo_verify(cameras)
            verified = sum(1 for c in cameras if c.verified)
            logger.info(f"[Discovery] YOLO verified {verified}/{len(cameras)} cameras")

        return cameras

    # ------------------------------------------------------------------
    # Stage 1: Async TCP port scan
    # ------------------------------------------------------------------
    async def _port_scan(self) -> Dict[str, List[int]]:
        """Return {ip: [open_ports]} for hosts with at least one open port."""
        sem = asyncio.Semaphore(128)
        results: Dict[str, List[int]] = {}
        lock = asyncio.Lock()

        async def _check(ip: str, port: int):
            async with sem:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port),
                        timeout=self.timeout,
                    )
                    writer.close()
                    await writer.wait_closed()
                    async with lock:
                        results.setdefault(ip, []).append(port)
                except (OSError, asyncio.TimeoutError):
                    pass

        tasks = []
        for host in self.network.hosts():
            ip = str(host)
            if ip in self.exclude_ips:
                continue
            for port in _SCAN_PORTS:
                tasks.append(_check(ip, port))

        await asyncio.gather(*tasks)
        return results

    # ------------------------------------------------------------------
    # Stage 2: URL probe with cv2.VideoCapture
    # ------------------------------------------------------------------
    async def _url_probe(self, reachable: Dict[str, List[int]]) -> List[CameraInfo]:
        loop = asyncio.get_event_loop()
        cameras: List[CameraInfo] = []

        async def _probe_ip(ip: str):
            result = await loop.run_in_executor(None, self._probe_ip_sync, ip)
            if result is not None:
                cameras.append(result)

        await asyncio.gather(*[_probe_ip(ip) for ip in reachable])
        return cameras

    def _probe_ip_sync(self, ip: str) -> Optional[CameraInfo]:
        """Try candidate URLs for a single IP, return CameraInfo on success."""
        for url_template in _CANDIDATE_URLS:
            url = url_template.format(ip=ip)
            try:
                cap = cv2.VideoCapture(url)
                if not cap.isOpened():
                    continue
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    camera_id = f"cam_{ip.replace('.', '_')}"
                    zone = self.zone_map.get(ip, "")
                    return CameraInfo(
                        camera_id=camera_id,
                        protocol="http_stream",
                        address=url,
                        zone_name=zone,
                        verified=False,
                        last_seen=time.time(),
                    )
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Stage 3: YOLO verification
    # ------------------------------------------------------------------
    async def _yolo_verify(self, cameras: List[CameraInfo]) -> List[CameraInfo]:
        loop = asyncio.get_event_loop()

        async def _verify(cam: CameraInfo):
            verified = await loop.run_in_executor(None, self._verify_sync, cam)
            cam.verified = verified

        await asyncio.gather(*[_verify(c) for c in cameras])
        return cameras

    def _verify_sync(self, cam: CameraInfo) -> bool:
        """Grab one frame and run YOLO — returns True if any object detected."""
        try:
            cap = cv2.VideoCapture(cam.address)
            if not cap.isOpened():
                return False
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return False

            from yolo_inference import YOLOInference

            yolo = YOLOInference.get_instance()
            detections = yolo.infer(frame, conf_threshold=0.4)
            if detections:
                logger.info(
                    f"[Discovery] {cam.camera_id} verified — "
                    f"detected: {[d['class'] for d in detections[:3]]}"
                )
            return len(detections) > 0
        except Exception as e:
            logger.warning(f"[Discovery] YOLO verify failed for {cam.camera_id}: {e}")
            return False
