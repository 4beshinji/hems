"""
RtspSource — IP camera / virtual camera via RTSP.
Structurally identical to HttpStreamSource (cv2 handles rtsp:// natively).
"""
import asyncio
import logging
import time
from typing import Optional

import cv2
import numpy as np

from image_sources.base import CameraInfo, ImageSource

logger = logging.getLogger(__name__)


class RtspSource(ImageSource):
    """Captures frames from an RTSP stream."""

    def __init__(self, camera_info: CameraInfo):
        super().__init__(camera_info)
        self._cap: Optional[cv2.VideoCapture] = None

    def _open(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True
        self._cap = cv2.VideoCapture(self.camera_info.address)
        if not self._cap.isOpened():
            logger.warning(
                f"[RTSP] Failed to open {self.camera_info.address}"
            )
            self._cap = None
            return False
        return True

    async def capture(self) -> Optional[np.ndarray]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._capture_sync)

    def _capture_sync(self) -> Optional[np.ndarray]:
        if not self._open():
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning(
                f"[RTSP] Read failed for {self.camera_info.camera_id}, reconnecting"
            )
            self._release()
            return None
        self.camera_info.last_seen = time.time()
        return frame

    async def health_check(self) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._health_sync)

    def _health_sync(self) -> bool:
        if not self._open():
            return False
        ret, _ = self._cap.read()
        return ret

    def _release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    async def close(self):
        self._release()
