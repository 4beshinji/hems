"""
Task priority scoring for HEMS.
Simplified from SOMS (removed min_people_required).
"""
from enum import IntEnum
from dataclasses import dataclass


class TaskUrgency(IntEnum):
    DEFERRED = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class QueuedTask:
    task_id: int
    title: str
    urgency: int = 2
    zone: str = ""
    task_type: list = None
    xp_reward: int = 100
    estimated_duration: int = 10
    created_at: float = 0

    def compute_priority(self) -> float:
        """Compute priority score. Higher = more urgent."""
        import time
        age_minutes = (time.time() - self.created_at) / 60 if self.created_at else 0
        urgency_weight = self.urgency * 100
        age_bonus = min(age_minutes * 0.5, 50)  # Max 50 points from aging
        return urgency_weight + age_bonus
