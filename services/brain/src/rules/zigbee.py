"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""


class ZigbeeRulesMixin:
    def _evaluate_zigbee_sensor_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate Zigbee binary_sensor and sensor rules."""
        actions = []
        hd = world_model.home_devices

        # --- Z1: Moisture emergency ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"zigbee_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"【緊急】水漏れ検知: {name}",
                                "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                                "urgency": 4,
                                "zone": "home",
                                "task_type": ["water_leak"],
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"緊急！{name}で水漏れを検知しました！すぐに確認してください！",
                                "zone": "home",
                                "tone": "alert",
                            },
                        }
                    )

        # --- Z2: Door arrival/departure ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "door" and not bs.state and bs.previous_state:
                # door closed transition (was open, now closed)
                if now - bs.last_changed > 60:
                    continue  # too old
                if self._check_cooldown(f"zigbee_door_{eid}", now):
                    any_occupied = world_model.is_anyone_home()
                    if any_occupied:
                        # Arrival: turn on lights
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "おかえりなさい。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                        for d in self._get_devices(device_class="light"):
                            if not self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "on"))
                    else:
                        # Departure: turn off lights + switches
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "いってらっしゃい。照明とスイッチを切りますね。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                        for d in self._get_devices(device_class="light"):
                            if self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "off"))
                        for d in self._get_devices(device_class="switch"):
                            if self._device_is_on(d):
                                actions.append(self._make_action(d["device_id"], "off"))

        # --- Z3: Appliance finished (power drop to idle) ---
        for eid, s in hd.sensors.items():
            if (
                s.device_class == "power"
                and s.previous_value > self.thresholds.power_idle_watts
                and s.value <= self.thresholds.power_idle_watts
            ):
                if self._check_cooldown(f"zigbee_power_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    name_lower = name.lower()
                    if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": "洗濯物を干す",
                                    "description": f"{name}の運転が完了しました。洗濯物を干してください。",
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["laundry"],
                                },
                            }
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "洗濯が完了しました。洗濯物を干しましょう。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                    elif any(w in name_lower for w in ("kettle", "ケトル", "pot")):
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "お湯が沸きました。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )
                    else:
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": f"{name}の運転が完了しました。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )

        # --- Z4: CO2 high + all windows closed → ventilation suggestion ---
        co2_sensors = [s for s in hd.sensors.values() if s.device_class == "carbon_dioxide"]
        window_sensors = [bs for bs in hd.binary_sensors.values() if bs.device_class == "window"]
        for s in co2_sensors:
            if s.value > self.thresholds.co2_high:
                all_closed = all(not ws.state for ws in window_sensors) if window_sensors else False
                if all_closed and self._check_cooldown(f"zigbee_co2_window_{s.entity_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"CO2が{int(s.value)}ppmです。窓を開けて換気しましょう。",
                                "zone": "home",
                                "tone": "caring",
                            },
                        }
                    )

        # --- Z5: PM2.5 high → purifier on ---
        pm25_sensors = [s for s in hd.sensors.values() if s.device_class == "pm25"]
        for s in pm25_sensors:
            if s.value > self.thresholds.pm25_high:
                if self._check_cooldown(f"zigbee_pm25_{s.entity_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"PM2.5が{int(s.value)}μg/m³です。空気清浄機をつけます。",
                                "zone": "home",
                                "tone": "caring",
                            },
                        }
                    )
                    for d in self._get_devices(device_class="switch"):
                        did = d.get("device_id", "").lower()
                        purpose = (d.get("purpose") or "").lower()
                        if any(w in did or w in purpose for w in ("purifier", "清浄", "air")):
                            actions.append(self._make_action(d["device_id"], "on"))

        # --- Z6: Vibration stopped (washing machine) ---
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "vibration" and not bs.state and bs.previous_state:
                name_lower = eid.lower()
                if any(w in name_lower for w in ("washing", "laundry", "washer", "洗濯")):
                    if self._check_cooldown(f"zigbee_vibration_{eid}", now):
                        actions.append(
                            {
                                "tool": "create_task",
                                "args": {
                                    "title": "洗濯物を干す",
                                    "description": "洗濯機の振動が停止しました。洗濯物を干してください。",
                                    "urgency": 2,
                                    "zone": "home",
                                    "task_type": ["laundry"],
                                },
                            }
                        )
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "洗濯機が止まりました。洗濯物を干しましょう。",
                                    "zone": "home",
                                    "tone": "neutral",
                                },
                            }
                        )

        return actions

    def _eval_critical_moisture(self, world_model, now: float) -> list[dict]:
        """C3 Water-leak emergency (evaluate_critical block).

        Uses cooldown key ``critical_moisture_{eid}`` (separate from the
        normal-mode ``zigbee_moisture_{eid}``) so the two paths do not share
        state.
        """
        actions: list[dict] = []
        hd = world_model.home_devices
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"critical_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"【緊急】水漏れ検知: {name}",
                                "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                                "urgency": 4,
                                "zone": "home",
                                "task_type": ["water_leak"],
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"緊急！{name}で水漏れを検知しました！すぐに確認してください！",
                                "zone": "home",
                                "tone": "alert",
                            },
                        }
                    )
        return actions

    def _evaluate_zigbee_critical_only(self, world_model, now: float) -> list[dict]:
        """In guest mode, only evaluate critical safety rules (water leak, extreme conditions)."""
        actions = []
        hd = world_model.home_devices
        for eid, bs in hd.binary_sensors.items():
            if bs.device_class == "moisture" and bs.state:
                if self._check_cooldown(f"zigbee_moisture_{eid}", now):
                    name = eid.split(".")[-1] if "." in eid else eid
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"【緊急】水漏れ検知: {name}",
                                "description": f"{name}で水漏れが検知されました。直ちに確認してください。",
                                "urgency": 4,
                                "zone": "home",
                                "task_type": ["water_leak"],
                            },
                        }
                    )
        return actions
