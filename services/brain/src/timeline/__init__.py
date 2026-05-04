"""Schedule Timeline — merges routines, calendar, travel buffers, and tasks into a day timeline."""

from .generator import TimelineGenerator
from .models import CandidateTask, FreeWindow, TimelineSlot

__all__ = ["CandidateTask", "FreeWindow", "TimelineGenerator", "TimelineSlot"]
