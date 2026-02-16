"""
World Model: Centralized state management for office environment.
"""
import json
import logging
import time
from typing import Dict, Optional, List
from .data_classes import ZoneState, EnvironmentData, OccupancyData, DeviceState, Event
from .sensor_fusion import SensorFusion

logger = logging.getLogger(__name__)


MAX_EVENTS_PER_ZONE = 100


class WorldModel:
    """
    Maintains the unified state of all zones in the office.
    Integrates sensor data, occupancy information, and device states.
    """

    def __init__(self):
        self.zones: Dict[str, ZoneState] = {}
        self.sensor_fusion = SensorFusion()

        # Cache for LLM context (optimization)
        self._llm_context_cache: Optional[str] = None
        self._cache_timestamp: float = 0

        # Sensor readings buffer for fusion
        self._sensor_readings: Dict[str, List] = {}

    @staticmethod
    def _add_event(zone: ZoneState, event: Event):
        """Append an event to a zone, trimming oldest entries if over limit."""
        zone.events.append(event)
        if len(zone.events) > MAX_EVENTS_PER_ZONE:
            zone.events = zone.events[-MAX_EVENTS_PER_ZONE:]
    
    def update_from_mqtt(self, topic: str, payload: dict):
        """
        Update world model from MQTT message.
        
        Args:
            topic: MQTT topic (e.g., "office/kitchen/sensor/temp_01/temperature")
            payload: Message payload (JSON dict)
        """
        parsed = self._parse_topic(topic)
        if not parsed:
            logger.debug(f"Ignoring non-office topic: {topic}")
            return
        
        zone_id = parsed["zone"]
        device_type = parsed["device_type"]
        device_id = parsed.get("device_id")
        channel = parsed.get("channel")
        
        # Create zone if it doesn't exist
        if zone_id not in self.zones:
            self.zones[zone_id] = ZoneState(zone_id=zone_id)
            logger.info(f"Created new zone: {zone_id}")
        
        zone = self.zones[zone_id]
        
        # Route to appropriate handler
        if device_type == "sensor":
            self._update_environment(zone, channel, payload, device_id)
        elif device_type in ("camera", "occupancy"):
            self._update_occupancy(zone, payload)
        elif device_type == "activity":
            self._update_activity(zone, payload)
        elif device_type == "task_report":
            self._handle_task_report(zone, payload, device_id)
        elif device_type in ["hvac", "light", "coffee_machine"]:
            self._update_device(zone, device_type, device_id, payload)
        
        zone.last_update = time.time()
        
        # Detect events based on state changes
        self._detect_events(zone)
        
        # Invalidate LLM context cache
        self._llm_context_cache = None
    
    def _parse_topic(self, topic: str) -> Optional[Dict[str, str]]:
        """
        Parse MQTT topic into components.
        
        Format: office/{zone}/{device_type}/{device_id}/{channel}
        Example: office/meeting_room_a/sensor/env_01/temperature
        
        Returns:
            Dict with zone, device_type, device_id, channel or None
        """
        parts = topic.split('/')
        if len(parts) < 3 or parts[0] != "office":
            return None
        
        return {
            "zone": parts[1],
            "device_type": parts[2],
            "device_id": parts[3] if len(parts) > 3 else None,
            "channel": parts[4] if len(parts) > 4 else None
        }
    
    def _update_environment(self, zone: ZoneState, channel: str, payload: dict, device_id: str):
        """Update environmental data for a zone."""
        current_time = time.time()
        
        # Extract value from payload
        value = payload.get(channel) or payload.get("value")
        if value is None:
            return
        
        # Store reading for sensor fusion
        reading_key = f"{zone.zone_id}:{channel}"
        if reading_key not in self._sensor_readings:
            self._sensor_readings[reading_key] = []
        
        self._sensor_readings[reading_key].append((device_id, value, current_time))
        
        # Keep only recent readings (last 10 minutes)
        self._sensor_readings[reading_key] = [
            r for r in self._sensor_readings[reading_key]
            if current_time - r[2] < 600
        ]
        
        # Fuse multiple sensor readings with appropriate sensor type
        fused_value = self.sensor_fusion.fuse_generic(
            self._sensor_readings[reading_key], 
            sensor_type=channel  # Pass sensor type for half-life selection
        )
        
        if fused_value is None:
            return
        
        # Update zone environment
        if channel == "temperature":
            zone.environment.temperature = fused_value
        elif channel == "humidity":
            zone.environment.humidity = fused_value
        elif channel == "co2":
            zone.environment.co2 = int(fused_value)
        elif channel == "illuminance":
            zone.environment.illuminance = fused_value
        elif channel == "pressure":
            zone.environment.pressure = fused_value
        elif channel == "gas_resistance":
            zone.environment.gas_resistance = int(fused_value)
        elif channel == "motion":
            zone.occupancy.pir_detected = bool(fused_value)
            zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
                vision_count=zone.occupancy.vision_count,
                pir_active=zone.occupancy.pir_detected
            )
        elif channel == "door":
            prev_door = getattr(zone, '_prev_door_state', None)
            door_open = bool(fused_value)
            if prev_door is not None and door_open != prev_door:
                event = Event(
                    timestamp=current_time,
                    event_type="door_opened" if door_open else "door_closed",
                    severity="info",
                    data={"device_id": device_id, "state": "open" if door_open else "closed"}
                )
                self._add_event(zone, event)
            zone._prev_door_state = door_open

        # Update timestamp
        zone.environment.timestamps[channel] = current_time
    
    def _update_occupancy(self, zone: ZoneState, payload: dict):
        """Update occupancy data from camera/vision system."""
        # Handle different payload formats
        if "person_count" in payload:
            zone.occupancy.vision_count = payload["person_count"]
        elif "count" in payload:
            zone.occupancy.vision_count = payload["count"]
        elif "occupancy" in payload:
            zone.occupancy.vision_count = 1 if payload["occupancy"] else 0
        
        # Activity distribution (from activity classification)
        if "activity_distribution" in payload:
            zone.occupancy.activity_distribution = payload["activity_distribution"]
        
        if "avg_motion_level" in payload:
            zone.occupancy.avg_motion_level = payload["avg_motion_level"]
        
        # Integrate with PIR if available
        zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
            vision_count=zone.occupancy.vision_count,
            pir_active=zone.occupancy.pir_detected
        )
    
    def _update_activity(self, zone: ZoneState, payload: dict):
        """Update activity data from Perception ActivityMonitor."""
        if "person_count" in payload:
            zone.occupancy.vision_count = payload["person_count"]
            zone.occupancy.person_count = self.sensor_fusion.integrate_occupancy(
                vision_count=payload["person_count"],
                pir_active=zone.occupancy.pir_detected
            )
        if "activity_level" in payload:
            zone.occupancy.activity_level = payload["activity_level"]
        if "activity_class" in payload:
            zone.occupancy.activity_class = payload["activity_class"]
        if "posture_duration_sec" in payload:
            zone.occupancy.posture_duration_sec = payload["posture_duration_sec"]
        if "posture_status" in payload:
            zone.occupancy.posture_status = payload["posture_status"]

    def _update_device(self, zone: ZoneState, device_type: str, device_id: str, payload: dict):
        """Update device state."""
        if device_id not in zone.devices:
            zone.devices[device_id] = DeviceState(
                device_id=device_id,
                device_type=device_type
            )
        
        device = zone.devices[device_id]
        
        # Update power state
        if "power_state" in payload:
            device.power_state = payload["power_state"]
        elif "state" in payload:
            device.power_state = payload["state"]
        
        # Update specific state
        if "mode" in payload or "target_temp" in payload:
            device.specific_state.update(payload)
    
    def _handle_task_report(self, zone: ZoneState, payload: dict, device_id: str):
        """Handle task completion report from dashboard."""
        event = Event(
            timestamp=time.time(),
            event_type="task_report",
            severity="info",
            data={
                "task_id": payload.get("task_id", device_id),
                "title": payload.get("title", ""),
                "report_status": payload.get("report_status", "unknown"),
                "completion_note": payload.get("completion_note", ""),
            }
        )
        self._add_event(zone, event)
        logger.info("Task report received: task_id=%s status=%s",
                     payload.get("task_id"), payload.get("report_status"))

    def _detect_events(self, zone: ZoneState):
        """Detect events based on state changes."""
        current_time = time.time()

        # Capture previous env values before they are updated below
        saved_prev_temperature = zone._prev_temperature
        saved_prev_humidity = zone._prev_humidity

        # Person count change
        if zone.occupancy.person_count != zone._prev_occupancy:
            if zone.occupancy.person_count > zone._prev_occupancy:
                event = Event(
                    timestamp=current_time,
                    event_type="person_entered",
                    severity="info",
                    data={"count": zone.occupancy.person_count}
                )
                self._add_event(zone, event)
                zone.occupancy.last_entry_time = current_time
            elif zone.occupancy.person_count < zone._prev_occupancy:
                event = Event(
                    timestamp=current_time,
                    event_type="person_exited",
                    severity="info",
                    data={"count": zone.occupancy.person_count}
                )
                self._add_event(zone, event)
                if zone.occupancy.person_count == 0:
                    zone.occupancy.last_exit_time = current_time
            
            zone._prev_occupancy = zone.occupancy.person_count
        
        # CO2 threshold exceeded
        if zone.environment.co2 and zone.environment.co2 > 1000:
            # Avoid duplicate events (don't create if one exists in last 10 minutes)
            recent_co2_events = [
                e for e in zone.events
                if e.event_type == "co2_threshold_exceeded"
                and current_time - e.timestamp < 600
            ]
            if not recent_co2_events:
                event = Event(
                    timestamp=current_time,
                    event_type="co2_threshold_exceeded",
                    severity="warning",
                    data={"value": zone.environment.co2}
                )
                self._add_event(zone, event)
        
        # Temperature spike
        if zone.environment.temperature and zone._prev_temperature:
            temp_change = abs(zone.environment.temperature - zone._prev_temperature)
            if temp_change > 3.0:  # 3°C change
                event = Event(
                    timestamp=current_time,
                    event_type="temp_spike",
                    severity="warning",
                    data={"value": zone.environment.temperature, "change": temp_change}
                )
                self._add_event(zone, event)
        
        zone._prev_temperature = zone.environment.temperature

        # Sedentary alert: static posture for >= 30 minutes with people present
        if (zone.occupancy.person_count > 0
                and zone.occupancy.posture_status == "static"
                and zone.occupancy.posture_duration_sec >= 1800):
            recent_sedentary = [
                e for e in zone.events
                if e.event_type == "sedentary_alert"
                and current_time - e.timestamp < 3600  # 1 hour cooldown
            ]
            if not recent_sedentary:
                event = Event(
                    timestamp=current_time,
                    event_type="sedentary_alert",
                    severity="info",
                    data={
                        "duration_sec": zone.occupancy.posture_duration_sec,
                        "person_count": zone.occupancy.person_count,
                    }
                )
                self._add_event(zone, event)

        # Sensor tamper: rapid environment change (use saved previous values)
        for channel, prev_val, threshold in [
            ("temperature", saved_prev_temperature, 5.0),
            ("humidity", saved_prev_humidity, 20.0),
        ]:
            current_val = getattr(zone.environment, channel, None)
            ts_key = channel
            current_ts = zone.environment.timestamps.get(ts_key)
            prev_ts = zone._prev_env_timestamps.get(ts_key)

            if (current_val is not None and prev_val is not None
                    and current_ts is not None and prev_ts is not None):
                dt = current_ts - prev_ts
                if 0 < dt <= 30:
                    change = abs(current_val - prev_val)
                    if change >= threshold:
                        recent_tamper = [
                            e for e in zone.events
                            if e.event_type == "sensor_tamper"
                            and current_time - e.timestamp < 300  # 5 min cooldown
                        ]
                        if not recent_tamper:
                            event = Event(
                                timestamp=current_time,
                                event_type="sensor_tamper",
                                severity="warning",
                                data={
                                    "channel": channel,
                                    "change": change,
                                    "duration_sec": dt,
                                    "value": current_val,
                                }
                            )
                            self._add_event(zone, event)

            if current_val is not None:
                if channel == "humidity":
                    zone._prev_humidity = current_val
            if current_ts is not None:
                zone._prev_env_timestamps[ts_key] = current_ts

        # Limit event history size (keep last 50 events per zone)
        if len(zone.events) > 50:
            zone.events = zone.events[-50:]
    
    def get_zone(self, zone_id: str) -> Optional[ZoneState]:
        """Get state of a specific zone."""
        return self.zones.get(zone_id)
    
    def get_all_zones(self) -> Dict[str, ZoneState]:
        """Get all zones."""
        return self.zones
    
    def get_llm_context(self) -> str:
        """
        Generate optimized context string for LLM.
        Cached for 5 seconds to avoid redundant generation.
        """
        current_time = time.time()
        
        # Return cached context if fresh
        if self._llm_context_cache and (current_time - self._cache_timestamp < 5):
            return self._llm_context_cache
        
        context_parts = []

        # Collect alerts for abnormal values across all zones
        alerts = []
        for zone_id, zone in sorted(self.zones.items()):
            env = zone.environment
            if env.temperature is not None:
                if env.temperature > 26:
                    alerts.append(f"⚠️ [{zone_id}] 高温: {env.temperature:.1f}℃（基準: 18-26℃）")
                elif env.temperature < 18:
                    alerts.append(f"⚠️ [{zone_id}] 低温: {env.temperature:.1f}℃（基準: 18-26℃）")
            if env.co2 is not None and env.co2 > 1000:
                alerts.append(f"⚠️ [{zone_id}] CO2高濃度: {env.co2}ppm（基準: 1000ppm以下）")
            if env.humidity is not None:
                if env.humidity > 60:
                    alerts.append(f"⚠️ [{zone_id}] 高湿度: {env.humidity:.0f}%（基準: 30-60%）")
                elif env.humidity < 30:
                    alerts.append(f"⚠️ [{zone_id}] 低湿度: {env.humidity:.0f}%（基準: 30-60%）")

        if alerts:
            context_parts.append("### アラート（要対応）\n" + "\n".join(alerts))

        for zone_id, zone in sorted(self.zones.items()):
            summary = f"### {zone_id}\n"
            
            # Occupancy and activity
            if zone.occupancy.person_count > 0:
                summary += f"- 状態: {zone.occupancy.activity_summary}\n"
                if zone.occupancy.avg_motion_level > 0:
                    summary += f"- 活動レベル: {zone.occupancy.avg_motion_level:.2f}\n"
                if zone.occupancy.posture_status != "unknown":
                    minutes = int(zone.occupancy.posture_duration_sec / 60)
                    summary += f"- 姿勢状態: {zone.occupancy.posture_status} ({minutes}分間)\n"
            else:
                summary += "- 状態: 無人\n"
            
            # Environment
            if zone.environment.temperature is not None:
                summary += f"- 気温: {zone.environment.temperature:.1f}℃ ({zone.environment.thermal_comfort})\n"
            
            if zone.environment.humidity is not None:
                summary += f"- 湿度: {zone.environment.humidity:.0f}%\n"
            
            if zone.environment.co2 is not None:
                summary += f"- CO2: {zone.environment.co2}ppm"
                if zone.environment.is_stuffy:
                    summary += " ⚠️換気必要\n"
                else:
                    summary += "\n"
            
            if zone.environment.pressure is not None:
                summary += f"- 気圧: {zone.environment.pressure:.1f}hPa\n"

            if zone.environment.illuminance is not None:
                summary += f"- 照度: {zone.environment.illuminance:.0f}lux\n"
            
            # Devices
            if zone.devices:
                summary += "- デバイス:\n"
                for device_id, device in zone.devices.items():
                    summary += f"  - {device.device_type} ({device_id}): {device.power_state}\n"
            
            # Recent events (last 10 minutes)
            recent_events = [
                e for e in zone.events
                if current_time - e.timestamp < 600
            ]
            if recent_events:
                summary += "- 最近のイベント:\n"
                for event in recent_events[-3:]:  # Last 3 events
                    summary += f"  - {event.description}\n"
            
            context_parts.append(summary)
        
        context = "\n".join(context_parts)
        
        # Update cache
        self._llm_context_cache = context
        self._cache_timestamp = current_time
        
        return context
