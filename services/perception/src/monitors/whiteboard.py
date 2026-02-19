"""
Whiteboard Monitor - ホワイトボード監視（汚れ検知）
低頻度・中解像度
"""
import time
import logging
import numpy as np
import cv2
from monitors.base import MonitorBase
from state_publisher import StatePublisher

logger = logging.getLogger(__name__)

class WhiteboardMonitor(MonitorBase):
    def __init__(self, camera_id: str, zone_name: str = "meeting_room_a", image_source=None):
        super().__init__(
            name=f"WhiteboardMonitor_{zone_name}",
            camera_id=camera_id,
            interval_sec=60.0,      # 60秒ごと
            resolution="VGA",       # 640x480 (汚れ検知には十分)
            quality=10,             # 中品質
            image_source=image_source,
        )
        self.zone_name = zone_name
        self.publisher = StatePublisher.get_instance()
        self.previous_hash = None
        self.clean_threshold = 0.05  # 変化率5%以下でクリーンと判定
        
    async def analyze(self, image: np.ndarray):
        """
        ホワイトボードの汚れ検知
        グレースケール変換 → エッジ検出 → エッジ密度で判定
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # エッジ検出
        edges = cv2.Canny(gray, 50, 150)
        
        # エッジ密度計算
        total_pixels = edges.shape[0] * edges.shape[1]
        edge_pixels = np.sum(edges > 0)
        edge_density = edge_pixels / total_pixels
        
        # 変化検出用のハッシュ
        current_hash = hash(edges.tobytes())
        changed = (self.previous_hash != current_hash)
        self.previous_hash = current_hash
        
        return {
            "edge_density": float(edge_density),
            "dirty": edge_density > self.clean_threshold,
            "changed": changed
        }
    
    async def process_results(self, analysis):
        """汚れている場合にアラート送信"""
        payload = {
            "zone": self.zone_name,
            "dirty": analysis["dirty"],
            "edge_density": analysis["edge_density"],
            "changed": analysis["changed"],
            "timestamp": time.time()
        }
        
        topic = f"office/{self.zone_name}/whiteboard/status"
        await self.publisher.publish(topic, payload)
        
        if analysis["dirty"] and analysis["changed"]:
            # タスク生成リクエスト
            task_payload = {
                "zone": self.zone_name,
                "issue": "whiteboard_dirty",
                "severity": "low",
                "timestamp": time.time()
            }
            await self.publisher.publish(
                f"office/{self.zone_name}/tasks/request",
                task_payload
            )
            logger.warning(f"[{self.name}] Whiteboard is dirty!")
        else:
            logger.info(f"[{self.name}] Whiteboard status: {'dirty' if analysis['dirty'] else 'clean'}")
