"""Free-window computation: subtract locked slots from the day bounds."""

from datetime import datetime, timedelta

from .models import FreeWindow, TimelineSlot


def compute_free_windows(
    day_start: datetime,
    day_end: datetime,
    locked_blocks: list[TimelineSlot],
    min_minutes: int = 15,
) -> list[FreeWindow]:
    """Return gaps between locked blocks within [day_start, day_end] that are ≥ min_minutes."""
    if day_end <= day_start:
        return []

    blocks = sorted(
        [b for b in locked_blocks if b.end > day_start and b.start < day_end],
        key=lambda b: b.start,
    )

    windows: list[FreeWindow] = []
    cursor = day_start

    for b in blocks:
        start = max(b.start, day_start)
        end = min(b.end, day_end)
        if start > cursor:
            gap = FreeWindow(start=cursor, end=start)
            if gap.duration_min >= min_minutes:
                windows.append(gap)
        if end > cursor:
            cursor = end

    if cursor < day_end:
        tail = FreeWindow(start=cursor, end=day_end)
        if tail.duration_min >= min_minutes:
            windows.append(tail)

    return windows


def bucket_of(dt: datetime) -> str:
    """Time-of-day bucket matching preferred_time_slot values."""
    h = dt.hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "deep_night"


def split_window(window: FreeWindow, at: datetime, consume_min: int) -> tuple[FreeWindow | None, FreeWindow | None]:
    """Place a task of consume_min starting at `at` inside the window.

    Returns (before, after) — sub-windows left over (may be None if too short).
    """
    before = FreeWindow(start=window.start, end=at) if at > window.start else None
    end = at + timedelta(minutes=consume_min)
    after = FreeWindow(start=end, end=window.end) if end < window.end else None
    return before, after
