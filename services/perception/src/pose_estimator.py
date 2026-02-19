"""
Pose Estimator — YOLO-Pose model wrapper for skeleton keypoint extraction.

COCO 17 keypoints:
  0: nose        1: left_eye     2: right_eye    3: left_ear     4: right_ear
  5: left_shoulder  6: right_shoulder  7: left_elbow  8: right_elbow
  9: left_wrist    10: right_wrist   11: left_hip   12: right_hip
  13: left_knee    14: right_knee    15: left_ankle  16: right_ankle
"""
import logging
from typing import Dict, List

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


class PoseEstimator:
    """Singleton wrapper around a YOLO-Pose model."""

    _instance = None

    @classmethod
    def get_instance(cls, model_path: str = "yolo11s-pose.pt"):
        if cls._instance is None:
            cls._instance = cls(model_path)
        return cls._instance

    def __init__(self, model_path: str = "yolo11s-pose.pt"):
        logger.info(f"Loading pose model: {model_path}")
        self.model = YOLO(model_path)
        logger.info("Pose model loaded successfully")

    def estimate(
        self, image: np.ndarray, conf_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Run pose estimation on an image.

        Returns:
            List of person dicts, each containing:
              - bbox: [x1, y1, x2, y2]
              - confidence: float
              - keypoints: np.ndarray shape (17, 2) — (x, y) pixel coords
              - keypoint_conf: np.ndarray shape (17,) — per-keypoint confidence
        """
        results = self.model(image, verbose=False, conf=conf_threshold)

        persons = []
        for r in results:
            if r.keypoints is None:
                continue
            # r.keypoints.data: (N, 17, 3) — x, y, conf
            kpts_data = r.keypoints.data.cpu().numpy()
            boxes = r.boxes

            for i in range(kpts_data.shape[0]):
                xy = kpts_data[i, :, :2]       # (17, 2)
                conf = kpts_data[i, :, 2]       # (17,)
                persons.append({
                    "bbox": boxes.xyxy[i].tolist(),
                    "confidence": float(boxes.conf[i]),
                    "keypoints": xy,
                    "keypoint_conf": conf,
                })

        return persons
