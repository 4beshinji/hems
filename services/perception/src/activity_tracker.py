"""
Posture classification, activity level computation, and duration tracking.
Uses COCO 17-keypoint skeleton from YOLOv11-pose.
"""
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from loguru import logger

# COCO keypoint indices
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16

# Minimum keypoint confidence to consider valid
MIN_KP_CONF = 0.3


@dataclass
class ActivityState:
    """Current activity state for a tracked person/zone."""
    posture: str = "unknown"           # standing, sitting, lying, walking, unknown
    activity_level: float = 0.0        # 0.0-1.0 smoothed
    activity_class: str = "unknown"    # idle, low, moderate, high
    posture_duration_sec: float = 0.0  # seconds in current posture
    posture_status: str = "unknown"    # changing, mostly_static, static
    last_update: float = 0.0


class ActivityTracker:
    """Track posture and activity level from keypoint sequences."""

    # Activity level thresholds
    IDLE_THRESHOLD = 0.1
    LOW_THRESHOLD = 0.3
    MODERATE_THRESHOLD = 0.6

    # Posture duration thresholds (seconds)
    CHANGING_THRESHOLD = 300      # < 5 min
    MOSTLY_STATIC_THRESHOLD = 3600  # < 60 min

    # EMA smoothing factor for activity level
    EMA_ALPHA = 0.3

    # Movement normalization factor (pixels)
    MOVEMENT_NORM = 200.0

    def __init__(self):
        # Tiered pose buffer
        self._tier1: deque[np.ndarray] = deque(maxlen=3)    # 15s (3 frames)
        self._tier2: deque[np.ndarray] = deque(maxlen=12)   # 60s (12 frames)
        self._tier3: deque[np.ndarray] = deque(maxlen=60)   # 300s (60 frames)

        self._state = ActivityState()
        self._posture_start_time: float = 0.0
        self._last_posture: str = "unknown"
        self._smoothed_activity: float = 0.0

    @property
    def state(self) -> ActivityState:
        return self._state

    def update(self, keypoints: np.ndarray | None, timestamp: float | None = None) -> ActivityState:
        """Update tracker with new keypoints (17, 3) and return current state.

        Args:
            keypoints: COCO 17-keypoint array (17, 3) with x, y, confidence.
                       None if no person detected.
            timestamp: Current timestamp. Uses time.time() if not provided.
        """
        ts = timestamp or time.time()

        if keypoints is None or len(keypoints) < 17:
            self._state.last_update = ts
            return self._state

        # Add to tiered buffers
        self._tier1.append(keypoints.copy())
        self._tier2.append(keypoints.copy())
        self._tier3.append(keypoints.copy())

        # Classify posture
        posture = self._classify_posture(keypoints)

        # Compute raw activity from inter-frame movement
        raw_activity = self._compute_movement()

        # Check for walking (standing + high movement)
        if posture == "standing" and raw_activity > self.LOW_THRESHOLD:
            posture = "walking"

        # EMA smooth activity level
        self._smoothed_activity = (
            self.EMA_ALPHA * raw_activity
            + (1 - self.EMA_ALPHA) * self._smoothed_activity
        )
        activity_level = max(0.0, min(1.0, self._smoothed_activity))

        # Classify activity
        activity_class = self._classify_activity(activity_level)

        # Track posture duration
        if posture != self._last_posture:
            self._last_posture = posture
            self._posture_start_time = ts

        posture_duration = ts - self._posture_start_time if self._posture_start_time > 0 else 0.0

        # Derive posture status
        posture_status = self._derive_posture_status(posture_duration)

        self._state = ActivityState(
            posture=posture,
            activity_level=round(activity_level, 2),
            activity_class=activity_class,
            posture_duration_sec=round(posture_duration, 1),
            posture_status=posture_status,
            last_update=ts,
        )
        return self._state

    def _classify_posture(self, kps: np.ndarray) -> str:
        """Classify posture from COCO keypoints based on joint relationships."""
        def valid(idx: int) -> bool:
            return kps[idx][2] >= MIN_KP_CONF

        def y(idx: int) -> float:
            return kps[idx][1]

        # Need at least shoulders and hips
        has_shoulders = valid(LEFT_SHOULDER) or valid(RIGHT_SHOULDER)
        has_hips = valid(LEFT_HIP) or valid(RIGHT_HIP)
        if not has_shoulders or not has_hips:
            return "unknown"

        # Average Y positions (lower Y = higher in image for standard camera)
        shoulder_y = np.mean([y(i) for i in [LEFT_SHOULDER, RIGHT_SHOULDER] if valid(i)])
        hip_y = np.mean([y(i) for i in [LEFT_HIP, RIGHT_HIP] if valid(i)])

        torso_height = abs(hip_y - shoulder_y)

        # Lying: shoulder and hip at similar height (horizontal torso)
        if torso_height < 30:
            return "lying"

        # Check knees if available
        has_knees = valid(LEFT_KNEE) or valid(RIGHT_KNEE)
        if has_knees:
            knee_y = np.mean([y(i) for i in [LEFT_KNEE, RIGHT_KNEE] if valid(i)])

            # Sitting: knees at roughly same height as hips
            hip_knee_diff = abs(knee_y - hip_y)
            if hip_knee_diff < torso_height * 0.5:
                return "sitting"

        # Default to standing if torso is vertical
        return "standing"

    def _compute_movement(self) -> float:
        """Compute inter-frame movement from tier1 buffer."""
        if len(self._tier1) < 2:
            return 0.0

        prev = self._tier1[-2]
        curr = self._tier1[-1]

        # Only consider keypoints that are valid in both frames
        total_disp = 0.0
        count = 0
        for i in range(min(len(prev), len(curr))):
            if prev[i][2] >= MIN_KP_CONF and curr[i][2] >= MIN_KP_CONF:
                dx = curr[i][0] - prev[i][0]
                dy = curr[i][1] - prev[i][1]
                total_disp += np.sqrt(dx * dx + dy * dy)
                count += 1

        if count == 0:
            return 0.0

        # Normalize: average displacement per keypoint / norm factor
        avg_disp = total_disp / count
        return min(1.0, avg_disp / self.MOVEMENT_NORM)

    def _classify_activity(self, level: float) -> str:
        """Map activity level to class string."""
        if level < self.IDLE_THRESHOLD:
            return "idle"
        elif level < self.LOW_THRESHOLD:
            return "low"
        elif level < self.MODERATE_THRESHOLD:
            return "moderate"
        else:
            return "high"

    def _derive_posture_status(self, duration_sec: float) -> str:
        """Derive posture status from duration."""
        if duration_sec < self.CHANGING_THRESHOLD:
            return "changing"
        elif duration_sec < self.MOSTLY_STATIC_THRESHOLD:
            return "mostly_static"
        else:
            return "static"
