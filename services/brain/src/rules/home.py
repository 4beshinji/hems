"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""

import rule_engine as _rule_engine


class HomeRulesMixin:
    def _evaluate_home_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate home automation rules (vendor-agnostic via Device Registry)."""
        actions = []
        hour = _rule_engine.datetime.now().hour

        # --- 1. Sleep detection → lights off ---
        if hour >= 23 or hour < 5:
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (
                    occ.count > 0
                    and occ.activity_class == "idle"
                    and occ.posture_status == "static"
                    and occ.posture_duration_sec > 600
                ):
                    lights_on = [d for d in self._get_devices(device_class="light") if self._device_is_on(d)]
                    if lights_on and self._check_cooldown_daily(f"ha_sleep_detect_{zone_id}", now):
                        for d in lights_on:
                            actions.append(self._make_action(d["device_id"], "off"))
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "おやすみなさい。照明を消しますね。",
                                    "zone": zone_id,
                                    "tone": "caring",
                                },
                            }
                        )

        # --- 2. Pre-arrival HVAC ---
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            predicted_arrival = self.schedule_learner.predict_next_arrival(calendar_events)
            if predicted_arrival:
                minutes_until = (predicted_arrival - now) / 60
                # Multi-source "away" check (camera + PIR + motion + PC + HR)
                # so we don't pre-heat the house when the user is already home
                # but simply out of camera view.
                all_away = not world_model.is_anyone_home()

                if all_away and 0 < minutes_until <= 30:
                    if self._check_cooldown("ha_prearrival_hvac", now):
                        month = _rule_engine.datetime.now().month
                        if 6 <= month <= 9:
                            mode, temp = "cool", 26
                        elif month <= 3 or month >= 11:
                            mode, temp = "heat", 22
                        else:
                            mode, temp = "auto", 24

                        for d in self._get_devices(device_class="climate"):
                            actions.append(
                                self._make_action(d["device_id"], "set_temperature", {"value": temp, "mode": mode})
                            )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"もうすぐ帰宅ですね。エアコンを{mode}モード{temp}度でつけました。",
                                    "zone": "home",
                                    "tone": "caring",
                                },
                            }
                        )

        # --- 3. Wake-up curtain → natural light ---
        if self.schedule_learner:
            calendar_events = None
            if world_model.gas_state.bridge_connected:
                calendar_events = world_model.gas_state.calendar_events

            wake_time = self.schedule_learner.get_wake_time(calendar_events)
            if wake_time:
                minutes_until_wake = (wake_time - now) / 60
                if 0 < minutes_until_wake <= 60:
                    covers = self._get_devices(device_class="cover")
                    closed_covers = [d for d in covers if not (d.get("last_state") or {}).get("position", 0) > 0]
                    if closed_covers and self._check_cooldown_daily("ha_wake_curtain", now):
                        for d in closed_covers:
                            actions.append(self._make_action(d["device_id"], "set_position", {"value": 100}))

        # --- 4. Wake-up detection → lights on + morning greeting ---
        if 5 <= hour < 10:
            for zone_id, zone in world_model.zones.items():
                occ = zone.occupancy
                if (
                    occ.count > 0
                    and occ.activity_class in ("low", "moderate", "high")
                    and self._check_cooldown_daily(f"ha_wake_detect_{zone_id}", now)
                ):
                    lights_off = [d for d in self._get_devices(device_class="light") if not self._device_is_on(d)]
                    if lights_off:
                        for d in lights_off:
                            actions.append(self._make_action(d["device_id"], "on"))
                            actions.append(self._make_action(d["device_id"], "set_brightness", {"value": 255}))
                            if "color_temp" in (d.get("capabilities") or []):
                                actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": 400}))
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": "おはようございます。",
                                "zone": zone_id,
                                "tone": "neutral",
                            },
                        }
                    )

        return actions

    def _evaluate_circadian_lighting(self, world_model, now: float) -> list[dict]:
        """Adjust light color temperature based on time of day (circadian rhythm)."""
        if not self.thresholds.circadian_enabled:
            return []
        if not self._check_cooldown("circadian_update", now):
            return []

        lights_on = [
            d for d in self._get_devices(device_class="light", capability="color_temp") if self._device_is_on(d)
        ]
        if not lights_on:
            return []

        hour = _rule_engine.datetime.now().hour + _rule_engine.datetime.now().minute / 60.0
        target_mirek, target_brightness_pct = self._interpolate_circadian(hour)
        target_brightness = int(target_brightness_pct / 100 * 255)

        actions = []
        for d in lights_on:
            state = d.get("last_state") or {}
            ct = state.get("color_temp", 0)
            br = state.get("brightness", 0)
            if ct and abs(ct - target_mirek) < 20 and abs(br - target_brightness) < 15:
                continue
            actions.append(self._make_action(d["device_id"], "set_brightness", {"value": target_brightness}))
            actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": target_mirek}))
        return actions

    def _interpolate_circadian(self, hour: float) -> tuple[int, int]:
        """Interpolate circadian curve for given fractional hour."""
        curve = self.thresholds.circadian_curve
        # Find surrounding points
        for i in range(len(curve) - 1):
            if curve[i][0] <= hour < curve[i + 1][0]:
                h0, m0, b0 = curve[i]
                h1, m1, b1 = curve[i + 1]
                t = (hour - h0) / (h1 - h0)
                return int(m0 + (m1 - m0) * t), int(b0 + (b1 - b0) * t)
        # After last point, use last value
        return curve[-1][1], curve[-1][2]

    def _evaluate_absence_lighting(self, world_model, now: float) -> list[dict]:
        """Randomly toggle lights during extended absence to simulate presence."""
        if not self.thresholds.absence_lighting_enabled:
            return []

        # Check every presence signal, not just the camera — otherwise the
        # absence-lighting prank can fire while the occupant is quietly at the PC.
        all_empty = bool(world_model.zones) and not world_model.is_anyone_home()
        if not all_empty:
            actions = []
            for did in list(self._absence_light_state.keys()):
                if self._absence_light_state[did]:
                    actions.append(self._make_action(did, "off"))
            self._absence_light_state.clear()
            return actions

        hour = _rule_engine.datetime.now().hour
        if not (self.thresholds.absence_lighting_start_hour <= hour < self.thresholds.absence_lighting_end_hour):
            return []

        if not self._check_cooldown("absence_lighting", now):
            return []
        self._cooldowns["absence_lighting"] = (
            now
            - self.COOLDOWN_SECONDS
            + _rule_engine.random.randint(
                self.thresholds.absence_lighting_interval // 2, self.thresholds.absence_lighting_interval
            )
        )

        all_lights = [d["device_id"] for d in self._get_devices(device_class="light")]
        if not all_lights:
            return []

        actions = []
        targets = _rule_engine.random.sample(all_lights, min(2, len(all_lights)))
        for did in targets:
            currently_simulated = self._absence_light_state.get(did, False)
            new_state = not currently_simulated
            self._absence_light_state[did] = new_state
            if new_state:
                actions.append(self._make_action(did, "on"))
                actions.append(
                    self._make_action(did, "set_brightness", {"value": _rule_engine.random.randint(100, 200)})
                )
            else:
                actions.append(self._make_action(did, "off"))

        return actions
