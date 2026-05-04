"""
VLM Adaptive Scheduler — decides when and at what tier to run VLM analysis.

Modes:
  - Normal:   base_interval (default 30min), light tier
  - Boosted:  reduced interval + heavy tier on significant events
  - Quiet:    extended interval after consecutive uninteresting results
  - On-demand: immediate analysis from brain tool calls
"""

import time
import uuid
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class OnDemandRequest:
    """Queued on-demand VLM analysis request."""

    request_id: str
    zone: str = ""
    prompt: str = ""
    timestamp: float = field(default_factory=time.time)


# Event boost configuration: (interval_factor, duration_seconds, tier)
_EVENT_BOOST: dict[str, tuple[float, int, str]] = {
    "person_count_changed": (0.05, 300, "heavy"),
    "posture_changed": (0.2, 120, "light"),
    "activity_spike": (0.3, 120, "light"),
    "sensor_alert": (0.2, 180, "heavy"),
}


class VLMScheduler:
    """Adaptive scheduling engine for VLM analysis."""

    def __init__(
        self,
        base_interval: int = 1800,
        min_interval: int = 60,
        max_interval: int = 7200,
        boost_duration: int = 300,
        cooldown: int = 30,
    ):
        self.base_interval = base_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.boost_duration = boost_duration
        self.cooldown = cooldown

        # State
        self._last_run: float = 0
        self._boost_until: float = 0
        self._boost_factor: float = 1.0
        self._boost_tier: str = "light"
        self._quiet_count: int = 0  # consecutive uninteresting results
        self._on_demand_queue: list[OnDemandRequest] = []
        self._current_tier: str = "light"

    @property
    def current_tier(self) -> str:
        """Current VLM tier that will be used on next run."""
        return self._current_tier

    @property
    def current_interval(self) -> float:
        """Current effective interval in seconds."""
        now = time.time()

        # Boosted mode
        if now < self._boost_until:
            interval = self.base_interval * self._boost_factor
            return max(interval, self.min_interval)

        # Quiet decay: grow interval by quiet_count * 0.2, capped at 3x
        if self._quiet_count > 0:
            decay_factor = min(1.0 + self._quiet_count * 0.2, 3.0)
            interval = self.base_interval * decay_factor
            return min(interval, self.max_interval)

        return self.base_interval

    @property
    def mode(self) -> str:
        """Current scheduler mode."""
        if self._on_demand_queue:
            return "on_demand"
        now = time.time()
        if now < self._boost_until:
            return "boosted"
        if self._quiet_count > 2:
            return "quiet"
        return "normal"

    @property
    def next_run_estimate(self) -> float:
        """Estimated timestamp of next VLM run."""
        if self._on_demand_queue:
            return time.time()  # immediate
        return self._last_run + self.current_interval

    def notify_event(self, event_type: str, data: dict | None = None) -> None:
        """Called by YOLO loop on state changes to potentially boost VLM frequency.

        Args:
            event_type: One of person_count_changed, posture_changed,
                        activity_spike, sensor_alert.
            data: Optional event data.
        """
        boost_config = _EVENT_BOOST.get(event_type)
        if not boost_config:
            return

        factor, duration, tier = boost_config
        now = time.time()

        # Only upgrade boost (don't downgrade an active stronger boost)
        if now < self._boost_until and factor >= self._boost_factor:
            return

        self._boost_factor = factor
        self._boost_until = now + duration
        self._boost_tier = tier
        self._quiet_count = 0  # Reset quiet decay on any event

        logger.debug(f"VLM boost: event={event_type}, factor={factor}, duration={duration}s, tier={tier}")

    def should_run_now(self) -> bool:
        """Check if VLM analysis should run now.

        Returns True if interval has elapsed, on-demand request is queued,
        or boost mode warrants a run.
        """
        now = time.time()

        # On-demand requests always run
        if self._on_demand_queue:
            self._current_tier = "heavy"
            return True

        # Cooldown check (minimum gap between runs)
        if now - self._last_run < self.cooldown:
            return False

        # Check against current effective interval
        if now - self._last_run >= self.current_interval:
            self._current_tier = self._select_tier(None)
            return True

        return False

    def record_run(self, interesting: bool = True) -> None:
        """Record that a VLM run completed.

        Args:
            interesting: Whether the result contained notable content.
                         False results grow the quiet decay.
        """
        self._last_run = time.time()

        if interesting:
            self._quiet_count = 0
        else:
            self._quiet_count += 1

    def request_on_demand(self, zone: str = "", prompt: str = "") -> str:
        """Queue an immediate on-demand VLM analysis.

        Returns:
            request_id for tracking.
        """
        request_id = str(uuid.uuid4())[:8]
        self._on_demand_queue.append(OnDemandRequest(request_id=request_id, zone=zone, prompt=prompt))
        logger.info(f"VLM on-demand queued: id={request_id}, zone={zone}")
        return request_id

    def pop_on_demand(self) -> OnDemandRequest | None:
        """Pop the next on-demand request from the queue."""
        if self._on_demand_queue:
            return self._on_demand_queue.pop(0)
        return None

    def _select_tier(self, event_type: str | None) -> str:
        """Select VLM tier based on trigger event or current state."""
        if event_type in ("person_count_changed", "sensor_alert", "on_demand"):
            return "heavy"

        now = time.time()
        if now < self._boost_until:
            return self._boost_tier

        return "light"

    def get_status(self) -> dict:
        """Return scheduler status for REST API / MQTT."""
        return {
            "mode": self.mode,
            "tier": self._current_tier,
            "current_interval": self.current_interval,
            "last_run": self._last_run,
            "next_run_est": self.next_run_estimate,
            "boost_until": self._boost_until,
            "quiet_count": self._quiet_count,
            "on_demand_pending": len(self._on_demand_queue),
        }
