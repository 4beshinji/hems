"""Brain-side feedback and learning subsystem (Phase 1)."""

from feedback.collector import FeedbackCollector
from feedback.implicit_detector import ImplicitFeedbackDetector
from feedback.outcome_reward import OutcomeRewardCalculator
from feedback.trajectory_recorder import TrajectoryRecorder

__all__ = [
    "FeedbackCollector",
    "ImplicitFeedbackDetector",
    "OutcomeRewardCalculator",
    "TrajectoryRecorder",
]
