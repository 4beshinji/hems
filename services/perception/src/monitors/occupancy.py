"""
Occupancy Monitor - 座席占有確認
高頻度・低解像度
"""
import time
import logging
import numpy as np
from monitors.base import MonitorBase
from yolo_inference import YOLOInference
from state_publisher import StatePublisher

logger = logging.getLogger(__name__)

class OccupancyMonitor(MonitorBase):
    def __init__(self, camera_id: str, zone_name: str = "meeting_room_a", image_source=None):
        super().__init__(
            name=f"OccupancyMonitor_{zone_name}",
            camera_id=camera_id,
            interval_sec=5.0,      # 5秒ごと
            resolution="QVGA",      # 320x240
            quality=15,             # 低品質でOK
            image_source=image_source,
        )
        self.zone_name = zone_name
        self.yolo = YOLOInference.get_instance()
        self.publisher = StatePublisher.get_instance()
        
    async def analyze(self, image: np.ndarray):
        """人物検出のみ"""
        results = self.yolo.infer(image, conf_threshold=0.5)
        persons = self.yolo.filter_by_class(results, "person")
        return persons
    
    async def process_results(self, detections):
        """占有状態を送信"""
        count = len(detections)
        occupied = count > 0
        
        payload = {
            "zone": self.zone_name,
            "occupied": occupied,
            "person_count": count,
            "timestamp": time.time()
        }
        
        topic = f"office/{self.zone_name}/occupancy"
        await self.publisher.publish(topic, payload)
        
        logger.info(f"[{self.name}] Occupancy: {count} person(s)")
