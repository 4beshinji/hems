"""
Schedule learner — learns user's life patterns and predicts arrivals/departures/wake times.

Data sources:
- OccupancyData count transitions (0→1 = arrival, 1→0 = departure)
- Google Calendar events (for schedule-aware predictions)
"""

import os
import statistics
import time
from datetime import datetime, timedelta

from loguru import logger

# Minimum weeks of data before predictions are reliable
MIN_WEEKS_FOR_PREDICTION = 2
# Maximum weeks of history to retain
MAX_HISTORY_WEEKS = 4

# Fallback wake time when no calendar/history data (HH:MM, empty=disabled)
FALLBACK_WAKE_TIME = os.getenv("FALLBACK_WAKE_TIME", "07:00")


class ScheduleLearner:
    """Learns and predicts user's daily life patterns."""

    def __init__(self):
        # weekday (0-6) → list of hour_float (e.g. 18.5 = 18:30)
        self._arrival_history: dict[int, list[float]] = {}
        self._departure_history: dict[int, list[float]] = {}
        self._wake_history: dict[int, list[float]] = {}

        # Last known occupancy count (for transition detection)
        self._last_occupancy: int = 0
        self._last_transition_time: float = 0

    # Public history accessors so consumers (e.g. TimelineGenerator) read routine
    # patterns without reaching into the private _*_history dicts.
    _HISTORY_ATTR = {
        "wake": "_wake_history",
        "departure": "_departure_history",
        "arrival": "_arrival_history",
    }

    def history_count(self, kind: str, weekday: int) -> int:
        """Number of recorded samples for a routine *kind* on *weekday* (0-6)."""
        hist = getattr(self, self._HISTORY_ATTR[kind], {})
        return len(hist.get(weekday, []))

    def median_hour(self, kind: str, weekday: int, default: float, min_samples: int = 2) -> float:
        """Median recorded hour_float for a routine *kind* on *weekday*.

        Returns *default* when fewer than *min_samples* observations exist.
        """
        hist = getattr(self, self._HISTORY_ATTR[kind], {})
        entries = hist.get(weekday, [])
        if len(entries) >= min_samples:
            return statistics.median(entries)
        return default

    def update_occupancy(self, count: int, timestamp: float | None = None):
        """Update with new occupancy count. Detects arrivals and departures."""
        ts = timestamp or time.time()
        # Debounce: ignore transitions within 60 seconds
        if ts - self._last_transition_time < 60:
            self._last_occupancy = count
            return

        if self._last_occupancy == 0 and count > 0:
            self.record_arrival(ts)
        elif self._last_occupancy > 0 and count == 0:
            self.record_departure(ts)

        self._last_occupancy = count
        self._last_transition_time = ts

    def record_arrival(self, timestamp: float):
        """Record an arrival event."""
        dt = datetime.fromtimestamp(timestamp)
        weekday = dt.weekday()
        hour_float = dt.hour + dt.minute / 60.0

        if weekday not in self._arrival_history:
            self._arrival_history[weekday] = []
        self._arrival_history[weekday].append(hour_float)
        self._prune_history(self._arrival_history[weekday])
        logger.debug(f"Arrival recorded: weekday={weekday} time={hour_float:.1f}")

    def record_departure(self, timestamp: float):
        """Record a departure event."""
        dt = datetime.fromtimestamp(timestamp)
        weekday = dt.weekday()
        hour_float = dt.hour + dt.minute / 60.0

        if weekday not in self._departure_history:
            self._departure_history[weekday] = []
        self._departure_history[weekday].append(hour_float)
        self._prune_history(self._departure_history[weekday])
        logger.debug(f"Departure recorded: weekday={weekday} time={hour_float:.1f}")

    def record_wake(self, timestamp: float):
        """Record a wake-up event (activity transition from idle)."""
        dt = datetime.fromtimestamp(timestamp)
        weekday = dt.weekday()
        hour_float = dt.hour + dt.minute / 60.0

        # Only record between 4:00 and 12:00
        if not (4 <= hour_float <= 12):
            return

        if weekday not in self._wake_history:
            self._wake_history[weekday] = []
        self._wake_history[weekday].append(hour_float)
        self._prune_history(self._wake_history[weekday])

    def record_sleep_from_biometrics(self, sleep_start_ts: float, sleep_end_ts: float):
        """Record wake time from biometric sleep data (more accurate than posture estimation).

        Uses the sleep end timestamp as the wake time.
        """
        if sleep_end_ts <= 0:
            return
        dt = datetime.fromtimestamp(sleep_end_ts)
        hour_float = dt.hour + dt.minute / 60.0
        # Only record reasonable wake times (4:00 - 12:00)
        if not (4 <= hour_float <= 12):
            return
        weekday = dt.weekday()
        if weekday not in self._wake_history:
            self._wake_history[weekday] = []
        self._wake_history[weekday].append(hour_float)
        self._prune_history(self._wake_history[weekday])
        logger.debug(f"Biometric wake recorded: weekday={weekday} time={hour_float:.1f}")

    def predict_next_arrival(self, calendar_events: list = None) -> float | None:
        """Predict next arrival time as UNIX timestamp.

        Priority:
        1. Calendar events with home-related keywords
        2. Historical pattern median for today's weekday

        Returns None if insufficient data.
        """
        now = datetime.now()
        today_weekday = now.weekday()

        # Check calendar for home-arrival hints
        if calendar_events:
            home_keywords = {"帰宅", "自宅", "家", "帰る", "home", "return"}
            now_ts = time.time()
            for ev in calendar_events:
                title = getattr(ev, "title", "") or ""
                start_ts = getattr(ev, "start_ts", 0) or 0
                if start_ts > now_ts and any(kw in title.lower() for kw in home_keywords):
                    return start_ts

        # Historical pattern
        history = self._arrival_history.get(today_weekday, [])
        if len(history) < MIN_WEEKS_FOR_PREDICTION:
            return None

        median_hour = statistics.median(history)
        # If current time is past the median, no prediction for today
        current_hour = now.hour + now.minute / 60.0
        if current_hour >= median_hour:
            return None

        # Convert median hour to today's timestamp
        predicted_dt = now.replace(
            hour=int(median_hour),
            minute=int((median_hour % 1) * 60),
            second=0,
            microsecond=0,
        )
        return predicted_dt.timestamp()

    def get_wake_time(
        self,
        calendar_events: list = None,
        fatigue_score: int | None = None,
    ) -> float | None:
        """Predict the next upcoming wake time as a UNIX timestamp.

        Returns today's predicted wake if it has not yet passed; otherwise
        tomorrow's predicted wake. BootLoad and SunriseAlarm rely on this
        being "the next wake event" rather than literally tomorrow.

        Priority:
        1. Calendar: next first-of-day event minus 1 hour prep time
        2. Historical wake pattern median for that weekday
        3. FALLBACK_WAKE_TIME env var

        fatigue_score (0-100, optional): if ≥70 the predicted wake time is
        delayed up to 30 minutes (only applies to the historical pattern path,
        not the calendar path — calendar events still take precedence).

        Returns None if insufficient data.
        """
        now = datetime.now()
        now_ts = now.timestamp()

        # Convert fatigue (0-100) to delay seconds (0 → 0 / 100 → 1800).
        # Apply only above a 60 floor so mild tiredness doesn't shift wake.
        fatigue_offset_sec = 0
        if fatigue_score is not None and fatigue_score >= 60:
            fatigue_offset_sec = int(min(fatigue_score - 60, 40) * 45)  # 60→0s, 100→1800s

        # Helper: build a wake datetime for a given target date + hour_float
        def _build(target_date: datetime, hour_float: float) -> datetime:
            return target_date.replace(
                hour=int(hour_float),
                minute=int((hour_float % 1) * 60),
                second=0,
                microsecond=0,
            )

        # Try today first, then tomorrow — return the first prediction in the future
        for day_offset in (0, 1):
            target = now + timedelta(days=day_offset)
            target_weekday = target.weekday()
            day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            # 1. Calendar: first event of the day minus 1h prep
            if calendar_events:
                day_events = []
                for ev in calendar_events:
                    start_ts = getattr(ev, "start_ts", 0) or 0
                    is_all_day = getattr(ev, "is_all_day", False)
                    if is_all_day or start_ts <= 0:
                        continue
                    if day_start.timestamp() <= start_ts < day_end.timestamp():
                        day_events.append(start_ts)
                if day_events:
                    first_event_ts = min(day_events)
                    wake_dt = datetime.fromtimestamp(first_event_ts - 3600)
                    if wake_dt.hour < 5:
                        wake_dt = wake_dt.replace(hour=5, minute=0)
                    if wake_dt.timestamp() > now_ts:
                        return wake_dt.timestamp()

            # 2. Historical wake pattern median (with optional fatigue delay)
            history = self._wake_history.get(target_weekday, [])
            if len(history) >= MIN_WEEKS_FOR_PREDICTION:
                wake_dt = _build(target, statistics.median(history))
                if fatigue_offset_sec:
                    wake_dt = wake_dt + timedelta(seconds=fatigue_offset_sec)
                if wake_dt.timestamp() > now_ts:
                    return wake_dt.timestamp()

            # 3. Fallback: fixed time from env var
            if FALLBACK_WAKE_TIME:
                try:
                    h, m = (int(x) for x in FALLBACK_WAKE_TIME.split(":"))
                    wake_dt = target.replace(hour=h, minute=m, second=0, microsecond=0)
                    if wake_dt.timestamp() > now_ts:
                        return wake_dt.timestamp()
                except (ValueError, TypeError):
                    pass

        return None

    def get_wake_confidence(self) -> str:
        """Return ``high`` / ``medium`` / ``low`` for the next wake prediction.

        BootLoadManager uses this to widen its pre-wake window when the
        prediction is uncertain (sparse history or large stdev), so we don't
        miss the wake event by a few minutes early in the learner's life.

        - high:   >= 4 weeks of data AND stdev <= 20min
        - medium: >= 2 weeks of data AND stdev <= 40min (or simply >= 2 weeks)
        - low:    < 2 weeks of data (FALLBACK_WAKE_TIME or single sample)
        """
        now = datetime.now()
        # Prefer today's weekday history; fall back to tomorrow's (the
        # weekday `get_wake_time` would actually consult if today is past).
        history = self._wake_history.get(now.weekday(), [])
        if not history:
            history = self._wake_history.get((now + timedelta(days=1)).weekday(), [])

        if len(history) >= 4:
            stdev_min = statistics.stdev(history) * 60 if len(history) > 1 else 0
            if stdev_min <= 20:
                return "high"
            if stdev_min <= 40:
                return "medium"
            return "low"
        if len(history) >= MIN_WEEKS_FOR_PREDICTION:
            return "medium"
        return "low"

    def get_arrival_stats(self) -> dict:
        """Return summary statistics for LLM context."""
        now = datetime.now()
        weekday = now.weekday()
        stats = {}

        history = self._arrival_history.get(weekday, [])
        if len(history) >= MIN_WEEKS_FOR_PREDICTION:
            median = statistics.median(history)
            stdev = statistics.stdev(history) if len(history) > 1 else 0
            h = int(median)
            m = int((median % 1) * 60)
            stats["weekday_arrival"] = f"~{h:02d}:{m:02d}"
            stats["arrival_stdev_min"] = int(stdev * 60)

        wake_history = self._wake_history.get(weekday, [])
        if len(wake_history) >= MIN_WEEKS_FOR_PREDICTION:
            median = statistics.median(wake_history)
            h = int(median)
            m = int((median % 1) * 60)
            stats["weekday_wake"] = f"~{h:02d}:{m:02d}"

        return stats

    def save_state(self) -> dict:
        """Serialize state for persistence."""
        return {
            "arrival_history": self._arrival_history,
            "departure_history": self._departure_history,
            "wake_history": self._wake_history,
        }

    def load_state(self, data: dict):
        """Restore state from persisted data."""
        if not data:
            return
        # Convert string keys back to int (JSON serialization issue)
        self._arrival_history = {int(k): v for k, v in data.get("arrival_history", {}).items()}
        self._departure_history = {int(k): v for k, v in data.get("departure_history", {}).items()}
        self._wake_history = {int(k): v for k, v in data.get("wake_history", {}).items()}

    @staticmethod
    def _prune_history(history: list):
        """Keep only the last MAX_HISTORY_WEEKS * 7 entries."""
        max_entries = MAX_HISTORY_WEEKS * 7
        if len(history) > max_entries:
            del history[:-max_entries]
