"""
YOLOv11s-pose inference — single-pass person detection + keypoint extraction.
"""
import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    keypoints: np.ndarray | None = None  # (17, 3) COCO format: x, y, conf


@dataclass
class FrameResult:
    person_count: int
    detections: list[Detection] = field(default_factory=list)
    timestamp: float = 0.0


class Detector:
    """YOLOv11s-pose detector — person detection + skeleton in one pass."""

    PERSON_CLASS = 0  # COCO person class ID

    def __init__(self, pose_model_name: str = "yolo11s-pose.pt",
                 confidence: float = 0.5):
        self.pose_model_name = pose_model_name
        self.confidence = confidence
        self._pose_model = None
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_models(self):
        """Load YOLO pose model. Auto-downloads on first run (~30-60s)."""
        try:
            from ultralytics import YOLO
            logger.info(f"Loading pose model: {self.pose_model_name}")
            self._pose_model = YOLO(self.pose_model_name)
            self._loaded = True
            logger.info("Pose model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self._loaded = False

    def detect(self, frame: np.ndarray) -> FrameResult:
        """Run pose detection on a frame. Returns person detections with keypoints."""
        if not self._loaded or self._pose_model is None:
            return FrameResult(person_count=0, timestamp=time.time())

        results = self._pose_model(
            frame,
            conf=self.confidence,
            classes=[self.PERSON_CLASS],
            verbose=False,
        )

        detections = []
        for result in results:
            boxes = result.boxes
            keypoints_data = result.keypoints

            for i in range(len(boxes)):
                box = boxes[i]
                bbox = tuple(float(v) for v in box.xyxy[0].tolist())
                conf = float(box.conf[0])

                kps = None
                if keypoints_data is not None and i < len(keypoints_data):
                    kps_raw = keypoints_data[i].data
                    if kps_raw is not None and len(kps_raw) > 0:
                        kps = kps_raw[0].cpu().numpy()  # (17, 3)

                detections.append(Detection(
                    bbox=bbox,
                    confidence=conf,
                    keypoints=kps,
                ))

        return FrameResult(
            person_count=len(detections),
            detections=detections,
            timestamp=time.time(),
        )
