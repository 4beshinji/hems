"""Schedule Timeline — merges routines, calendar, travel buffers, and tasks into a day timeline."""
from .generator import TimelineGenerator
from .models import TimelineSlot, CandidateTask, FreeWindow

__all__ = ["TimelineGenerator", "TimelineSlot", "CandidateTask", "FreeWindow"]
