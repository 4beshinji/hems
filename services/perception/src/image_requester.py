"""
Image Requester - MQTT経由でカメラに画像をリクエスト
"""
import asyncio
import uuid
import json
import base64
import logging
import os
from typing import Dict, Optional
import paho.mqtt.client as mqtt
import numpy as np
import cv2

logger = logging.getLogger(__name__)

class ImageRequester:
    _instance = None
    
    @classmethod
    def get_instance(cls, broker: str = "localhost", port: int = 1883):
        if cls._instance is None:
            cls._instance = cls(broker, port)
        return cls._instance
    
    def __init__(self, broker: str = "localhost", port: int = 1883):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_user = os.getenv("MQTT_USER")
        mqtt_pass = os.getenv("MQTT_PASS")
        if mqtt_user:
            self.client.username_pw_set(mqtt_user, mqtt_pass)
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self.client.on_message = self._on_message
        self.client.connect(broker, port)
        self.client.subscribe("mcp/+/response/#")
        self.client.loop_start()
        logger.info(f"ImageRequester connected to {broker}:{port}")
        
    def _on_message(self, client, userdata, msg):
        """レスポンス受信時のコールバック (MQTT thread)"""
        try:
            # トピックからrequest_idを抽出
            # mcp/camera_node_01/response/req-abc123
            parts = msg.topic.split('/')
            request_id = parts[-1]

            future = self.pending_requests.pop(request_id, None)
            if future is None:
                logger.warning(f"Unknown request_id: {request_id}")
                return

            if not self._loop or future.done():
                return

            payload = json.loads(msg.payload)

            # Base64デコード
            image_b64 = payload["image"]
            image_bytes = base64.b64decode(image_b64)

            # OpenCV形式に変換
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"Failed to decode image for {request_id}")
                self._loop.call_soon_threadsafe(
                    future.set_exception, ValueError("Image decode failed")
                )
                return

            # Futureを完了
            self._loop.call_soon_threadsafe(future.set_result, image)
            logger.debug(f"Image received: {request_id}, shape={image.shape}")

        except Exception as e:
            logger.error(f"Error processing response: {e}", exc_info=True)
    
    async def request(
        self, 
        camera_id: str, 
        resolution: str = "VGA", 
        quality: int = 10,
        timeout: float = 10.0
    ) -> Optional[np.ndarray]:
        """
        画像リクエスト（非同期）
        
        Args:
            camera_id: カメラID (例: "camera_node_01")
            resolution: 解像度 ("QVGA", "VGA", "SVGA", "XGA", "UXGA")
            quality: JPEG品質 (1-63, 低いほど高品質)
            timeout: タイムアウト秒数
        
        Returns:
            np.ndarray: OpenCV画像 (BGR), タイムアウト時はNone
        """
        request_id = f"req-{uuid.uuid4().hex[:8]}"

        # Futureを作成
        self._loop = asyncio.get_running_loop()
        future = self._loop.create_future()
        self.pending_requests[request_id] = future
        
        # リクエスト送信
        request = {
            "id": request_id,
            "resolution": resolution,
            "quality": quality
        }
        topic = f"mcp/{camera_id}/request/capture"
        self.client.publish(topic, json.dumps(request))
        logger.debug(f"Image requested: {camera_id}, {resolution}, q={quality}")
        
        # タイムアウト付きで待機
        try:
            image = await asyncio.wait_for(future, timeout=timeout)
            return image
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            logger.error(f"Image request timeout: {camera_id}")
            return None
