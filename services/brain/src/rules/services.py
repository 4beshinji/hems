"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""

import rule_engine as _rule_engine


class ServiceRulesMixin:
    def _evaluate_service_vip_rules(self, world_model, now: float) -> list[dict]:
        """B-2: Speak immediately on VIP service events (Gmail VIP sender, etc).

        Cooldown: 5 min per service to suppress storms.
        """
        actions: list[dict] = []
        ss = getattr(world_model, "services_state", None)
        if ss is None or not ss.events:
            return actions
        for ev in ss.events[-20:]:
            if ev.event_type != "service_vip_event":
                continue
            # Only fire for events less than 60s old (avoid speaking on replay)
            if ev.timestamp and now - ev.timestamp > 60:
                continue
            service = (ev.data or {}).get("service", "サービス")
            key = f"service_vip_{service}"
            if not self._check_cooldown_custom(key, now, 300):
                continue
            summary = ev.description or f"{service} で更新あり"
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"重要な通知です。{summary}",
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )
        return actions

    def _evaluate_device_health_rules(self, now: float) -> list[dict]:
        """B-5: Battery / LQI / staleness alerts for registered devices.

        Reads `self._device_cache` (populated by `refresh_devices`). Cooldowns:
        - battery_low: 7 days per device
        - link_quality_low: 24h per device
        - stale: 24h per device
        """
        actions: list[dict] = []
        if not self._device_cache:
            return actions

        WEEK_S = 7 * 86400
        DAY_S = 86400
        stale_threshold_s = _rule_engine.DEVICE_STALE_HOURS * 3600

        for d in self._device_cache:
            if not d.get("is_enabled", True):
                continue
            device_id = d.get("device_id") or ""
            if not device_id:
                continue
            display = d.get("display_name") or device_id

            # Battery (≤10% by default)
            battery = d.get("battery_pct")
            if isinstance(battery, (int, float)) and battery <= _rule_engine.DEVICE_BATTERY_LOW:
                if self._check_cooldown_custom(f"dev_battery_{device_id}", now, WEEK_S):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"電池切れ間近: {display}",
                                "description": f"{display} の電池残量が{int(battery)}%です。早めの交換を。",
                                "urgency": 2,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

            # Link quality (Z2M LQI < 50 means weak mesh signal)
            lqi = d.get("link_quality")
            if isinstance(lqi, (int, float)) and lqi < _rule_engine.DEVICE_LQI_LOW and (d.get("vendor") == "zigbee"):
                if self._check_cooldown_custom(f"dev_lqi_{device_id}", now, DAY_S):
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"信号弱: {display}",
                                "description": f"{display} のZigbeeリンク品質が低下 (LQI={int(lqi)}). 中継器の追加か配置の見直しを検討してください。",
                                "urgency": 1,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

            # Staleness (no updates for >24h)
            last_seen_iso = d.get("last_seen")
            last_seen_ts = _rule_engine.parse_iso_ts(last_seen_iso)
            if last_seen_ts is not None and (now - last_seen_ts) > stale_threshold_s:
                if self._check_cooldown_custom(f"dev_stale_{device_id}", now, DAY_S):
                    hours_ago = int((now - last_seen_ts) / 3600)
                    actions.append(
                        {
                            "tool": "create_task",
                            "args": {
                                "title": f"反応なし: {display}",
                                "description": f"{display} は{hours_ago}時間応答していません。確認/再ペアリングしてください。",
                                "urgency": 2,
                                "zone": d.get("zone") or "home",
                                "task_type": ["maintenance"],
                            },
                        }
                    )

        return actions
