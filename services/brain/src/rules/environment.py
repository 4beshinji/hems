"""Zone-environment RuleEngine rules.

Extracted (W2.4) from the inline zone-loop body of ``RuleEngine.evaluate``.
Each method receives ``(zone_id, zone, now)`` (or a narrower slice) and returns
a list of action dicts.  The orchestrator (``_evaluate_zone_environment``) calls
these in the **exact source order** of the original inline blocks so that the
emitted action list is byte-for-byte identical to the pre-refactor behaviour.

Block map (Z numbers per docs/refactor/2026-06-11/W2.4-design-note.md):
  Z1,Z2  co2 / temperature        -> _eval_env_basic
  Z3,Z4  sedentary / posture      -> _eval_occupancy
  Z5,Z6  humidity high / low      -> _eval_humidity
  Z7     pressure drop / sustained-> _eval_pressure
  Z8     soil moisture            -> _eval_soil
  Z9     VOC sustained            -> _eval_voc
  Z10    native PM2.5             -> _eval_pm25
  Z11    illuminance              -> _eval_illuminance
  Z12    late-night idle          -> _eval_late_night

Note: Z3/Z4 (occupancy) sit *between* Z2 and Z5/Z6 in the source, and Z12 is the
final zone block.  Keeping each method to a contiguous source range and calling
them in source order is what preserves the firing sequence — type-grouping would
reorder Z3/Z4 relative to humidity and break it.
"""

from datetime import datetime


class EnvironmentRulesMixin:
    def _evaluate_zone_environment(self, zone_id, zone, now: float) -> list[dict]:
        """Orchestrate all per-zone environment blocks in source order."""
        actions: list[dict] = []
        env = zone.environment
        # Z1, Z2 — CO2 ventilation task + temperature high/low speak
        actions.extend(self._eval_env_basic(zone_id, env, now))
        # Z3, Z4 — sedentary event + static posture
        actions.extend(self._eval_occupancy(zone_id, zone, now))
        # Z5, Z6 — humidity high / low
        actions.extend(self._eval_humidity(zone_id, env, now))
        # Z7 — pressure drop + sustained low pressure
        actions.extend(self._eval_pressure(zone_id, env, now))
        # Z8 — soil moisture watering
        actions.extend(self._eval_soil(zone_id, env, now))
        # Z9 — VOC sustained high
        actions.extend(self._eval_voc(zone_id, env, now))
        # Z10 — native PM2.5 high (shares cooldown key with zigbee mixin)
        actions.extend(self._eval_pm25(zone_id, env, now))
        # Z11 — illuminance anomalies
        actions.extend(self._eval_illuminance(zone_id, env, now))
        # Z12 — late night low activity
        actions.extend(self._eval_late_night(zone_id, zone, now))
        return actions

    def _eval_env_basic(self, zone_id, env, now: float) -> list[dict]:
        """Z1 CO2 ventilation task + Z2 temperature high/low speak."""
        actions: list[dict] = []

        # CO2 above threshold -> create ventilation task
        if env.co2 is not None and env.co2 > self.thresholds.co2_high:
            if self._check_cooldown(f"co2_{zone_id}", now):
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": f"{zone_id}の換気",
                            "description": f"CO2濃度が{int(env.co2)}ppmです。窓を開けて換気してください。",
                            "urgency": 3,
                            "zone": zone_id,
                            "task_type": ["ventilation"],
                        },
                    }
                )

        # Temperature too high or too low
        if env.temperature is not None:
            if env.temperature > self.thresholds.temp_high and self._check_cooldown(f"temp_high_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度です。エアコンをつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )
            elif env.temperature < self.thresholds.temp_low and self._check_cooldown(f"temp_low_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の室温が{env.temperature:.1f}度と低めです。暖房をつけましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )
        return actions

    def _eval_occupancy(self, zone_id, zone, now: float) -> list[dict]:
        """Z3 sedentary event + Z4 long static posture."""
        actions: list[dict] = []

        # Sedentary detection (from events)
        for event in zone.events:
            if event.event_type == "sedentary_alert" and self._check_cooldown(f"sed_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "長時間座っていますね。少し休憩しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

        # Long static posture detection
        occ = zone.occupancy
        if (
            occ.posture_status == "static"
            and occ.posture_duration_sec > self.thresholds.sedentary_minutes * 60
            and self._check_cooldown(f"posture_{zone_id}", now)
        ):
            duration_min = int(occ.posture_duration_sec / 60)
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"同じ姿勢で{duration_min}分経っています。少しストレッチしましょう。",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                }
            )
        return actions

    def _eval_humidity(self, zone_id, env, now: float) -> list[dict]:
        """Z5 humidity high + Z6 humidity low."""
        actions: list[dict] = []

        # Humidity high
        if env.humidity is not None and env.humidity > self.thresholds.humidity_high:
            if self._check_cooldown(f"humidity_high_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の湿度が{env.humidity:.0f}%です。除湿しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

        # Humidity low
        if env.humidity is not None and env.humidity < self.thresholds.humidity_low:
            if self._check_cooldown(f"humidity_low_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{zone_id}の湿度が{env.humidity:.0f}%と低めです。加湿しましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )
        return actions

    def _eval_pressure(self, zone_id, env, now: float) -> list[dict]:
        """Z7 pressure drop detection + sustained low pressure.

        ``_pressure_history`` is written unconditionally (before any cooldown
        check) to keep the previous-value baseline current.  The sustained-low
        tracker (``_low_pressure_since``) is set/popped inside this method.
        """
        actions: list[dict] = []

        if env.pressure is not None:
            prev_pressure = self._pressure_history.get(zone_id)
            self._pressure_history[zone_id] = env.pressure
            if prev_pressure is not None and prev_pressure - env.pressure >= 5:
                if self._check_cooldown(f"pressure_drop_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"気圧が低下しています（{prev_pressure:.0f}→{env.pressure:.0f}hPa）。頭痛に注意してください。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )

            # Sustained low pressure → weather headache warning (≤1 per day)
            if env.pressure < self.thresholds.low_pressure_threshold:
                start = self._low_pressure_since.get(zone_id)
                if start is None:
                    self._low_pressure_since[zone_id] = now
                elif now - start >= self.thresholds.low_pressure_sustain_s and self._check_cooldown_daily(
                    f"pressure_low_sustained_{zone_id}", now
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"気圧が{env.pressure:.0f}hPaで長時間低めです。気象病や頭痛に注意してください。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
            else:
                self._low_pressure_since.pop(zone_id, None)
        return actions

    def _eval_soil(self, zone_id, env, now: float) -> list[dict]:
        """Z8 soil moisture watering (auto-water or create task)."""
        actions: list[dict] = []

        if env.soil_moisture is not None and env.soil_moisture < self.thresholds.soil_moisture_low:
            if self._check_cooldown_custom(f"soil_low_{zone_id}", now, 6 * 3600):
                pump = next(
                    (
                        d
                        for d in self._device_cache
                        if "pulse" in (d.get("capabilities") or [])
                        and any(
                            w in ((d.get("purpose") or "") + (d.get("device_id") or "")).lower()
                            for w in ("pump", "ポンプ", "water", "水や", "給水")
                        )
                        and (not d.get("zone") or d["zone"] == zone_id)
                    ),
                    None,
                )
                msg = f"植物の土壌水分が{env.soil_moisture:.0f}%です。水やりをしてください。"
                if self.thresholds.auto_water_enabled and pump is not None:
                    actions.append(
                        self._make_action(
                            pump["device_id"],
                            "pulse",
                            {"duration_s": self.thresholds.auto_water_duration_s},
                        )
                    )
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"土壌水分が{env.soil_moisture:.0f}%だったので、自動で給水しました。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
                else:
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": "植物に水やり",
                                "description": msg,
                                "urgency": 2,
                                "zone": zone_id,
                                "task_type": ["gardening"],
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": msg,
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
        return actions

    def _eval_voc(self, zone_id, env, now: float) -> list[dict]:
        """Z9 VOC sustained high. Sets/pops ``_voc_high_since``."""
        actions: list[dict] = []

        if env.voc is not None:
            if env.voc > self.thresholds.voc_high_threshold:
                start = self._voc_high_since.get(zone_id)
                if start is None:
                    self._voc_high_since[zone_id] = now
                elif now - start >= self.thresholds.voc_sustain_seconds and self._check_cooldown_custom(
                    f"voc_high_{zone_id}", now, self.thresholds.voc_cooldown_seconds
                ):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"VOCが{env.voc:.0f}と高めです。換気をおすすめします。",
                                "zone": zone_id,
                                "tone": "caring",
                            },
                        }
                    )
                    # Engage a ventilation scene if one exists
                    vent = next(
                        (
                            d
                            for d in self._device_cache
                            if any(
                                w in (d.get("device_id") or "").lower() or w in (d.get("purpose") or "").lower()
                                for w in ("vent", "換気", "fan", "ventilation")
                            )
                            and d.get("device_class") in ("switch", "fan")
                        ),
                        None,
                    )
                    if vent is not None:
                        actions.append(self._make_action(vent["device_id"], "on"))
            else:
                self._voc_high_since.pop(zone_id, None)
        return actions

    def _eval_pm25(self, zone_id, env, now: float) -> list[dict]:
        """Z10 native PM2.5 high.

        Dedup key is shared with the zigbee HA-binary PM2.5 rule
        (``zigbee_pm25_{zone_id}``) so both paths can't fire the same message
        twice.  This method runs inside the zone loop, i.e. *before* the zigbee
        mixin — preserving that order is required for the dedup semantics.
        """
        actions: list[dict] = []

        if env.pm25 is not None and env.pm25 > self.thresholds.pm25_native_high:
            if self._check_cooldown(f"zigbee_pm25_{zone_id}", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"PM2.5が{env.pm25:.0f}μg/m³です。空気清浄機をつけます。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )
                for d in self._get_devices(device_class="switch"):
                    did = (d.get("device_id") or "").lower()
                    purpose = (d.get("purpose") or "").lower()
                    if any(w in did or w in purpose for w in ("purifier", "清浄", "air")):
                        actions.append(self._make_action(d["device_id"], "on"))
        return actions

    def _eval_illuminance(self, zone_id, env, now: float) -> list[dict]:
        """Z11 illuminance anomalies. Sets/pops ``_low_light_since`` / ``_high_light_since``."""
        actions: list[dict] = []

        if env.light is not None:
            hour = datetime.now().hour
            is_night = hour >= 22 or hour < 5
            # Sustained darkness outside sleeping hours → sensor / power fault suspicion
            if not is_night and env.light < self.thresholds.illuminance_low_lx:
                start = self._low_light_since.get(zone_id)
                if start is None:
                    self._low_light_since[zone_id] = now
                elif now - start >= self.thresholds.illuminance_low_sustain_s and self._check_cooldown_daily(
                    f"light_low_sustained_{zone_id}", now
                ):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"{zone_id}の照度センサー確認",
                                "description": (
                                    f"日中に照度が{env.light:.0f}lxと低い状態が続いています。"
                                    "センサー故障または停電の可能性を確認してください。"
                                ),
                                "urgency": 2,
                                "zone": zone_id,
                                "task_type": ["maintenance"],
                            },
                        }
                    )
            else:
                self._low_light_since.pop(zone_id, None)

            # Sustained daylight glare → suggest / request curtain close
            if env.light > self.thresholds.illuminance_high_lx:
                start = self._high_light_since.get(zone_id)
                if start is None:
                    self._high_light_since[zone_id] = now
                elif now - start >= self.thresholds.illuminance_high_sustain_s and self._check_cooldown_custom(
                    f"light_high_sustained_{zone_id}", now, 3600
                ):
                    covers = self._get_devices(device_class="cover", zone=zone_id)
                    if covers:
                        for c in covers:
                            actions.append(self._make_action(c["device_id"], "set_position", {"position": 0}))
                        actions.append(
                            {
                                "tool": "speak",
                                "args": {
                                    "message": "日差しが強いのでカーテンを閉めます。",
                                    "zone": zone_id,
                                    "tone": "neutral",
                                },
                            }
                        )
            else:
                self._high_light_since.pop(zone_id, None)
        return actions

    def _eval_critical_env_zone(self, zone_id, env, now: float) -> list[dict]:
        """C1 CO2 danger level + C2 extreme temperature (critical zone block).

        Extracted from evaluate_critical.  Uses distinct cooldown keys
        (``critical_co2_*`` / ``critical_temp_high_*`` / ``critical_temp_low_*``)
        that are separate from the normal-mode keys so the two code paths do not
        interfere with each other.
        """
        actions: list[dict] = []

        # --- C1: CO2 danger level ---
        if (
            env.co2 is not None
            and env.co2 > self.thresholds.co2_critical
            and self._check_cooldown(f"critical_co2_{zone_id}", now)
        ):
            actions.append(
                {
                    "tool": "create_task",
                    "args": {
                        "title": f"【緊急】{zone_id}のCO2危険レベル",
                        "description": (f"CO2濃度が{int(env.co2)}ppmです。直ちに換気してください。"),
                        "urgency": 4,
                        "zone": zone_id,
                        "task_type": ["ventilation"],
                    },
                }
            )
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (f"緊急です！{zone_id}のCO2濃度が{int(env.co2)}ppmです。すぐに換気してください！"),
                        "zone": zone_id,
                        "tone": "alert",
                    },
                }
            )

        # --- C2: Extreme temperature ---
        if env.temperature is not None:
            if env.temperature > self.thresholds.temp_critical_high and self._check_cooldown(
                f"critical_temp_high_{zone_id}", now
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": (
                                f"危険！{zone_id}の室温が{env.temperature:.1f}℃です。熱中症に注意してください！"
                            ),
                            "zone": zone_id,
                            "tone": "alert",
                        },
                    }
                )
            elif env.temperature < self.thresholds.temp_critical_low and self._check_cooldown(
                f"critical_temp_low_{zone_id}", now
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": (
                                f"危険！{zone_id}の室温が{env.temperature:.1f}℃まで低下しています。"
                                "暖房を確認してください！"
                            ),
                            "zone": zone_id,
                            "tone": "alert",
                        },
                    }
                )
        return actions

    def _eval_late_night(self, zone_id, zone, now: float) -> list[dict]:
        """Z12 late-night low activity → suggest sleep."""
        actions: list[dict] = []
        occ = zone.occupancy

        hour = datetime.now().hour
        if (
            (hour >= 23 or hour < 5)
            and occ.activity_class == "idle"
            and occ.count > 0
            and self._check_cooldown(f"late_idle_{zone_id}", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "深夜ですね。そろそろ休みましょう。",
                        "zone": zone_id,
                        "tone": "caring",
                    },
                }
            )
        return actions
