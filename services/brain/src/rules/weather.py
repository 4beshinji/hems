"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""


class WeatherRulesMixin:
    def _evaluate_weather_rules(self, world_model, now: float) -> list[dict]:
        """Weather-based automation rules."""
        w = world_model.weather
        if w.last_update == 0 and w.last_alerts_update == 0:
            return []

        actions = []
        hd = world_model.home_devices

        # Severe weather alerts → speak + create_task (24h cooldown per alert title)
        severe_levels = {"warning", "severe", "extreme", "critical"}
        for alert in w.alerts:
            sev = (alert.severity or "").lower()
            if sev not in severe_levels or not alert.title:
                continue
            key = f"weather_alert_{alert.title}"
            if not self._check_cooldown_daily(key, now):
                continue
            area_part = f"（{alert.area}）" if alert.area else ""
            tone = "alert" if sev in ("extreme", "critical") else "caring"
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"気象警報: {alert.title}{area_part}。注意してください。",
                        "zone": "home",
                        "tone": tone,
                    },
                }
            )
            actions.append(
                {
                    "tool": "create_task",
                    "args": {
                        "title": f"気象警報: {alert.title}",
                        "description": (alert.description or alert.title)[:300],
                        "urgency": 4 if sev in ("extreme", "critical") else 3,
                        "zone": "home",
                        "task_type": ["weather_alert"],
                    },
                }
            )

        # Rain forecast + windows open → alert
        rain_soon = any(
            f.precipitation_probability > 60
            for f in w.forecast[:4]  # next ~4 hours
        )
        if rain_soon:
            open_windows = [bs for bs in hd.binary_sensors.values() if bs.device_class == "window" and bs.state]
            if open_windows and self._check_cooldown("weather_rain_window", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "雨の予報が出ています。窓を閉めてください。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # High temperature forecast → pre-cool advice
        hot_forecast = any(f.temperature > 33 for f in w.forecast[:6])
        if hot_forecast and self._check_cooldown_daily("weather_hot_forecast", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "本日は猛暑の予報です。エアコンの早めの稼働をお勧めします。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        return actions
