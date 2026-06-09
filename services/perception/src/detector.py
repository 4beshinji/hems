"""
RTMO pose inference (rtmlib / ONNX Runtime) — single-pass multi-person
detection + COCO-17 keypoint extraction.

Replaces the former ultralytics YOLOv11s-pose backend (AGPL-3.0) with RTMO
(MMPose, Apache-2.0) executed via rtmlib (Apache-2.0, onnxruntime-only — no
torch). Downstream consumers (activity_tracker, main) see the same
(17, 3) COCO keypoint contract, so nothing below this module changes.
"""

import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

# Per-keypoint score below which a joint is ignored when deriving the bbox.
_KP_VIS_THRESHOLD = 0.3
# RTMO returns a single zero-filled sentinel "person" when nothing is detected;
# any real person clears this mean-score floor, the sentinel does not.
_SENTINEL_EPS = 0.05


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
    """RTMO detector — person detection + COCO-17 skeleton in one pass."""

    def __init__(
        self,
        pose_model_name: str = "https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/"
        "rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip",
        confidence: float = 0.5,
        device: str = "cpu",
    ):
        # pose_model_name is an ONNX url or local path resolved by rtmlib.
        self.pose_model_name = pose_model_name
        self.confidence = confidence
        self.device = device
        self._pose_model = None
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load_models(self):
        """Load the RTMO ONNX model. Resolved from the rtmlib cache baked into
        the image at build time; only downloads if that cache is absent."""
        try:
            from rtmlib import RTMO

            logger.info(f"Loading RTMO pose model: {self.pose_model_name}")
            self._pose_model = RTMO(
                onnx_model=self.pose_model_name,
                model_input_size=(640, 640),
                score_thr=self.confidence,  # RTMO's internal detection gate
                backend="onnxruntime",
                device=self.device,
            )
            self._loaded = True
            logger.info("RTMO pose model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self._loaded = False

    def detect(self, frame: np.ndarray) -> FrameResult:
        """Run pose detection on a frame. Returns person detections with COCO-17
        keypoints. RTMO already gates detections by score_thr; here we only drop
        the zero-filled sentinel it emits when the frame has no person."""
        if not self._loaded or self._pose_model is None:
            return FrameResult(person_count=0, timestamp=time.time())

        keypoints, scores = self._pose_model(frame)  # (N,17,2), (N,17)

        detections = []
        for kp_xy, kp_score in zip(keypoints, scores):
            mean_score = float(kp_score.mean())
            if mean_score < _SENTINEL_EPS:  # no-detection sentinel
                continue

            kps = np.concatenate([kp_xy, kp_score[:, None]], axis=1)  # (17,3)

            visible = kps[kps[:, 2] >= _KP_VIS_THRESHOLD]
            if len(visible) == 0:
                continue
            x1, y1 = float(visible[:, 0].min()), float(visible[:, 1].min())
            x2, y2 = float(visible[:, 0].max()), float(visible[:, 1].max())

            detections.append(
                Detection(
                    bbox=(x1, y1, x2, y2),
                    confidence=mean_score,
                    keypoints=kps.astype(np.float32),
                )
            )

        return FrameResult(
            person_count=len(detections),
            detections=detections,
            timestamp=time.time(),
        )
