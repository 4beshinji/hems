"""Classical Earliest-Deadline-First scheduler with priority + cognitive-load tie-breakers."""
from datetime import datetime, timedelta
from .models import TimelineSlot, CandidateTask, FreeWindow
from .free_window import bucket_of

# Margin added after each task to avoid back-to-back cognitive strain
TASK_MARGIN_MIN = 5

# Far-future sentinel for tasks without deadline
_FAR_FUTURE = datetime.max.replace(tzinfo=None)


def _cognitive_match_score(task_load: int | None, bucket: str) -> int:
    """How well does task cognitive load match the time-of-day bucket? Higher = better."""
    if task_load is None:
        return 0
    # Morning favors deep focus; evening favors light; afternoon is flexible
    ideal_by_bucket = {
        "morning": 3,
        "afternoon": 2,
        "evening": 1,
        "deep_night": 0,
    }
    ideal = ideal_by_bucket.get(bucket, 2)
    return -abs(task_load - ideal)


def _sort_key(task: CandidateTask):
    deadline_val = (
        task.deadline.replace(tzinfo=None) if task.deadline else _FAR_FUTURE
    )
    return (deadline_val, -task.urgency, -(task.cognitive_load or 0))


def _fits_preferred_slot(task: CandidateTask, window_bucket: str) -> bool:
    if not task.preferred_slot or task.preferred_slot == "anytime":
        return True
    return task.preferred_slot == window_bucket


def _try_place_in_window(
    task: CandidateTask,
    window: FreeWindow,
    require_preferred: bool,
) -> TimelineSlot | None:
    needed = task.duration_min + TASK_MARGIN_MIN
    if window.duration_min < needed:
        return None
    start = window.start
    window_bucket = bucket_of(start)
    if require_preferred and not _fits_preferred_slot(task, window_bucket):
        return None
    end = start + timedelta(minutes=task.duration_min)
    return TimelineSlot(
        start=start,
        end=end,
        kind="task",
        title=task.title,
        ref_task_id=task.task_id,
        location=task.location,
        is_locked=False,
    )


def _place_locked_tasks(
    tasks: list[CandidateTask],
    windows: list[FreeWindow],
) -> tuple[list[TimelineSlot], list[CandidateTask], list[FreeWindow]]:
    """Place tasks with explicit locked_start first. Returns (slots, remaining_tasks, remaining_windows)."""
    placed: list[TimelineSlot] = []
    unlocked: list[CandidateTask] = []
    remaining = list(windows)

    for task in tasks:
        if not task.locked_start:
            unlocked.append(task)
            continue

        start = task.locked_start
        end = start + timedelta(minutes=task.duration_min)

        new_remaining: list[FreeWindow] = []
        consumed = False
        for win in remaining:
            if consumed or start >= win.end or end <= win.start:
                new_remaining.append(win)
                continue
            if win.start <= start and end <= win.end:
                if start > win.start:
                    gap = FreeWindow(start=win.start, end=start)
                    if gap.duration_min >= 15:
                        new_remaining.append(gap)
                tail_start = end + timedelta(minutes=TASK_MARGIN_MIN)
                if tail_start < win.end:
                    tail = FreeWindow(start=tail_start, end=win.end)
                    if tail.duration_min >= 15:
                        new_remaining.append(tail)
                consumed = True
            else:
                new_remaining.append(win)
        remaining = new_remaining

        placed.append(
            TimelineSlot(
                start=start,
                end=end,
                kind="task",
                title=task.title,
                ref_task_id=task.task_id,
                location=task.location,
                is_locked=True,
            )
        )

    return placed, unlocked, remaining


def schedule_edf(
    tasks: list[CandidateTask],
    windows: list[FreeWindow],
    now: datetime,
) -> tuple[list[TimelineSlot], list[CandidateTask]]:
    """Schedule tasks into free windows using weighted EDF.

    Algorithm:
      1. Locked tasks (locked_start set) placed first, splitting windows.
      2. Remaining sorted by (deadline ASC, urgency DESC, cognitive_load DESC).
      3. Pass 1: place each task into earliest window matching preferred_slot.
      4. Pass 2: fallback without preferred_slot filter.
      5. Tasks whose deadline has passed are rejected.

    Returns (scheduled_slots, overflow_tasks).
    """
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now

    viable: list[CandidateTask] = []
    overflow: list[CandidateTask] = []
    for t in tasks:
        if t.deadline:
            dl_naive = t.deadline.replace(tzinfo=None) if t.deadline.tzinfo else t.deadline
            if dl_naive < now_naive:
                overflow.append(t)
                continue
        viable.append(t)

    scheduled, unlocked, remaining = _place_locked_tasks(viable, windows)
    unlocked.sort(key=_sort_key)

    def place(remaining_tasks: list[CandidateTask], require_pref: bool) -> list[CandidateTask]:
        leftover: list[CandidateTask] = []
        nonlocal remaining
        for task in remaining_tasks:
            placed_slot: TimelineSlot | None = None
            placed_win_idx: int | None = None
            for idx, win in enumerate(sorted(remaining, key=lambda w: w.start)):
                slot = _try_place_in_window(task, win, require_preferred=require_pref)
                if slot:
                    placed_slot = slot
                    placed_win_idx = remaining.index(win)
                    break
            if placed_slot is None:
                leftover.append(task)
                continue
            scheduled.append(placed_slot)
            win = remaining.pop(placed_win_idx)
            consumed_end = placed_slot.end + timedelta(minutes=TASK_MARGIN_MIN)
            if consumed_end < win.end:
                tail = FreeWindow(start=consumed_end, end=win.end)
                if tail.duration_min >= 15:
                    remaining.append(tail)
        return leftover

    still_unplaced = place(unlocked, require_pref=True)
    still_unplaced = place(still_unplaced, require_pref=False)
    overflow.extend(still_unplaced)

    return scheduled, overflow
