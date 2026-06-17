"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""

from datetime import datetime


class PerceptionRulesMixin:
    def _evaluate_perception_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate camera/perception-based rules."""
        actions = []
        hour = datetime.now().hour
        ha_enabled = world_model.home_devices.bridge_connected

        for zone_id, zone in world_model.zones.items():
            occ = zone.occupancy

            # 1. Sedentary sitting detection (camera posture)
            # Require all three: sitting posture, ≥90min streak, activity<0.1.
            # The activity gate cuts false positives when the YOLO posture
            # classifier locks onto "sitting" but the user is actually moving
            # (reaching, typing, fidgeting).
            if (
                occ.posture == "sitting"
                and occ.posture_duration_sec >= 90 * 60
                and occ.activity_level < 0.1
                and self._check_cooldown(f"percep_sitting_{zone_id}", now)
            ):
                duration_min = int(occ.posture_duration_sec / 60)
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": f"{duration_min}分座りっぱなしです。少し体を動かしましょう。",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 2. Empty room with lights/climate on → turn off
            has_devs = ha_enabled or bool(self._device_cache)
            if has_devs and occ.count == 0 and occ.last_update > 0 and now - occ.last_update < 300:
                lights_on = [d for d in self._get_devices(device_class="light", zone=zone_id) if self._device_is_on(d)]
                if lights_on and self._check_cooldown(f"percep_empty_lights_{zone_id}", now):
                    for d in lights_on:
                        actions.append(self._make_action(d["device_id"], "off"))
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"{zone_id}は空室です。照明を消しますね。",
                                "zone": zone_id,
                                "tone": "neutral",
                            },
                        }
                    )
                climates_on = [
                    d
                    for d in self._get_devices(device_class="climate", zone=zone_id)
                    if (d.get("last_state") or {}).get("hvac_mode", "off") != "off"
                ]
                if climates_on and self._check_cooldown(f"percep_empty_climate_{zone_id}", now):
                    for d in climates_on:
                        actions.append(self._make_action(d["device_id"], "set_temperature", {"mode": "off"}))

            # 3. Daytime lying detection → health check
            if (
                6 <= hour <= 21
                and occ.posture == "lying"
                and occ.posture_duration_sec > 600
                and self._check_cooldown(f"percep_lying_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "日中に横になっていますね。体調は大丈夫ですか？",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 4. Activity level sudden drop (>0.5 → <0.1 sustained 15min)
            if (
                occ.activity_level is not None
                and occ.activity_level < 0.1
                and occ.count > 0
                and occ.posture_duration_sec > 900
                and self._check_cooldown(f"percep_activity_drop_{zone_id}", now)
            ):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "しばらく動きがないようです。大丈夫ですか？",
                            "zone": zone_id,
                            "tone": "caring",
                        },
                    }
                )

            # 5. VLM anomaly detected — 3-stage escalation:
            #    (a) Initial alert when anomaly first observed (cooldown gated)
            #    (b) 5min persistence: escalate (speak + task)
            #    (c) 30min persistence: request VLM rescan (heavy) via MQTT (30min cooldown)
            if occ.scene_anomalies and occ.vlm_last_update > 0 and now - occ.vlm_last_update < 120:
                anomaly_text = "、".join(occ.scene_anomalies[:3])
                first_seen = occ.anomaly_first_seen or occ.vlm_last_update
                persist_sec = now - first_seen

                # (a) Initial alert
                if self._check_cooldown(f"percep_vlm_anomaly_{zone_id}", now):
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"カメラで異常を検知しました: {anomaly_text}。確認をお願いします。",
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )

                # (b) 5min escalation — speak + task if anomaly still present
                if persist_sec >= 300 and not occ.anomaly_escalated:
                    occ.anomaly_escalated = True
                    actions.append(
                        {
                            "tool": "speak",
                            "args": {
                                "message": f"先ほどの異常({anomaly_text})が5分経過しても続いています。確認してください。",
                                "zone": zone_id,
                                "tone": "alert",
                            },
                        }
                    )
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"VLM異常持続: {zone_id}",
                                "description": f"{zone_id}で検知された異常 ({anomaly_text}) が5分以上継続しています。現地確認をお願いします。",
                                "urgency": 3,
                                "zone": zone_id,
                                "task_type": ["vlm_anomaly"],
                            },
                        }
                    )

                # (c) 30min persistence → re-request VLM heavy scan (30min cooldown)
                rescan_cooldown_ok = (now - occ.anomaly_rescan_requested) >= 1800
                if persist_sec >= 1800 and rescan_cooldown_ok and self.mqtt_publisher is not None:
                    try:
                        self.mqtt_publisher(
                            "hems/perception/vlm/request",
                            {"zone": zone_id, "reason": "anomaly_persisted_30min"},
                        )
                        occ.anomaly_rescan_requested = now
                    except Exception:
                        pass

        return actions
