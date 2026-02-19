"""
ImageSource ABC and CameraInfo dataclass
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time
import numpy as np


@dataclass
class CameraInfo:
    camera_id: str          # "cam_192_168_128_172"
    protocol: str           # "http_stream", "mqtt", "rtsp"
    address: str            # "http://192.168.128.172:81/"
    zone_name: str = ""
    verified: bool = False
    last_seen: float = field(default_factory=time.time)


class ImageSource(ABC):
    """Abstract base for all image capture backends."""

    def __init__(self, camera_info: CameraInfo):
        self.camera_info = camera_info

    @abstractmethod
    async def capture(self) -> Optional[np.ndarray]:
        """Capture a single frame. Returns BGR ndarray or None on failure."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the source is reachable."""

    async def close(self):
        """Release resources (override if needed)."""
