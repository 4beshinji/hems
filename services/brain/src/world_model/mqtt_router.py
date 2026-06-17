"""WorldModel mixin extracted from the facade module."""

import time

from loguru import logger

from .data_classes import Event, OccupancyData
from .sanitizer import _sanitize_text
from .sensor_fusion import ChannelType, classify_channel
from .sensor_validation import validate_sensor_value


class MqttRouterMixin:
    def update_from_mqtt(self, topic: str, payload: dict):
        """Parse MQTT topic and update world state."""
        parts = topic.split("/")

        # W3.8c: hems/sensors/{zone}/{device_type}/{device_id}/{channel}
        # Canonical prefix for physical sensor / camera / activity telemetry.
        if len(parts) >= 5 and parts[0] == "hems" and parts[1] == "sensors":
            # Remap: parts[2]=zone, parts[3]=device_type, parts[4]=device_id
            # parts[5]=channel (sensor/camera only; activity has no channel part)
            zone_id = parts[2]
            device_type = parts[3]
            device_id = parts[4]
            channel = parts[5] if len(parts) >= 6 else ""
            value = payload.get(channel) or payload.get("value")
            if device_type == "sensor":
                if len(parts) < 6:
                    return  # channel part required for sensor topics
                if value is not None:
                    ch_type = classify_channel(channel)
                    if ch_type == ChannelType.ANALOG:
                        ok, coerced = validate_sensor_value(channel, value)
                        if not ok:
                            logger.warning(
                                f"Rejected sensor value (not fused): topic={topic} channel={channel} raw={value!r}"
                            )
                            return
                        self._update_sensor(zone_id, channel, coerced)
                    elif ch_type == ChannelType.EVENT:
                        self._update_event_channel(zone_id, channel, value, device_id)
                    elif ch_type == ChannelType.STATE:
                        self._update_state_channel(zone_id, channel, value, device_id)
            elif device_type == "camera" and len(parts) >= 6:
                count = payload.get("person_count", payload.get("count", 0))
                zone = self._get_zone(zone_id)
                zone.occupancy = OccupancyData(count=int(count), last_update=time.time())
            elif device_type == "activity":
                zone = self._get_zone(zone_id)
                activity = payload.get("activity_level", "")
                if isinstance(activity, float):
                    zone.occupancy.activity_level = activity
                if "activity_class" in payload:
                    zone.occupancy.activity_class = payload["activity_class"]
                if "posture" in payload:
                    zone.occupancy.posture = payload["posture"]
                if "posture_duration_sec" in payload:
                    zone.occupancy.posture_duration_sec = payload["posture_duration_sec"]
                if "posture_status" in payload:
                    zone.occupancy.posture_status = payload["posture_status"]
                if activity == "sedentary":
                    duration = payload.get("duration_minutes", 0)
                    if duration >= self.thresholds.sedentary_minutes:
                        zone.add_event(
                            Event(
                                event_type="sedentary_alert",
                                description=f"長時間着座検知: {duration}分",
                                severity=1,
                                zone=zone_id,
                                data={"duration_minutes": duration},
                            )
                        )

        # office/{zone}/task_report/{task_id} (backend → brain, W3.8c 時点では旧プレフィックスのまま)
        elif "task_report" in topic:
            zone_id = parts[1] if len(parts) >= 2 else "unknown"
            zone = self._get_zone(zone_id)
            safe_title = _sanitize_text(payload.get("title", ""), 100)
            safe_status = _sanitize_text(payload.get("report_status", ""), 30)
            zone.add_event(
                Event(
                    event_type="task_report",
                    description=f"タスク報告: {safe_title} ({safe_status})",
                    severity=1 if payload.get("report_status") in ("needs_followup", "cannot_resolve") else 0,
                    zone=zone_id,
                    data=payload,
                )
            )

        # hems/pc/* topics (OpenClaw bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "pc":
            self._update_pc_state(parts[2:], payload)

        # hems/services/{name}/status (Service Monitor)
        elif parts[0] == "hems" and len(parts) >= 4 and parts[1] == "services":
            self._update_service_state(parts[2], parts[3], payload)

        # hems/ha/bridge/status — canonical bridge status (W3.3)
        elif (
            parts[0] == "hems"
            and len(parts) == 4
            and parts[1] == "ha"
            and parts[2] == "bridge"
            and parts[3] == "status"
        ):
            self.home_devices.bridge_connected = payload.get("connected", False)

        # hems/biometric/bridge/status — canonical bridge status (W3.3)
        elif (
            parts[0] == "hems"
            and len(parts) == 4
            and parts[1] == "biometric"
            and parts[2] == "bridge"
            and parts[3] == "status"
        ):
            bio = self.biometric_state
            bio.bridge_connected = payload.get("connected", False)
            if payload.get("provider"):
                bio.provider = payload["provider"]

        # hems/home/* topics (HA bridge — also handles legacy hems/home/bridge/status)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "home":
            self._update_home_device(parts[2:], payload)

        # hems/gas/* topics (GAS bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "gas":
            self._update_gas_state(parts[2:], payload)

        # hems/perception/vlm/* topics (VLM scene analysis)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "perception":
            self._update_vlm(parts[2:], payload)

        # hems/news/* topics (news-bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "news":
            self._update_news_state(parts[2], payload)

        # hems/weather/* topics (weather-bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "weather":
            self._update_weather_state(parts[2], payload)

        # hems/shopping/list snapshot (backend) — keeps ShoppingState live
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "shopping":
            self._update_shopping_state(parts[2], payload)

        # hems/personal/* topics (Phase 2 — data-bridge)
        elif parts[0] == "hems" and len(parts) >= 3 and parts[1] == "personal":
            self._update_personal(parts[2:], payload)

        # hems/tapo/{vendor_ref}/state → power metering + on/off state
        elif parts[0] == "hems" and len(parts) >= 4 and parts[1] == "tapo" and parts[3] == "state":
            self._update_tapo_state(parts[2], payload)

        # zigbee2mqtt/{device} → sensor channels + on/off state (Z2M direct)
        elif parts[0] == "zigbee2mqtt" and len(parts) >= 2 and not parts[1].startswith("bridge"):
            self._update_zigbee_state(parts[1], payload)
