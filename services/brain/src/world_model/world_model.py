"""
WorldModel — maintains unified zone state from MQTT messages.
Forked from SOMS with HEMS personal topic support.
"""
import time
import logging
from .data_classes import ZoneState, EnvironmentData, OccupancyData, Event
from .sensor_fusion import SensorFusion

logger = logging.getLogger(__name__)

# Environment thresholds for event generation
CO2_HIGH = 1000
CO2_CRITICAL = 1500
TEMP_HIGH = 28
TEMP_LOW = 16
SEDENTARY_MINUTES = 60


class WorldModel:
    def __init__(self):
        self.zones: dict[str, ZoneState] = {}
        self._sensor_fusions: dict[str, SensorFusion] = {}
        self.event_writer = None  # Set by Brain if event_store is available

    def _get_zone(self, zone_id: str) -> ZoneState:
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
        return self.zones[zone_id]

    def _get_fusion(self, key: str) -> SensorFusion:
        if key not in self._sensor_fusions:
            self._sensor_fusions[key] = SensorFusion()
        return self._sensor_fusions[key]

    def update_from_mqtt(self, topic: str, payload: dict):
        """Parse MQTT topic and update world state."""
        parts = topic.split("/")

        # office/{zone}/sensor/{device_id}/{channel}
        if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
            zone_id = parts[1]
            channel = parts[4]
            value = payload.get(channel) or payload.get("value")
            if value is not None:
                self._update_sensor(zone_id, channel, float(value))

        # office/{zone}/camera/{camera_id}/status (occupancy)
        elif len(parts) >= 5 and parts[0] == "office" and parts[2] == "camera":
            zone_id = parts[1]
            count = payload.get("person_count", payload.get("count", 0))
            zone = self._get_zone(zone_id)
            zone.occupancy = OccupancyData(count=int(count), last_update=time.time())

        # office/{zone}/activity/{monitor_id} (activity/sedentary)
        elif len(parts) >= 4 and parts[0] == "office" and parts[2] == "activity":
            zone_id = parts[1]
            activity = payload.get("activity_level", "")
            if activity == "sedentary":
                duration = payload.get("duration_minutes", 0)
                if duration >= SEDENTARY_MINUTES:
                    zone = self._get_zone(zone_id)
                    zone.add_event(Event(
                        event_type="sedentary_alert",
                        description=f"長時間着座検知: {duration}分",
                        severity=1,
                        zone=zone_id,
                        data={"duration_minutes": duration},
                    ))

        # office/{zone}/task_report/{task_id}
        elif "task_report" in topic:
            zone_id = parts[1] if len(parts) >= 2 else "unknown"
            zone = self._get_zone(zone_id)
            zone.add_event(Event(
                event_type="task_report",
                description=f"タスク報告: {payload.get('title', '')} ({payload.get('report_status', '')})",
                severity=1 if payload.get("report_status") in ("needs_followup", "cannot_resolve") else 0,
                zone=zone_id,
                data=payload,
            ))

        # hems/personal/* topics (Phase 2 — data-bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "personal":
            self._update_personal(parts[2:], payload)

    def _update_sensor(self, zone_id: str, channel: str, value: float):
        zone = self._get_zone(zone_id)
        fusion_key = f"{zone_id}/{channel}"
        fusion = self._get_fusion(fusion_key)
        fusion.add_reading(value)
        fused = fusion.get_value()

        if fused is None:
            return

        env = zone.environment
        prev = getattr(env, channel, None) if hasattr(env, channel) else None

        if channel == "temperature":
            env.temperature = round(fused, 1)
        elif channel == "humidity":
            env.humidity = round(fused, 1)
        elif channel == "co2":
            env.co2 = round(fused, 0)
        elif channel == "pressure":
            env.pressure = round(fused, 1)
        elif channel == "light":
            env.light = round(fused, 1)
        elif channel == "voc":
            env.voc = round(fused, 1)

        env.last_update = time.time()

        # Generate events from threshold crossings
        self._check_thresholds(zone, channel, fused, prev)

    def _check_thresholds(self, zone: ZoneState, channel: str, value: float, prev: float | None):
        if channel == "co2":
            if value > CO2_CRITICAL and (prev is None or prev <= CO2_CRITICAL):
                zone.add_event(Event(
                    event_type="co2_critical",
                    description=f"CO2危険レベル: {int(value)}ppm",
                    severity=2,
                    zone=zone.zone_id,
                    data={"co2": value},
                ))
            elif value > CO2_HIGH and (prev is None or prev <= CO2_HIGH):
                zone.add_event(Event(
                    event_type="co2_high",
                    description=f"CO2上昇: {int(value)}ppm",
                    severity=1,
                    zone=zone.zone_id,
                    data={"co2": value},
                ))

        elif channel == "temperature":
            if value > TEMP_HIGH and (prev is None or prev <= TEMP_HIGH):
                zone.add_event(Event(
                    event_type="temp_high",
                    description=f"室温上昇: {value:.1f}度",
                    severity=1,
                    zone=zone.zone_id,
                    data={"temperature": value},
                ))
            elif value < TEMP_LOW and (prev is None or prev >= TEMP_LOW):
                zone.add_event(Event(
                    event_type="temp_low",
                    description=f"室温低下: {value:.1f}度",
                    severity=1,
                    zone=zone.zone_id,
                    data={"temperature": value},
                ))

    def _update_personal(self, path_parts: list[str], payload: dict):
        """Handle hems/personal/* topics (Phase 2 stub)."""
        # Will be expanded when data-bridge is implemented
        pass

    def get_llm_context(self) -> str:
        """Build text context for LLM from current world state."""
        if not self.zones:
            return ""

        lines = []
        for zone_id, zone in self.zones.items():
            env = zone.environment
            parts = [f"### {zone_id}"]

            if env.temperature is not None:
                parts.append(f"  温度: {env.temperature}度")
            if env.humidity is not None:
                parts.append(f"  湿度: {env.humidity}%")
            if env.co2 is not None:
                parts.append(f"  CO2: {int(env.co2)}ppm")
            if zone.occupancy and zone.occupancy.count > 0:
                parts.append(f"  在室: {zone.occupancy.count}人")

            lines.append("\n".join(parts))

        return "\n\n".join(lines)
