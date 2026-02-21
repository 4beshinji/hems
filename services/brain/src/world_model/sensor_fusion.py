"""
Sensor fusion logic for combining multiple sensor readings.
"""
import math
import time
from typing import List, Tuple, Dict, Optional


class SensorFusion:
    """Combines multiple sensor readings with reliability weighting."""

    HALF_LIFE = {
        "temperature": 120,
        "humidity": 120,
        "co2": 60,
        "illuminance": 120,
        "occupancy": 30,
        "pir": 10,
        "default": 120
    }

    def __init__(self):
        self.sensor_reliability: Dict[str, float] = {"default": 0.5}
        self._readings: List[Tuple[str, float, float]] = []  # (sensor_id, value, ts)
        self._max_readings: int = 10

    def set_reliability(self, sensor_id: str, score: float):
        """Set reliability score for a specific sensor."""
        if not 0.0 <= score <= 1.0:
            raise ValueError("Reliability score must be between 0.0 and 1.0")
        self.sensor_reliability[sensor_id] = score

    def _get_half_life(self, sensor_type: str) -> float:
        """Get half-life for sensor type."""
        return self.HALF_LIFE.get(sensor_type, self.HALF_LIFE["default"])

    def add_reading(self, value: float, sensor_id: str = "default"):
        """Add a single sensor reading with current timestamp."""
        self._readings.append((sensor_id, value, time.time()))
        if len(self._readings) > self._max_readings:
            self._readings = self._readings[-self._max_readings:]

    def get_value(self, sensor_type: str = "default") -> Optional[float]:
        """Get fused value from stored readings."""
        if not self._readings:
            return None
        return self.fuse_generic(self._readings, sensor_type)

    def fuse_temperature(self, readings: List[Tuple[str, float, float]], sensor_type: str = "temperature") -> Optional[float]:
        """Fuse multiple temperature readings with weighted average."""
        if not readings:
            return None
        total_weight = 0.0
        weighted_sum = 0.0
        current_time = time.time()
        half_life = self._get_half_life(sensor_type)
        for sensor_id, value, timestamp in readings:
            age_seconds = current_time - timestamp
            age_factor = math.exp(-age_seconds / half_life)
            reliability = self.sensor_reliability.get(sensor_id, self.sensor_reliability["default"])
            weight = reliability * age_factor
            weighted_sum += value * weight
            total_weight += weight
        if total_weight == 0:
            return None
        return weighted_sum / total_weight

    def fuse_generic(self, readings: List[Tuple[str, float, float]], sensor_type: str = "default") -> Optional[float]:
        """Generic sensor fusion with sensor-type specific half-life."""
        return self.fuse_temperature(readings, sensor_type)

    def integrate_occupancy(self, vision_count: int, pir_active: bool, zone_size: float = 20.0) -> int:
        """Integrate occupancy from YOLO vision and PIR sensor."""
        estimated_count = vision_count
        if pir_active and vision_count == 0:
            estimated_count = 1
        if zone_size > 50 and vision_count > 0:
            estimated_count = int(vision_count * 1.2)
        return estimated_count
