"""
Tests for ScheduleLearner — life pattern learning and prediction.
"""
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from schedule_learner import ScheduleLearner


class TestScheduleLearnerRecording:
    def test_record_arrival(self):
        sl = ScheduleLearner()
        now = time.time()
        sl.record_arrival(now)
        weekday = datetime.fromtimestamp(now).weekday()
        assert len(sl._arrival_history[weekday]) == 1

    def test_record_departure(self):
        sl = ScheduleLearner()
        now = time.time()
        sl.record_departure(now)
        weekday = datetime.fromtimestamp(now).weekday()
        assert len(sl._departure_history[weekday]) == 1

    def test_record_wake(self):
        sl = ScheduleLearner()
        # Create a timestamp at 7:30 AM today
        now = datetime.now().replace(hour=7, minute=30, second=0, microsecond=0)
        sl.record_wake(now.timestamp())
        weekday = now.weekday()
        assert len(sl._wake_history[weekday]) == 1

    def test_record_wake_outside_range(self):
        sl = ScheduleLearner()
        # 3 AM — should not be recorded
        now = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
        sl.record_wake(now.timestamp())
        weekday = now.weekday()
        assert weekday not in sl._wake_history or len(sl._wake_history[weekday]) == 0

    def test_update_occupancy_arrival(self):
        sl = ScheduleLearner()
        sl._last_occupancy = 0
        now = time.time()
        sl.update_occupancy(1, now)
        weekday = datetime.fromtimestamp(now).weekday()
        assert len(sl._arrival_history.get(weekday, [])) == 1

    def test_update_occupancy_departure(self):
        sl = ScheduleLearner()
        sl._last_occupancy = 1
        now = time.time()
        sl.update_occupancy(0, now)
        weekday = datetime.fromtimestamp(now).weekday()
        assert len(sl._departure_history.get(weekday, [])) == 1

    def test_update_occupancy_debounce(self):
        sl = ScheduleLearner()
        now = time.time()
        sl._last_occupancy = 0
        sl.update_occupancy(1, now)
        # Immediate second transition should be debounced
        sl.update_occupancy(0, now + 30)
        weekday = datetime.fromtimestamp(now).weekday()
        # arrival should have been recorded, departure debounced
        assert len(sl._arrival_history.get(weekday, [])) == 1
        assert len(sl._departure_history.get(weekday, [])) == 0


class TestScheduleLearnerPrediction:
    def _make_learner_with_history(self, hour_float: float = 18.5, weeks: int = 3):
        """Create a learner with fake arrival history."""
        sl = ScheduleLearner()
        now = datetime.now()
        weekday = now.weekday()
        sl._arrival_history[weekday] = [hour_float] * weeks
        return sl

    def test_predict_arrival_sufficient_data(self):
        sl = self._make_learner_with_history(18.5, weeks=3)
        fake_now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        with patch("schedule_learner.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            predicted = sl.predict_next_arrival()
        assert predicted is not None

    def test_predict_arrival_insufficient_data(self):
        sl = ScheduleLearner()
        assert sl.predict_next_arrival() is None

    def test_predict_arrival_from_calendar(self):
        sl = ScheduleLearner()
        # Create mock calendar event with home keyword
        ev = MagicMock()
        ev.title = "帰宅"
        ev.start_ts = time.time() + 3600  # 1 hour from now
        ev.is_all_day = False

        result = sl.predict_next_arrival(calendar_events=[ev])
        assert result is not None
        assert abs(result - ev.start_ts) < 1

    def test_get_wake_time_from_calendar(self):
        sl = ScheduleLearner()
        # Tomorrow at 8:30
        tomorrow = datetime.now() + timedelta(days=1)
        event_time = tomorrow.replace(hour=8, minute=30, second=0, microsecond=0)

        ev = MagicMock()
        ev.title = "Morning meeting"
        ev.start_ts = event_time.timestamp()
        ev.is_all_day = False

        wake_time = sl.get_wake_time(calendar_events=[ev])
        assert wake_time is not None
        # Should be ~1 hour before (7:30)
        wake_dt = datetime.fromtimestamp(wake_time)
        assert wake_dt.hour == 7

    def test_get_wake_time_insufficient_data(self):
        sl = ScheduleLearner()
        assert sl.get_wake_time() is None

    def test_get_wake_time_from_history(self):
        sl = ScheduleLearner()
        tomorrow = datetime.now() + timedelta(days=1)
        weekday = tomorrow.weekday()
        sl._wake_history[weekday] = [7.0, 7.5, 7.0]  # ~7:00-7:30

        wake_time = sl.get_wake_time()
        assert wake_time is not None
        wake_dt = datetime.fromtimestamp(wake_time)
        assert wake_dt.hour == 7


class TestScheduleLearnerStats:
    def test_get_arrival_stats_no_data(self):
        sl = ScheduleLearner()
        stats = sl.get_arrival_stats()
        assert stats == {}

    def test_get_arrival_stats_with_data(self):
        sl = ScheduleLearner()
        weekday = datetime.now().weekday()
        sl._arrival_history[weekday] = [18.0, 18.5, 19.0]
        stats = sl.get_arrival_stats()
        assert "weekday_arrival" in stats

    def test_get_arrival_stats_with_wake_data(self):
        sl = ScheduleLearner()
        weekday = datetime.now().weekday()
        sl._wake_history[weekday] = [7.0, 7.5, 7.0]
        stats = sl.get_arrival_stats()
        assert "weekday_wake" in stats


class TestScheduleLearnerPersistence:
    def test_save_load_roundtrip(self):
        sl = ScheduleLearner()
        sl._arrival_history = {0: [18.0, 18.5], 4: [17.0]}
        sl._departure_history = {0: [8.0]}
        sl._wake_history = {0: [7.0, 7.5]}

        state = sl.save_state()
        sl2 = ScheduleLearner()
        sl2.load_state(state)

        assert sl2._arrival_history == sl._arrival_history
        assert sl2._departure_history == sl._departure_history
        assert sl2._wake_history == sl._wake_history

    def test_load_empty_state(self):
        sl = ScheduleLearner()
        sl.load_state({})
        assert sl._arrival_history == {}

    def test_load_none_state(self):
        sl = ScheduleLearner()
        sl.load_state(None)
        assert sl._arrival_history == {}


class TestScheduleLearnerPruning:
    def test_prune_history(self):
        sl = ScheduleLearner()
        weekday = 0
        # Add way more entries than max
        sl._arrival_history[weekday] = [18.0] * 100
        sl._prune_history(sl._arrival_history[weekday])
        assert len(sl._arrival_history[weekday]) <= 28  # MAX_HISTORY_WEEKS * 7
