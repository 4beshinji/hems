"""Timeline data classes — pure data shapes, no I/O."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimelineSlot:
    """A single rendered slot on the timeline."""

    start: datetime
    end: datetime
    kind: str  # calendar|task|routine_wake|commute_out|commute_in|focus_free|sleep|prep
    title: str
    ref_task_id: int | None = None
    ref_calendar_event_id: str | None = None
    location: str | None = None
    is_locked: bool = False
    travel_buffer_minutes: int = 0

    @property
    def duration_min(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))


@dataclass
class CandidateTask:
    """A task considered for timeline placement."""

    task_id: int
    title: str
    duration_min: int
    deadline: datetime | None
    cognitive_load: int | None
    preferred_slot: str  # morning|afternoon|evening|deep_night|anytime
    urgency: int
    locked_start: datetime | None = None
    source: str | None = None
    zone: str | None = None
    location: str | None = None


@dataclass
class FreeWindow:
    """Gap in the locked timeline available for task insertion."""

    start: datetime
    end: datetime

    @property
    def duration_min(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() // 60))
