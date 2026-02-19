"""
YOLO Inference Engine - YOLOv11を使用した物体検出
"""
import logging
from ultralytics import YOLO
import numpy as np
from typing import List, Dict

logger = logging.getLogger(__name__)

class YOLOInference:
    _instance = None
    
    @classmethod
    def get_instance(cls, model_path: str = "yolo11s.pt"):
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance
    
    def __init__(self, model_path: str = "yolo11s.pt"):
        logger.info(f"Loading YOLO model: {model_path}")
        self.model = YOLO(model_path)
        logger.info("YOLO model loaded successfully")
        
    def infer(self, image: np.ndarray, conf_threshold: float = 0.5) -> List[Dict]:
        """
        YOLO推論実行
        
        Args:
            image: OpenCV画像 (BGR)
            conf_threshold: 信頼度閾値
        
        Returns:
            List[Dict]: 検出結果のリスト
        """
        results = self.model(image, verbose=False, conf=conf_threshold)
        
        detections = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                detections.append({
                    "class": self.model.names[cls_id],
                    "confidence": float(box.conf[0]),
                    "bbox": box.xyxy[0].tolist(),  # [x1, y1, x2, y2]
                    "center": box.xywh[0][:2].tolist(),  # [cx, cy]
                    "width": float(box.xywh[0][2]),
                    "height": float(box.xywh[0][3])
                })
        
        return detections
    
    def filter_by_class(self, detections: List[Dict], class_name: str) -> List[Dict]:
        """特定のクラスでフィルタリング"""
        return [det for det in detections if det['class'] == class_name]
