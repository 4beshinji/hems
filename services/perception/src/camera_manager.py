"""
Camera source management — MCP (ESP32 MQTT) and Stream (RTSP/HTTP) cameras.
"""
import asyncio
import base64
import time
import uuid
from abc import ABC, abstractmethod

import cv2
import numpy as np
from loguru import logger

from mqtt_publisher import MQTTPublisher


class CameraSource(ABC):
    """Base class for camera sources."""

    def __init__(self, camera_id: str, zone: str):
        self.camera_id = camera_id
        self.zone = zone
        self.connected = False

    @abstractmethod
    async def capture(self) -> np.ndarray | None:
        """Capture a single frame. Returns None on failure."""

    async def start(self):
        """Initialize camera connection."""

    async def stop(self):
        """Clean up camera resources."""


class MCPCamera(CameraSource):
    """ESP32 MCP/MQTT camera — request/response via MQTT topics."""

    def __init__(self, camera_id: str, zone: str, mqtt_pub: MQTTPublisher,
                 timeout: float = 10.0):
        super().__init__(camera_id, zone)
        self._mqtt = mqtt_pub
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}

    async def start(self):
        self._mqtt.subscribe(f"mcp/{self.camera_id}/response/#")
        self.connected = True
        logger.info(f"MCP camera {self.camera_id} ready (zone={self.zone})")

    def handle_response(self, topic: str, payload: dict):
        """Route MCP response to waiting future."""
        # topic: mcp/{device_id}/response/{req_id}
        parts = topic.split("/")
        if len(parts) >= 4:
            req_id = parts[3]
            fut = self._pending.pop(req_id, None)
            if fut and not fut.done():
                fut.set_result(payload)

    async def capture(self) -> np.ndarray | None:
        req_id = str(uuid.uuid4())[:8]
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[req_id] = fut

        # Send capture request
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "call_tool",
            "params": {
                "name": "capture",
                "arguments": {"resolution": "VGA"},
            },
        }
        self._mqtt.publish(f"mcp/{self.camera_id}/request/call_tool", request)

        try:
            response = await asyncio.wait_for(fut, timeout=self._timeout)
            return self._decode_image(response)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            logger.warning(f"MCP camera {self.camera_id} capture timeout")
            return None
        except Exception as e:
            self._pending.pop(req_id, None)
            logger.error(f"MCP camera {self.camera_id} capture error: {e}")
            return None

    def _decode_image(self, response: dict) -> np.ndarray | None:
        """Decode base64 image from MCP response."""
        image_b64 = response.get("image")
        if not image_b64:
            # Try nested result structure
            result = response.get("result", {})
            if isinstance(result, dict):
                image_b64 = result.get("image")
            if not image_b64:
                return None

        try:
            img_bytes = base64.b64decode(image_b64)
            img_array = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return frame
        except Exception as e:
            logger.error(f"Image decode error: {e}")
            return None

    async def stop(self):
        self.connected = False
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()


class StreamCamera(CameraSource):
    """RTSP/HTTP stream camera — cv2.VideoCapture based."""

    def __init__(self, camera_id: str, zone: str, url: str):
        super().__init__(camera_id, zone)
        self.url = url
        self._cap: cv2.VideoCapture | None = None

    async def start(self):
        loop = asyncio.get_event_loop()
        try:
            self._cap = await loop.run_in_executor(
                None, lambda: cv2.VideoCapture(self.url)
            )
            self.connected = self._cap.isOpened()
            if self.connected:
                logger.info(f"Stream camera {self.camera_id} connected (zone={self.zone})")
            else:
                logger.warning(f"Stream camera {self.camera_id} failed to connect: {self.url}")
        except Exception as e:
            logger.error(f"Stream camera {self.camera_id} error: {e}")
            self.connected = False

    async def capture(self) -> np.ndarray | None:
        if self._cap is None or not self._cap.isOpened():
            self.connected = False
            return None

        loop = asyncio.get_event_loop()
        try:
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if ret:
                self.connected = True
                return frame
            else:
                self.connected = False
                return None
        except Exception as e:
            logger.error(f"Stream camera {self.camera_id} read error: {e}")
            self.connected = False
            return None

    async def stop(self):
        if self._cap:
            self._cap.release()
            self._cap = None
        self.connected = False


class CameraManager:
    """Manages multiple camera sources."""

    def __init__(self, mqtt_pub: MQTTPublisher | None = None):
        self.cameras: dict[str, CameraSource] = {}
        self._mqtt = mqtt_pub

    def add_camera(self, config: dict):
        """Add camera from config dict."""
        cam_id = config.get("device_id", "")
        zone = config.get("zone", "default")
        cam_type = config.get("type", "stream")

        if not cam_id:
            logger.warning(f"Camera config missing device_id: {config}")
            return

        if cam_type == "mcp":
            if self._mqtt is None:
                logger.warning(f"Cannot create MCP camera {cam_id}: no MQTT publisher")
                return
            cam = MCPCamera(cam_id, zone, self._mqtt)
        elif cam_type in ("stream", "rtsp", "http"):
            url = config.get("url", "")
            if not url:
                logger.warning(f"Stream camera {cam_id} missing url")
                return
            cam = StreamCamera(cam_id, zone, url)
        else:
            logger.warning(f"Unknown camera type: {cam_type}")
            return

        self.cameras[cam_id] = cam
        logger.info(f"Added camera: {cam_id} (type={cam_type}, zone={zone})")

    def handle_mqtt_message(self, topic: str, payload: dict):
        """Route MQTT messages to MCP cameras."""
        for cam in self.cameras.values():
            if isinstance(cam, MCPCamera) and topic.startswith(f"mcp/{cam.camera_id}/"):
                cam.handle_response(topic, payload)

    async def start_all(self):
        """Start all cameras."""
        for cam in self.cameras.values():
            await cam.start()

    async def capture_all(self) -> dict[str, np.ndarray]:
        """Capture from all connected cameras."""
        results = {}
        tasks = {}

        for cam_id, cam in self.cameras.items():
            if cam.connected:
                tasks[cam_id] = asyncio.create_task(cam.capture())

        for cam_id, task in tasks.items():
            try:
                frame = await task
                if frame is not None:
                    results[cam_id] = frame
            except Exception as e:
                logger.error(f"Capture failed for {cam_id}: {e}")

        return results

    async def stop_all(self):
        """Stop all cameras."""
        for cam in self.cameras.values():
            await cam.stop()

    @property
    def active_count(self) -> int:
        return sum(1 for cam in self.cameras.values() if cam.connected)
