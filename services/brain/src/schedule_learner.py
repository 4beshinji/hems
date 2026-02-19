"""
Schedule learner — learns user's life patterns and predicts arrivals/departures/wake times.

Data sources:
- OccupancyData count transitions (0→1 = arrival, 1→0 = departure)
- Google Calendar events (for schedule-aware predictions)
"""
import time
import statistics
from datetime import datetime, timedelta
from loguru import logger


# Minimum weeks of data before predictions are reliable
MIN_WEEKS_FOR_PREDICTION = 2
# Maximum weeks of history to retain
MAX_HISTORY_WEEKS = 4


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
            second=0, microsecond=0,
        )
        return predicted_dt.timestamp()

    def get_wake_time(self, calendar_events: list = None) -> float | None:
        """Predict tomorrow's wake time as UNIX timestamp.

        Priority:
        1. Calendar: tomorrow's first event minus 1 hour prep time
        2. Historical wake pattern median

        Returns None if insufficient data.
        """
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        tomorrow_weekday = tomorrow.weekday()
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow_start + timedelta(days=1)

        # Check calendar for tomorrow's first event
        if calendar_events:
            tomorrow_events = []
            for ev in calendar_events:
                start_ts = getattr(ev, "start_ts", 0) or 0
                is_all_day = getattr(ev, "is_all_day", False)
                if is_all_day or start_ts <= 0:
                    continue
                if tomorrow_start.timestamp() <= start_ts < tomorrow_end.timestamp():
                    tomorrow_events.append(start_ts)

            if tomorrow_events:
                first_event_ts = min(tomorrow_events)
                # Wake up 1 hour before first event
                wake_ts = first_event_ts - 3600
                # Clamp to reasonable range (5:00 - 10:00)
                wake_dt = datetime.fromtimestamp(wake_ts)
                if wake_dt.hour < 5:
                    wake_dt = wake_dt.replace(hour=5, minute=0)
                return wake_dt.timestamp()

        # Historical pattern
        history = self._wake_history.get(tomorrow_weekday, [])
        if len(history) < MIN_WEEKS_FOR_PREDICTION:
            return None

        median_hour = statistics.median(history)
        wake_dt = tomorrow.replace(
            hour=int(median_hour),
            minute=int((median_hour % 1) * 60),
            second=0, microsecond=0,
        )
        return wake_dt.timestamp()

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
