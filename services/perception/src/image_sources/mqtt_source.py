"""
MqttImageSource — wraps the existing ImageRequester singleton.
"""
import logging
from typing import Optional

import numpy as np

from image_sources.base import CameraInfo, ImageSource

logger = logging.getLogger(__name__)


class MqttImageSource(ImageSource):
    """Captures frames via MQTT request/response (legacy ESP32 protocol)."""

    def __init__(
        self,
        camera_info: CameraInfo,
        resolution: str = "VGA",
        quality: int = 10,
    ):
        super().__init__(camera_info)
        self.resolution = resolution
        self.quality = quality

    async def capture(self) -> Optional[np.ndarray]:
        from image_requester import ImageRequester

        requester = ImageRequester.get_instance()
        return await requester.request(
            self.camera_info.camera_id,
            self.resolution,
            self.quality,
        )

    async def health_check(self) -> bool:
        frame = await self.capture()
        return frame is not None
