"""Unit tests for EDF scheduler."""

from datetime import datetime

from timeline.edf_scheduler import schedule_edf
from timeline.models import CandidateTask, FreeWindow


def _dt(h: int, m: int = 0) -> datetime:
    return datetime(2026, 4, 12, h, m)


def _task(
    tid: int,
    duration_min: int = 30,
    deadline: datetime | None = None,
    urgency: int = 2,
    preferred_slot: str = "anytime",
    cognitive_load: int | None = None,
    locked_start: datetime | None = None,
) -> CandidateTask:
    return CandidateTask(
        task_id=tid,
        title=f"task-{tid}",
        duration_min=duration_min,
        deadline=deadline,
        cognitive_load=cognitive_load,
        preferred_slot=preferred_slot,
        urgency=urgency,
        locked_start=locked_start,
    )


def test_empty_inputs():
    scheduled, overflow = schedule_edf([], [], _dt(10))
    assert scheduled == []
    assert overflow == []


def test_single_task_fits_single_window():
    tasks = [_task(1, duration_min=60)]
    windows = [FreeWindow(start=_dt(9), end=_dt(12))]
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 1
    assert scheduled[0].ref_task_id == 1
    assert scheduled[0].start == _dt(9)
    assert scheduled[0].duration_min == 60
    assert overflow == []


def test_task_longer_than_window_overflows():
    tasks = [_task(1, duration_min=180)]
    windows = [FreeWindow(start=_dt(9), end=_dt(10))]  # only 60min
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert scheduled == []
    assert len(overflow) == 1
    assert overflow[0].task_id == 1


def test_deadline_ordering():
    # Earlier deadline placed first
    tasks = [
        _task(1, duration_min=30, deadline=_dt(18)),
        _task(2, duration_min=30, deadline=_dt(12)),  # earlier deadline
    ]
    windows = [FreeWindow(start=_dt(9), end=_dt(11))]
    scheduled, _overflow = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 2
    assert scheduled[0].ref_task_id == 2  # earlier deadline wins
    assert scheduled[1].ref_task_id == 1


def test_urgency_ordering_when_deadlines_equal():
    # Both no deadline → urgency tiebreaker
    tasks = [
        _task(1, duration_min=30, urgency=1),
        _task(2, duration_min=30, urgency=4),  # higher urgency
    ]
    windows = [FreeWindow(start=_dt(9), end=_dt(11))]
    scheduled, _overflow = schedule_edf(tasks, windows, _dt(8))

    assert scheduled[0].ref_task_id == 2
    assert scheduled[1].ref_task_id == 1


def test_preferred_slot_respected_pass1():
    # Task prefers morning; given a morning and afternoon window
    tasks = [_task(1, duration_min=30, preferred_slot="morning")]
    windows = [
        FreeWindow(start=_dt(14), end=_dt(16)),  # afternoon (earlier in list)
        FreeWindow(start=_dt(9), end=_dt(11)),  # morning
    ]
    scheduled, _ = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 1
    assert scheduled[0].start == _dt(9)


def test_preferred_slot_fallback_when_no_match():
    # Task prefers morning, but only afternoon window exists → Pass 2 fallback
    tasks = [_task(1, duration_min=30, preferred_slot="morning")]
    windows = [FreeWindow(start=_dt(14), end=_dt(16))]
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 1
    assert scheduled[0].start == _dt(14)
    assert overflow == []


def test_expired_deadline_rejected():
    tasks = [_task(1, duration_min=30, deadline=_dt(6))]
    windows = [FreeWindow(start=_dt(9), end=_dt(11))]
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert scheduled == []
    assert len(overflow) == 1


def test_locked_task_placed_first():
    # Locked task should always be placed at the given time, splitting the window
    tasks = [
        _task(1, duration_min=60, locked_start=_dt(10)),
        _task(2, duration_min=30),  # unlocked
    ]
    windows = [FreeWindow(start=_dt(9), end=_dt(13))]
    scheduled, _overflow = schedule_edf(tasks, windows, _dt(8))

    locked_placements = [s for s in scheduled if s.is_locked]
    assert len(locked_placements) == 1
    assert locked_placements[0].ref_task_id == 1
    assert locked_placements[0].start == _dt(10)

    unlocked_placements = [s for s in scheduled if not s.is_locked]
    assert len(unlocked_placements) == 1
    assert unlocked_placements[0].ref_task_id == 2


def test_multiple_tasks_consume_margin():
    # 2 tasks of 30min each in 70min window should fit (30 + 5 margin + 30 = 65 < 70)
    tasks = [
        _task(1, duration_min=30, urgency=4),
        _task(2, duration_min=30, urgency=3),
    ]
    windows = [FreeWindow(start=_dt(9), end=_dt(10, 10))]
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 2
    assert overflow == []
    # Second task starts after first + 5-min margin
    assert scheduled[1].start >= scheduled[0].end


def test_multiple_tasks_with_insufficient_space_overflow():
    # Window 30min + 5 margin = 35min usable for one, second doesn't fit
    tasks = [
        _task(1, duration_min=30, urgency=4),
        _task(2, duration_min=30, urgency=3),
    ]
    windows = [FreeWindow(start=_dt(9), end=_dt(9, 40))]
    scheduled, overflow = schedule_edf(tasks, windows, _dt(8))

    assert len(scheduled) == 1
    assert scheduled[0].ref_task_id == 1
    assert len(overflow) == 1
    assert overflow[0].task_id == 2
