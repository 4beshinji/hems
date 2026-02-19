"""
image_sources package — pluggable camera backends.
"""
from image_sources.base import CameraInfo, ImageSource
from image_sources.http_stream import HttpStreamSource
from image_sources.mqtt_source import MqttImageSource
from image_sources.rtsp_source import RtspSource
from image_sources.factory import ImageSourceFactory

__all__ = [
    "CameraInfo",
    "ImageSource",
    "HttpStreamSource",
    "MqttImageSource",
    "RtspSource",
    "ImageSourceFactory",
]
