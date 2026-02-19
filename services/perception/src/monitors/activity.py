"""
Activity Monitor — two-tier person detection + pose estimation.

Tier 1 (every cycle): lightweight YOLO person detection.
  → No person? Skip pose.
Tier 2 (only when persons found): YOLO-Pose skeleton extraction.
  → Feed keypoints into tiered ActivityAnalyzer.
  → Publish activity level + posture stasis to MQTT.
"""
import time
import logging
import numpy as np

from monitors.base import MonitorBase
from yolo_inference import YOLOInference
from pose_estimator import PoseEstimator
from activity_analyzer import ActivityAnalyzer
from state_publisher import StatePublisher

logger = logging.getLogger(__name__)


class ActivityMonitor(MonitorBase):
    def __init__(
        self,
        camera_id: str,
        zone_name: str = "default",
        image_source=None,
    ):
        super().__init__(
            name=f"ActivityMonitor_{zone_name}",
            camera_id=camera_id,
            interval_sec=3.0,
            resolution="VGA",
            quality=15,
            image_source=image_source,
        )
        self.zone_name = zone_name
        self.yolo = YOLOInference.get_instance()
        self.pose = PoseEstimator.get_instance()
        self.publisher = StatePublisher.get_instance()
        self.analyzer = ActivityAnalyzer(frame_size=(800, 600))

    async def analyze(self, image: np.ndarray):
        """Two-tier: detect → pose (only if persons found)."""
        # Tier 1: cheap person detection
        detections = self.yolo.infer(image, conf_threshold=0.5)
        persons_det = self.yolo.filter_by_class(detections, "person")

        if not persons_det:
            return {"person_count": 0, "persons_pose": [], "image_shape": image.shape}

        # Tier 2: pose estimation (only runs when we have persons)
        persons_pose = self.pose.estimate(image, conf_threshold=0.4)

        return {
            "person_count": len(persons_det),
            "persons_pose": persons_pose,
            "image_shape": image.shape,
        }

    async def process_results(self, analysis):
        """Feed poses into analyzer and publish activity + posture status."""
        person_count = analysis["person_count"]
        persons_pose = analysis["persons_pose"]

        if persons_pose:
            h, w = analysis["image_shape"][:2]
            self.analyzer._diag = float(np.hypot(w, h))
            self.analyzer.push(persons_pose)

        result = self.analyzer.analyze()

        payload = {
            "zone": self.zone_name,
            "person_count": person_count,
            "activity_level": result["activity_level"],
            "activity_class": result["activity_class"],
            "posture_duration_sec": result["posture_duration_sec"],
            "posture_status": result["posture_status"],
            "buffer_depth": result["buffer_depth"],
            "timestamp": time.time(),
        }

        topic = f"office/{self.zone_name}/activity"
        await self.publisher.publish(topic, payload)

        logger.info(
            f"[{self.name}] persons={person_count} "
            f"activity={result['activity_level']:.3f} ({result['activity_class']}) "
            f"posture={result['posture_status']} "
            f"({result['posture_duration_sec']:.0f}s) "
            f"buf={result['buffer_depth']}"
        )
