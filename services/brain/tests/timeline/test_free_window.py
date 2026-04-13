"""Unit tests for free-window computation."""
from datetime import datetime, timedelta

from timeline.free_window import compute_free_windows, bucket_of, split_window
from timeline.models import TimelineSlot, FreeWindow


_BASE = datetime(2026, 4, 12, 0, 0)


def _dt(h: int, m: int = 0) -> datetime:
    return _BASE + timedelta(hours=h, minutes=m)


def _slot(start_h: int, end_h: int, kind: str = "calendar") -> TimelineSlot:
    return TimelineSlot(start=_dt(start_h), end=_dt(end_h), kind=kind, title=f"{kind}-{start_h}")


def test_no_locked_blocks_returns_full_day():
    windows = compute_free_windows(_dt(6), _dt(24), [], min_minutes=15)
    assert len(windows) == 1
    assert windows[0].start == _dt(6)
    assert windows[0].end == _dt(24)


def test_single_block_splits_day():
    locked = [_slot(10, 11)]
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    assert len(windows) == 2
    assert windows[0].end == _dt(10)
    assert windows[1].start == _dt(11)


def test_adjacent_blocks_no_gap():
    locked = [_slot(9, 10), _slot(10, 11)]
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    # No gap between 10 and 10 — should produce [6-9, 11-24] only
    assert len(windows) == 2
    assert windows[0].end == _dt(9)
    assert windows[1].start == _dt(11)


def test_overlapping_blocks_merged():
    locked = [_slot(10, 12), _slot(11, 13)]
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    # Cursor advances to max(end), so gap is 6-10 and 13-24
    assert len(windows) == 2
    assert windows[0] == FreeWindow(start=_dt(6), end=_dt(10))
    assert windows[1] == FreeWindow(start=_dt(13), end=_dt(24))


def test_min_minutes_filter():
    # 10-min gap is rejected when min_minutes=15
    locked = [_slot(9, 10), TimelineSlot(start=_dt(10, 10), end=_dt(11), kind="calendar", title="x")]
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    # Gap 10:00-10:10 is 10min → rejected. Surviving: 6-9 and 11-24.
    assert len(windows) == 2
    assert windows[0].end == _dt(9)
    assert windows[1].start == _dt(11)


def test_blocks_outside_day_bounds_ignored():
    locked = [_slot(3, 5), _slot(25, 26)]  # entirely outside 6-24
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    assert len(windows) == 1
    assert windows[0] == FreeWindow(start=_dt(6), end=_dt(24))


def test_block_clipped_to_day_bounds():
    locked = [_slot(4, 8)]  # starts before day_start
    windows = compute_free_windows(_dt(6), _dt(24), locked, min_minutes=15)
    assert len(windows) == 1
    assert windows[0].start == _dt(8)
    assert windows[0].end == _dt(24)


def test_bucket_of():
    assert bucket_of(_dt(7)) == "morning"
    assert bucket_of(_dt(12)) == "afternoon"
    assert bucket_of(_dt(20)) == "evening"
    assert bucket_of(_dt(2)) == "deep_night"
    assert bucket_of(_dt(22)) == "deep_night"


def test_split_window_middle():
    w = FreeWindow(start=_dt(9), end=_dt(12))
    before, after = split_window(w, at=_dt(10), consume_min=30)
    assert before == FreeWindow(start=_dt(9), end=_dt(10))
    assert after == FreeWindow(start=_dt(10, 30), end=_dt(12))


def test_split_window_at_start():
    w = FreeWindow(start=_dt(9), end=_dt(12))
    before, after = split_window(w, at=_dt(9), consume_min=30)
    assert before is None
    assert after == FreeWindow(start=_dt(9, 30), end=_dt(12))
