"""
ImageSourceFactory — protocol string → ImageSource class registry.
"""
import logging
from typing import Dict, Type

from image_sources.base import CameraInfo, ImageSource
from image_sources.http_stream import HttpStreamSource
from image_sources.mqtt_source import MqttImageSource
from image_sources.rtsp_source import RtspSource

logger = logging.getLogger(__name__)


class ImageSourceFactory:
    """Maps protocol names to ImageSource implementations."""

    _registry: Dict[str, Type[ImageSource]] = {
        "http_stream": HttpStreamSource,
        "mqtt": MqttImageSource,
        "rtsp": RtspSource,
    }

    @classmethod
    def register(cls, protocol: str, source_cls: Type[ImageSource]):
        """Register a new protocol at runtime."""
        cls._registry[protocol] = source_cls
        logger.info(f"Registered image source protocol: {protocol}")

    @classmethod
    def create(cls, camera_info: CameraInfo) -> ImageSource:
        """Create an ImageSource for the given CameraInfo."""
        source_cls = cls._registry.get(camera_info.protocol)
        if source_cls is None:
            raise ValueError(
                f"Unknown protocol '{camera_info.protocol}'. "
                f"Registered: {list(cls._registry.keys())}"
            )
        return source_cls(camera_info)
