"""
監視タスク基底クラス
"""
from abc import ABC, abstractmethod
import asyncio
import logging
import time
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# Health monitoring constants
_MAX_CONSECUTIVE_FAILURES = 3
_BACKOFF_SEC = 30.0


class MonitorBase(ABC):
    def __init__(
        self,
        name: str,
        camera_id: str,
        interval_sec: float,
        resolution: str,
        quality: int = 10,
        image_source=None,
    ):
        self.name = name
        self.camera_id = camera_id
        self.interval_sec = interval_sec
        self.resolution = resolution
        self.quality = quality
        self.enabled = True
        self._image_source = image_source
        self._consecutive_failures = 0

    async def run(self):
        """メインループ"""
        logger.info(f"[{self.name}] Started (interval={self.interval_sec}s, res={self.resolution})")

        while self.enabled:
            try:
                start_time = time.time()

                # 画像リクエスト
                image = await self.request_image()

                if image is not None:
                    self._consecutive_failures = 0
                    # 推論実行
                    detections = await self.analyze(image)
                    # 結果処理
                    await self.process_results(detections)
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        logger.warning(
                            f"[{self.name}] Camera offline "
                            f"({self._consecutive_failures} consecutive failures), "
                            f"backing off {_BACKOFF_SEC}s"
                        )
                        await asyncio.sleep(_BACKOFF_SEC)
                        continue
                    else:
                        logger.warning(f"[{self.name}] Image request failed")

                # インターバル調整
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval_sec - elapsed)
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"[{self.name}] Error: {e}", exc_info=True)
                await asyncio.sleep(self.interval_sec)

    async def request_image(self) -> Optional[np.ndarray]:
        """画像リクエスト (image_source優先、なければMQTTフォールバック)"""
        if self._image_source is not None:
            return await self._image_source.capture()
        # Legacy MQTT fallback
        from image_requester import ImageRequester
        requester = ImageRequester.get_instance()
        return await requester.request(
            self.camera_id,
            self.resolution,
            self.quality
        )

    @abstractmethod
    async def analyze(self, image: np.ndarray):
        """
        画像解析（サブクラスで実装）

        Args:
            image: OpenCV画像

        Returns:
            解析結果（サブクラスで定義）
        """
        pass

    @abstractmethod
    async def process_results(self, detections):
        """
        結果処理（サブクラスで実装）

        Args:
            detections: analyze()の戻り値
        """
        pass

    def stop(self):
        """監視タスクを停止"""
        self.enabled = False
        logger.info(f"[{self.name}] Stopped")
