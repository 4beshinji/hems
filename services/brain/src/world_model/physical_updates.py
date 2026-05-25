"""WorldModel mixin extracted from the facade module."""

from . import world_model as _world_model

# Analog sensor channels that map 1:1 onto EnvironmentData fields, with the
# rounding precision applied to the fused value (default 1 decimal).
_SENSOR_FIELDS = ("temperature", "humidity", "co2", "pressure", "light", "voc", "pm25", "soil_moisture")
_CHANNEL_PRECISION = {"co2": 0}


class PhysicalUpdatesMixin:
    def _update_sensor(self, zone_id: str, channel: str, value: float):
        zone = self._get_zone(zone_id)
        fusion_key = f"{zone_id}/{channel}"
        fusion = self._get_fusion(fusion_key)
        fusion.add_reading(value)
        fused = fusion.get_value()

        if fused is None:
            return

        env = zone.environment
        prev = getattr(env, channel, None)

        if channel in _SENSOR_FIELDS:
            setattr(env, channel, round(fused, _CHANNEL_PRECISION.get(channel, 1)))

        # Trend detection
        now = _world_model.time.time()
        self._trend_detector.record(fusion_key, fused, now)
        env.trends[channel] = self._trend_detector.get_trend(fusion_key, fused, channel)

        env.last_update = now
        env.channel_last_seen[channel] = now

        # Generate events from threshold crossings
        self._check_thresholds(zone, channel, fused, prev)

    def _update_event_channel(self, zone_id: str, channel: str, value, device_id: str):
        """Process event/pulse sensor data (motion, vibration)."""
        zone = self._get_zone(zone_id)
        reading_key = f"{zone_id}:{channel}"
        now = _world_model.time.time()

        if channel == "motion_count":
            self._event_counter.record_count(reading_key, int(value), now)
            if int(value) > 0:
                zone.occupancy.last_motion_ts = now
        elif value:
            self._event_counter.record_event(reading_key, now)
            zone.occupancy.last_motion_ts = now

        # Aggregate all motion-type events for this zone
        total = sum(self._event_counter.get_count(f"{zone_id}:{ch}") for ch in ("motion", "motion_count", "vibration"))
        zone.occupancy.motion_event_count_5min = total
        zone.occupancy.motion_frequency_per_min = total / 5.0
        zone.occupancy.last_update = now

    def _update_state_channel(self, zone_id: str, channel: str, value, device_id: str):
        """Process binary state sensor data (door, presence, contact, occupancy)."""
        zone = self._get_zone(zone_id)
        bool_value = bool(value)
        state_key = f"{zone_id}:{device_id}:{channel}"
        now = _world_model.time.time()
        changed = self._state_tracker.update(state_key, bool_value, now)

        if channel == "door":
            state_info = self._state_tracker.get_state(state_key)
            if state_info:
                zone.occupancy.door_states[device_id] = {
                    "open": state_info["state"],
                    "duration_sec": state_info["duration_sec"],
                    "changes_1h": state_info["changes_1h"],
                }
            if changed:
                zone.add_event(
                    _world_model.Event(
                        event_type="door_opened" if bool_value else "door_closed",
                        description=f"ドアが{'開' if bool_value else '閉'}きました ({device_id})",
                        severity=0,
                        zone=zone_id,
                        data={"device_id": device_id, "state": bool_value},
                    )
                )

        elif channel == "contact":
            # contact=false → door open (contact sensor logic inverted)
            door_open = not bool_value
            door_key = f"{zone_id}:{device_id}:door"
            self._state_tracker.update(door_key, door_open, now)
            state_info = self._state_tracker.get_state(door_key)
            if state_info:
                zone.occupancy.door_states[device_id] = {
                    "open": state_info["state"],
                    "duration_sec": state_info["duration_sec"],
                    "changes_1h": state_info["changes_1h"],
                }

        elif channel in ("presence", "occupancy"):
            zone.occupancy.presence_state = bool_value
            state_info = self._state_tracker.get_state(state_key)
            if state_info:
                zone.occupancy.presence_duration_sec = state_info["duration_sec"]
            # Each activation also counts as a motion event for the zone
            if bool_value:
                self._event_counter.record_event(f"{zone_id}:motion", now)
                total = sum(
                    self._event_counter.get_count(f"{zone_id}:{ch}") for ch in ("motion", "motion_count", "vibration")
                )
                zone.occupancy.motion_event_count_5min = total
                zone.occupancy.motion_frequency_per_min = total / 5.0
                zone.occupancy.last_motion_ts = now
            zone.occupancy.last_update = now

    def _check_thresholds(self, zone: _world_model.ZoneState, channel: str, value: float, prev: float | None):
        zid = zone.zone_id
        if channel == "co2":
            # Auto-clear suppression when CO2 returns to normal
            if value <= _world_model.CO2_HIGH:
                self.clear_suppression(zid, "co2_high")
                self.clear_suppression(zid, "co2_critical")

            if value > _world_model.CO2_CRITICAL and (prev is None or prev <= _world_model.CO2_CRITICAL):
                if not self._is_suppressed(zid, "co2_critical"):
                    zone.add_event(
                        _world_model.Event(
                            event_type="co2_critical",
                            description=f"CO2危険レベル: {int(value)}ppm",
                            severity=2,
                            zone=zid,
                            data={"co2": value},
                        )
                    )
            elif value > _world_model.CO2_HIGH and (prev is None or prev <= _world_model.CO2_HIGH):
                if not self._is_suppressed(zid, "co2_high"):
                    zone.add_event(
                        _world_model.Event(
                            event_type="co2_high",
                            description=f"CO2上昇: {int(value)}ppm",
                            severity=1,
                            zone=zid,
                            data={"co2": value},
                        )
                    )

        elif channel == "temperature":
            # Auto-clear suppression when temperature returns to normal range
            if _world_model.TEMP_LOW <= value <= _world_model.TEMP_HIGH:
                self.clear_suppression(zid, "temp_high")
                self.clear_suppression(zid, "temp_low")

            if value > _world_model.TEMP_HIGH and (prev is None or prev <= _world_model.TEMP_HIGH):
                if not self._is_suppressed(zid, "temp_high"):
                    zone.add_event(
                        _world_model.Event(
                            event_type="temp_high",
                            description=f"室温上昇: {value:.1f}度",
                            severity=1,
                            zone=zid,
                            data={"temperature": value},
                        )
                    )
            elif value < _world_model.TEMP_LOW and (prev is None or prev >= _world_model.TEMP_LOW):
                if not self._is_suppressed(zid, "temp_low"):
                    zone.add_event(
                        _world_model.Event(
                            event_type="temp_low",
                            description=f"室温低下: {value:.1f}度",
                            severity=1,
                            zone=zid,
                            data={"temperature": value},
                        )
                    )

    def _update_tapo_state(self, vendor_ref: str, payload: dict):
        """Tapo plug state → feed power metering into zone sensors if provided.

        Tapo P110 exposes power_watts/voltage/current/energy_kwh. Feed power
        readings into timeseries for the EnergyPanel; the device itself is
        tracked in the Device Registry (auto-register happens separately).
        """
        zone_id = payload.get("zone", "home")
        power = payload.get("power_watts")
        if power is not None:
            zone = self._get_zone(zone_id)
            zone.add_event(
                _world_model.Event(
                    event_type="tapo_power",
                    description=f"{vendor_ref}: {power:.1f}W",
                    severity=0,
                    zone=zone_id,
                    data={"power_watts": float(power), "vendor_ref": vendor_ref},
                )
            )

    def _update_zigbee_state(self, vendor_ref: str, payload: dict):
        """Zigbee2MQTT device update → feed sensor channels into zone state.

        Z2M publishes the full payload per device (state + sensor readings).
        Device auto-registration is handled separately via parse_mqtt;
        here we route sensor values to the zone using channel classification.
        """
        zone_id = payload.get("zone")
        if not zone_id:
            return

        _SKIP_KEYS = {
            "zone",
            "linkquality",
            "battery",
            "voltage",
            "update",
            "update_available",
            "last_seen",
            "elapsed",
            "state",
            "power_on_behavior",
        }
        device_id = f"zigbee.{vendor_ref}"

        for key, value in payload.items():
            if key in _SKIP_KEYS or value is None:
                continue
            ch_type = _world_model.classify_channel(key)
            if ch_type == _world_model.ChannelType.ANALOG:
                ok, coerced = _world_model.validate_sensor_value(key, value)
                if not ok:
                    _world_model.logger.warning(
                        f"Rejected zigbee sensor value (not fused): device={device_id} channel={key} raw={value!r}"
                    )
                    continue
                mapped = "light" if key == "illuminance" else key
                self._update_sensor(zone_id, mapped, coerced)
            elif ch_type == _world_model.ChannelType.EVENT:
                self._update_event_channel(zone_id, key, value, device_id)
            elif ch_type == _world_model.ChannelType.STATE:
                self._update_state_channel(zone_id, key, value, device_id)

    def _update_home_device(self, path_parts: list[str], payload: dict):
        """Handle hems/home/{zone}/{domain}/{entity_id}/state topics from HA bridge."""
        # hems/home/bridge/status
        if len(path_parts) >= 2 and path_parts[0] == "bridge" and path_parts[1] == "status":
            self.home_devices.bridge_connected = payload.get("connected", False)
            return

        # hems/home/{zone}/{domain}/{entity_id}/state
        if len(path_parts) < 3:
            return

        zone_id = path_parts[0]
        domain = path_parts[1] if len(path_parts) >= 2 else ""
        entity_id = path_parts[2] if len(path_parts) >= 3 else ""
        now = _world_model.time.time()
        hd = self.home_devices
        hd.bridge_connected = True

        if domain == "light":
            hd.lights[entity_id] = _world_model.LightState(
                entity_id=entity_id,
                on=payload.get("on", payload.get("state") == "on"),
                brightness=payload.get("brightness", 0),
                color_temp=payload.get("color_temp", 0),
                last_update=now,
            )
        elif domain == "climate":
            hd.climates[entity_id] = _world_model.ClimateState(
                entity_id=entity_id,
                mode=payload.get("hvac_mode", payload.get("state", "off")),
                target_temp=payload.get("temperature", 0) or 0,
                current_temp=payload.get("current_temperature", 0) or 0,
                fan_mode=payload.get("fan_mode", "auto"),
                last_update=now,
            )
        elif domain == "cover":
            hd.covers[entity_id] = _world_model.CoverState(
                entity_id=entity_id,
                position=payload.get("current_position", 0),
                is_open=payload.get("is_open", payload.get("state") == "open"),
                last_update=now,
            )
        elif domain == "switch":
            hd.switches[entity_id] = payload.get("on", payload.get("state") == "on")
        elif domain == "binary_sensor":
            raw_state = payload.get("state", "off")
            new_state = raw_state in ("on", "detected", "open", "wet")
            existing = hd.binary_sensors.get(entity_id)
            prev_state = existing.state if existing else False
            changed = existing is None or prev_state != new_state
            device_class = payload.get("device_class", existing.device_class if existing else "")
            hd.binary_sensors[entity_id] = _world_model.BinarySensorState(
                entity_id=entity_id,
                state=new_state,
                device_class=device_class,
                last_update=now,
                last_changed=now if changed else (existing.last_changed if existing else now),
                previous_state=prev_state,
            )
            if changed and existing is not None:
                self._handle_binary_sensor_event(hd, entity_id, new_state, prev_state, device_class)
            # Aggregate motion/occupancy/presence sensors into zone occupancy so
            # PIR-style devices (HA, SwitchBot, Zigbee via HA) contribute to
            # presence inference, not just the camera.
            if device_class in ("motion", "occupancy", "presence"):
                channel = "motion" if device_class == "motion" else "presence"
                if channel == "motion" and new_state:
                    self._update_event_channel(zone_id, "motion", True, entity_id)
                elif channel == "presence":
                    # Use state channel semantics for occupancy/presence class
                    self._update_state_channel(zone_id, "presence", new_state, entity_id)
        elif domain == "sensor":
            try:
                raw_val = payload.get("state", payload.get("value", 0))
                value = float(raw_val) if raw_val not in (None, "unknown", "unavailable", "") else 0
            except (ValueError, TypeError):
                value = 0
            existing = hd.sensors.get(entity_id)
            prev_value = existing.value if existing else 0
            device_class = payload.get("device_class", existing.device_class if existing else "")
            hd.sensors[entity_id] = _world_model.HASensorState(
                entity_id=entity_id,
                value=value,
                unit=payload.get("unit_of_measurement", payload.get("unit", existing.unit if existing else "")),
                device_class=device_class,
                last_update=now,
                previous_value=prev_value,
            )
            if device_class == "power":
                self._check_power_thresholds(hd, entity_id, value, prev_value)

    def _handle_binary_sensor_event(self, hd, entity_id: str, new_state: bool, prev_state: bool, device_class: str):
        """Generate events for binary sensor state transitions."""
        if device_class in ("door", "window"):
            event_type = f"{device_class}_{'opened' if new_state else 'closed'}"
            desc = f"{'開' if new_state else '閉'}きました ({entity_id})"
            hd.add_event(
                _world_model.Event(
                    event_type=event_type,
                    description=desc,
                    severity=0,
                    data={"entity_id": entity_id, "device_class": device_class, "state": new_state},
                )
            )
        elif device_class == "moisture" and new_state:
            hd.add_event(
                _world_model.Event(
                    event_type="moisture_detected",
                    description=f"水漏れ検知 ({entity_id})",
                    severity=2,
                    data={"entity_id": entity_id},
                )
            )
        elif device_class == "vibration" and not new_state:
            hd.add_event(
                _world_model.Event(
                    event_type="vibration_stopped",
                    description=f"振動停止 ({entity_id})",
                    severity=0,
                    data={"entity_id": entity_id},
                )
            )

    def _check_power_thresholds(self, hd, entity_id: str, value: float, prev_value: float):
        """Generate event when power drops to idle level."""
        if prev_value > _world_model.POWER_IDLE_WATTS and value <= _world_model.POWER_IDLE_WATTS:
            hd.add_event(
                _world_model.Event(
                    event_type="power_drop_idle",
                    description=f"電力がアイドルに低下 ({entity_id}: {prev_value:.1f}W → {value:.1f}W)",
                    severity=0,
                    data={"entity_id": entity_id, "value": value, "previous_value": prev_value},
                )
            )
