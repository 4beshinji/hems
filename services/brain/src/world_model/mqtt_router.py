"""WorldModel mixin extracted from the facade module."""

from . import world_model as _world_model


class MqttRouterMixin:
    def update_from_mqtt(self, topic: str, payload: dict):
        """Parse MQTT topic and update world state."""
        parts = topic.split("/")

        # office/{zone}/sensor/{device_id}/{channel}
        if len(parts) >= 5 and parts[0] == "office" and parts[2] == "sensor":
            zone_id = parts[1]
            device_id = parts[3]
            channel = parts[4]
            value = payload.get(channel) or payload.get("value")
            if value is not None:
                ch_type = _world_model.classify_channel(channel)
                if ch_type == _world_model.ChannelType.ANALOG:
                    # Input trust boundary: reject non-numeric / out-of-range
                    # injections before they reach sensor fusion + LLM context.
                    ok, coerced = _world_model.validate_sensor_value(channel, value)
                    if not ok:
                        _world_model.logger.warning(
                            f"Rejected sensor value (not fused): topic={topic} channel={channel} raw={value!r}"
                        )
                        return
                    self._update_sensor(zone_id, channel, coerced)
                elif ch_type == _world_model.ChannelType.EVENT:
                    self._update_event_channel(zone_id, channel, value, device_id)
                elif ch_type == _world_model.ChannelType.STATE:
                    self._update_state_channel(zone_id, channel, value, device_id)

        # office/{zone}/camera/{camera_id}/status (occupancy)
        elif len(parts) >= 5 and parts[0] == "office" and parts[2] == "camera":
            zone_id = parts[1]
            count = payload.get("person_count", payload.get("count", 0))
            zone = self._get_zone(zone_id)
            zone.occupancy = _world_model.OccupancyData(count=int(count), last_update=_world_model.time.time())

        # office/{zone}/activity/{monitor_id} (activity/sedentary)
        elif len(parts) >= 4 and parts[0] == "office" and parts[2] == "activity":
            zone_id = parts[1]
            zone = self._get_zone(zone_id)
            activity = payload.get("activity_level", "")
            # Update activity fields on _world_model.OccupancyData
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
            # Legacy: sedentary string value
            if activity == "sedentary":
                duration = payload.get("duration_minutes", 0)
                if duration >= self.thresholds.sedentary_minutes:
                    zone.add_event(
                        _world_model.Event(
                            event_type="sedentary_alert",
                            description=f"長時間着座検知: {duration}分",
                            severity=1,
                            zone=zone_id,
                            data={"duration_minutes": duration},
                        )
                    )

        # office/{zone}/task_report/{task_id}
        elif "task_report" in topic:
            zone_id = parts[1] if len(parts) >= 2 else "unknown"
            zone = self._get_zone(zone_id)
            safe_title = _world_model._sanitize_text(payload.get("title", ""), 100)
            safe_status = _world_model._sanitize_text(payload.get("report_status", ""), 30)
            zone.add_event(
                _world_model.Event(
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

        # hems/home/* topics (HA bridge)
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
