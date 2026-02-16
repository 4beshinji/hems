"""
Sensor fusion — half-life based weighted averaging.
"""
import time
import math

HALF_LIFE = 60.0  # seconds — readings older than this get half weight


class SensorFusion:
    def __init__(self):
        self._readings: list[tuple[float, float, float]] = []  # (timestamp, value, weight)

    def add_reading(self, value: float, weight: float = 1.0):
        now = time.time()
        self._readings.append((now, value, weight))
        # Prune old readings (older than 5 minutes)
        cutoff = now - 300
        self._readings = [(t, v, w) for t, v, w in self._readings if t > cutoff]

    def get_value(self) -> float | None:
        if not self._readings:
            return None

        now = time.time()
        total_weight = 0.0
        weighted_sum = 0.0

        for ts, value, base_weight in self._readings:
            age = now - ts
            decay = math.exp(-0.693 * age / HALF_LIFE)  # ln(2) ≈ 0.693
            w = base_weight * decay
            weighted_sum += value * w
            total_weight += w

        if total_weight == 0:
            return None
        return weighted_sum / total_weight
