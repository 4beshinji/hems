"""
HEMS Lite Sentinel — occupant state tracking.
Simplified version of brain's WorldModel, focused on monitoring.
"""
import time
from dataclasses import dataclass, field


@dataclass
class BiometricReading:
    value: float | None = None
    timestamp: float = 0.0

    @property
    def age_seconds(self) -> float:
        if self.timestamp <= 0:
            return float("inf")
        return time.time() - self.timestamp

    @property
    def is_fresh(self) -> bool:
        """Reading less than 5 minutes old."""
        return self.age_seconds < 300


@dataclass
class SleepData:
    stage: str = ""           # deep, light, rem, awake, ""
    duration_hours: float = 0.0
    quality_score: int = 0    # 0-100
    timestamp: float = 0.0


@dataclass
class ActivityData:
    steps: int = 0
    steps_goal: int = 8000
    posture: str = ""         # standing, sitting, lying, walking, ""
    posture_duration_sec: float = 0.0
    activity_level: float = 0.0  # 0.0-1.0
    person_count: int = 0
    timestamp: float = 0.0


@dataclass
class EnvironmentData:
    temperature: float | None = None
    humidity: float | None = None
    co2: float | None = None
    pressure: float | None = None
    illuminance: float | None = None
    timestamp: float = 0.0


@dataclass
class ZoneState:
    zone_id: str = ""
    environment: EnvironmentData = field(default_factory=EnvironmentData)
    activity: ActivityData = field(default_factory=ActivityData)


@dataclass
class OccupantState:
    """Tracks the full state of the monitored person and environment."""

    # Biometric readings
    heart_rate: BiometricReading = field(default_factory=BiometricReading)
    spo2: BiometricReading = field(default_factory=BiometricReading)
    stress: BiometricReading = field(default_factory=BiometricReading)
    fatigue: BiometricReading = field(default_factory=BiometricReading)
    hrv: BiometricReading = field(default_factory=BiometricReading)
    body_temp: BiometricReading = field(default_factory=BiometricReading)
    respiratory_rate: BiometricReading = field(default_factory=BiometricReading)

    # Sleep
    sleep: SleepData = field(default_factory=SleepData)

    # Activity / posture
    activity: ActivityData = field(default_factory=ActivityData)

    # Zones
    zones: dict[str, ZoneState] = field(default_factory=dict)

    # Connectivity
    biometric_connected: bool = False
    perception_connected: bool = False
    ha_connected: bool = False

    # History for trend detection (ring buffer of recent readings)
    # key: metric name, value: list of (timestamp, value)
    _history: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    _history_max_hours: int = 24

    def update_biometric(self, metric: str, value: float):
        """Update a biometric reading and append to history."""
        now = time.time()
        reading = BiometricReading(value=value, timestamp=now)

        if metric == "heart_rate":
            self.heart_rate = reading
        elif metric == "spo2":
            self.spo2 = reading
        elif metric == "stress":
            self.stress = reading
        elif metric == "fatigue":
            self.fatigue = reading
        elif metric == "hrv":
            self.hrv = reading
        elif metric == "body_temp":
            self.body_temp = reading
        elif metric == "respiratory_rate":
            self.respiratory_rate = reading

        self._append_history(f"bio_{metric}", now, value)

    def update_sleep(self, stage: str = "", duration: float = 0.0,
                     quality: int = 0):
        now = time.time()
        self.sleep = SleepData(
            stage=stage, duration_hours=duration,
            quality_score=quality, timestamp=now,
        )

    def update_activity(self, zone_id: str, person_count: int = 0,
                        posture: str = "", activity_level: float = 0.0,
                        posture_duration_sec: float = 0.0):
        now = time.time()
        self.activity = ActivityData(
            posture=posture, activity_level=activity_level,
            person_count=person_count,
            posture_duration_sec=posture_duration_sec,
            timestamp=now,
        )
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
        zone = self.zones[zone_id]
        zone.activity = self.activity
        self._append_history(f"activity_{zone_id}", now, activity_level)

    def update_environment(self, zone_id: str, **kwargs):
        now = time.time()
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
        env = self.zones[zone_id].environment
        env.timestamp = now
        for k, v in kwargs.items():
            if hasattr(env, k) and v is not None:
                setattr(env, k, v)
                self._append_history(f"env_{zone_id}_{k}", now, float(v))

    def update_steps(self, steps: int, steps_goal: int = 0):
        self.activity.steps = steps
        if steps_goal > 0:
            self.activity.steps_goal = steps_goal

    def get_history(self, metric: str, hours: int = 24) -> list[tuple[float, float]]:
        """Get recent history for a metric. Returns [(timestamp, value), ...]."""
        cutoff = time.time() - hours * 3600
        return [
            (ts, val) for ts, val in self._history.get(metric, [])
            if ts >= cutoff
        ]

    def _append_history(self, key: str, ts: float, value: float):
        if key not in self._history:
            self._history[key] = []
        self._history[key].append((ts, value))
        # Prune old entries
        cutoff = ts - self._history_max_hours * 3600
        self._history[key] = [
            (t, v) for t, v in self._history[key] if t >= cutoff
        ]

    def get_context_summary(self) -> str:
        """Generate concise state summary for LLM escalation."""
        lines = []
        now = time.time()

        # Biometrics
        bio_parts = []
        if self.heart_rate.is_fresh:
            bio_parts.append(f"HR={self.heart_rate.value:.0f}bpm")
        if self.spo2.is_fresh:
            bio_parts.append(f"SpO2={self.spo2.value:.0f}%")
        if self.stress.is_fresh:
            bio_parts.append(f"stress={self.stress.value:.0f}")
        if self.fatigue.is_fresh:
            bio_parts.append(f"fatigue={self.fatigue.value:.0f}")
        if self.hrv.is_fresh:
            bio_parts.append(f"HRV={self.hrv.value:.0f}ms")
        if self.body_temp.is_fresh:
            bio_parts.append(f"temp={self.body_temp.value:.1f}C")
        if self.respiratory_rate.is_fresh:
            bio_parts.append(f"resp={self.respiratory_rate.value:.0f}/min")
        if bio_parts:
            lines.append(f"Biometrics: {', '.join(bio_parts)}")

        # Sleep
        if self.sleep.timestamp > 0:
            age_h = (now - self.sleep.timestamp) / 3600
            lines.append(
                f"Sleep: stage={self.sleep.stage}, "
                f"duration={self.sleep.duration_hours:.1f}h, "
                f"quality={self.sleep.quality_score}/100 "
                f"({age_h:.0f}h ago)"
            )

        # Activity
        if self.activity.timestamp > 0:
            lines.append(
                f"Activity: posture={self.activity.posture}, "
                f"level={self.activity.activity_level:.2f}, "
                f"persons={self.activity.person_count}, "
                f"posture_held={self.activity.posture_duration_sec / 60:.0f}min, "
                f"steps={self.activity.steps}"
            )

        # Environment
        for zid, zone in self.zones.items():
            env = zone.environment
            if env.timestamp <= 0:
                continue
            parts = []
            if env.temperature is not None:
                parts.append(f"temp={env.temperature:.1f}C")
            if env.humidity is not None:
                parts.append(f"humidity={env.humidity:.0f}%")
            if env.co2 is not None:
                parts.append(f"CO2={env.co2:.0f}ppm")
            if parts:
                lines.append(f"Zone[{zid}]: {', '.join(parts)}")

        return "\n".join(lines) if lines else "No data available"
