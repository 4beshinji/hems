"""WorldModel mixin extracted from the facade module."""

from . import world_model as _world_model


class UserUpdatesMixin:
    def _update_personal(self, path_parts: list[str], payload: dict):
        """Handle hems/personal/* topics."""
        if not path_parts:
            return
        category = path_parts[0]

        # hems/personal/notes/* (Obsidian bridge)
        if category == "notes" and len(path_parts) >= 2:
            self._update_knowledge_state(path_parts[1], payload)

        # hems/personal/knowledge/* (Knowledge bridge)
        elif category == "knowledge" and len(path_parts) >= 2:
            self._update_external_knowledge_state(path_parts[1], payload)

        # hems/personal/biometrics/{provider}/{metric}
        elif category == "biometrics" and len(path_parts) >= 2:
            self._update_biometric_state(path_parts[1:], payload)

    def _update_news_state(self, sub_topic: str, payload: dict):
        """Handle hems/news/* topics from news-bridge."""
        ns = self.news_state

        if sub_topic == "daily":
            ns.daily_summary = payload.get("summary", "")
            ns.daily_chunks = payload.get("chunks", [])
            ns.daily_timestamp = payload.get("timestamp", _world_model.time.time())
            ns.add_event(
                _world_model.Event(
                    event_type="news_daily",
                    description=f"日次ニュースサマリ更新 ({payload.get('article_count', 0)}件)",
                    severity=0,
                )
            )

        elif sub_topic == "urgent":
            article = {
                "title": _world_model._sanitize_text(payload.get("title", ""), 100),
                "summary": _world_model._sanitize_text(payload.get("summary", ""), 300),
                "score": payload.get("score", 0),
                "source": payload.get("source", ""),
                "url": payload.get("url", ""),
                "timestamp": payload.get("timestamp", _world_model.time.time()),
            }
            ns.urgent_articles.append(article)
            # Keep only recent 10 urgent articles
            if len(ns.urgent_articles) > 10:
                ns.urgent_articles = ns.urgent_articles[-10:]
            ns.add_event(
                _world_model.Event(
                    event_type="news_urgent",
                    description=f"速報: {article['title'][:50]}",
                    severity=1,
                    data=article,
                )
            )

        elif sub_topic == "bridge":
            # hems/news/bridge/status
            ns.bridge_connected = payload.get("connected", False)

    def _update_weather_state(self, sub_topic: str, payload: dict):
        """Handle hems/weather/* topics from weather-bridge."""
        w = self.weather
        now = _world_model.time.time()

        if sub_topic == "current":
            w.condition = payload.get("condition", payload.get("weather_main", w.condition))
            w.temperature = float(payload.get("temperature", payload.get("temp", w.temperature)))
            w.humidity = float(payload.get("humidity", w.humidity))
            w.wind_speed = float(payload.get("wind_speed", w.wind_speed))
            w.last_update = now

        elif sub_topic == "forecast":
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            forecast: list[_world_model.WeatherForecast] = []
            for f in entries:
                if not isinstance(f, dict):
                    continue
                forecast.append(
                    _world_model.WeatherForecast(
                        datetime=str(f.get("datetime", "")),
                        condition=str(f.get("condition", f.get("weather_main", ""))),
                        temperature=float(f.get("temperature", f.get("temp", 0)) or 0),
                        precipitation_probability=int(f.get("precipitation_probability", 0) or 0),
                        wind_speed=float(f.get("wind_speed", 0) or 0),
                    )
                )
            w.forecast = forecast
            w.last_update = now

        elif sub_topic == "alerts":
            raw_alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
            alerts: list[_world_model.WeatherAlert] = []
            for a in raw_alerts:
                if not isinstance(a, dict):
                    continue
                alerts.append(
                    _world_model.WeatherAlert(
                        title=_world_model._sanitize_text(a.get("title", a.get("event", "")), 120),
                        severity=str(a.get("severity", "unknown")).lower(),
                        description=_world_model._sanitize_text(a.get("description", a.get("headline", "")), 300),
                        area=_world_model._sanitize_text(a.get("area", ""), 80),
                        issued_at=str(a.get("issued_at", a.get("start", ""))),
                        expires_at=str(a.get("expires_at", a.get("end", ""))),
                    )
                )
            w.alerts = alerts
            w.last_alerts_update = now

        elif sub_topic == "bridge":
            # hems/weather/bridge/status → keep last update for freshness tracking
            if payload.get("connected") is not None:
                w.last_update = w.last_update or now

    # -------------------------------------------------------------------------
    # Biometric metric handlers (one per metric)
    # -------------------------------------------------------------------------

    def _handle_biometric_heart_rate(self, bio, payload: dict, now: float) -> None:
        """Update heart_rate sub-object and fire threshold events."""
        bpm = payload.get("bpm")
        if bpm is not None:
            prev_bpm = bio.heart_rate.bpm
            bio.heart_rate.bpm = int(bpm)
            bio.heart_rate.zone = _world_model.HeartRateData.classify_zone(int(bpm))
            bio.heart_rate.last_update = now
            if "resting_bpm" in payload:
                bio.heart_rate.resting_bpm = int(payload["resting_bpm"])
            bio.bridge_connected = True
            bio.record_history("heart_rate", float(bpm), now)
            self._check_biometric_thresholds(
                "heart_rate", float(bpm), float(prev_bpm) if prev_bpm is not None else None
            )

    def _handle_biometric_spo2(self, bio, payload: dict, now: float) -> None:
        """Update spo2 sub-object and fire threshold events."""
        pct = payload.get("percent")
        if pct is not None:
            prev_pct = bio.spo2.percent
            bio.spo2.percent = int(pct)
            bio.spo2.last_update = now
            bio.bridge_connected = True
            bio.record_history("spo2", float(pct), now)
            self._check_biometric_thresholds("spo2", float(pct), float(prev_pct) if prev_pct is not None else None)

    def _handle_biometric_sleep(self, bio, payload: dict, now: float) -> None:
        """Update sleep sub-object (no threshold events)."""
        bio.sleep.stage = payload.get("stage", bio.sleep.stage)
        if "duration_minutes" in payload:
            bio.sleep.duration_minutes = int(payload["duration_minutes"])
            bio.record_history("sleep_duration", float(payload["duration_minutes"]), now)
        if "deep_minutes" in payload:
            bio.sleep.deep_minutes = int(payload["deep_minutes"])
        if "rem_minutes" in payload:
            bio.sleep.rem_minutes = int(payload["rem_minutes"])
        if "light_minutes" in payload:
            bio.sleep.light_minutes = int(payload["light_minutes"])
        if "quality_score" in payload:
            bio.sleep.quality_score = int(payload["quality_score"])
            bio.record_history("sleep_quality", float(payload["quality_score"]), now)
        if "sleep_start_ts" in payload:
            bio.sleep.sleep_start_ts = float(payload["sleep_start_ts"])
        if "sleep_end_ts" in payload:
            bio.sleep.sleep_end_ts = float(payload["sleep_end_ts"])
        bio.sleep.last_update = now
        bio.bridge_connected = True

    def _handle_biometric_activity(self, bio, payload: dict, now: float) -> None:
        """Update activity sub-object (no threshold events)."""
        if "steps" in payload:
            bio.activity.steps = int(payload["steps"])
            bio.record_history("steps", float(payload["steps"]), now)
        if "steps_goal" in payload:
            bio.activity.steps_goal = int(payload["steps_goal"])
        if "calories" in payload:
            bio.activity.calories = int(payload["calories"])
        if "active_minutes" in payload:
            bio.activity.active_minutes = int(payload["active_minutes"])
        if "level" in payload:
            bio.activity.level = payload["level"]
        bio.activity.last_update = now
        bio.bridge_connected = True

    def _handle_biometric_stress(self, bio, payload: dict, now: float) -> None:
        """Update stress sub-object and fire threshold events."""
        level = payload.get("level")
        if level is not None:
            prev_level = bio.stress.level
            bio.stress.level = int(level)
            bio.stress.category = _world_model.StressData.classify_category(int(level))
            bio.stress.last_update = now
            bio.bridge_connected = True
            bio.record_history("stress", float(level), now)
            self._check_biometric_thresholds(
                "stress", float(level), float(prev_level) if prev_level is not None else None
            )

    def _handle_biometric_fatigue(self, bio, payload: dict, now: float) -> None:
        """Update fatigue sub-object (no threshold events)."""
        if "score" in payload:
            bio.fatigue.score = int(payload["score"])
            bio.record_history("fatigue", float(payload["score"]), now)
        if "factors" in payload:
            bio.fatigue.factors = payload["factors"]
        bio.fatigue.last_update = now
        bio.bridge_connected = True

    def _handle_biometric_hrv(self, bio, payload: dict, now: float) -> None:
        """Update hrv sub-object and fire threshold events (inline — not via _check_biometric_thresholds)."""
        rmssd = payload.get("rmssd_ms")
        if rmssd is not None:
            prev_rmssd = bio.hrv.rmssd_ms
            bio.hrv.rmssd_ms = int(rmssd)
            bio.hrv.last_update = now
            bio.bridge_connected = True
            bio.record_history("hrv", float(rmssd), now)
            if int(rmssd) < self.thresholds.hrv_low and (prev_rmssd is None or prev_rmssd >= self.thresholds.hrv_low):
                bio.add_event(
                    _world_model.Event(
                        event_type="hrv_low",
                        description=f"HRV低下: {int(rmssd)}ms",
                        severity=1,
                        data={"rmssd_ms": int(rmssd)},
                    )
                )

    def _handle_biometric_body_temperature(self, bio, payload: dict, now: float) -> None:
        """Update body_temperature sub-object and fire threshold events (inline)."""
        celsius = payload.get("celsius")
        if celsius is not None:
            prev_temp = bio.body_temperature.celsius
            bio.body_temperature.celsius = float(celsius)
            bio.body_temperature.last_update = now
            bio.bridge_connected = True
            bio.record_history("body_temperature", float(celsius), now)
            if float(celsius) > self.thresholds.body_temp_high and (
                prev_temp is None or prev_temp <= self.thresholds.body_temp_high
            ):
                bio.add_event(
                    _world_model.Event(
                        event_type="body_temp_high",
                        description=f"体温上昇: {float(celsius):.1f}°C",
                        severity=1,
                        data={"celsius": float(celsius)},
                    )
                )

    def _handle_biometric_respiratory_rate(self, bio, payload: dict, now: float) -> None:
        """Update respiratory_rate sub-object and fire threshold events (inline)."""
        rate = payload.get("breaths_per_minute")
        if rate is not None:
            prev_rate = bio.respiratory_rate.breaths_per_minute
            bio.respiratory_rate.breaths_per_minute = int(rate)
            bio.respiratory_rate.last_update = now
            bio.bridge_connected = True
            bio.record_history("respiratory_rate", float(rate), now)
            if int(rate) > self.thresholds.respiratory_rate_high and (
                prev_rate is None or prev_rate <= self.thresholds.respiratory_rate_high
            ):
                bio.add_event(
                    _world_model.Event(
                        event_type="respiratory_rate_high",
                        description=f"呼吸数上昇: {int(rate)}回/分",
                        severity=1,
                        data={"breaths_per_minute": int(rate)},
                    )
                )

    def _handle_biometric_steps(self, bio, payload: dict, now: float) -> None:
        """Alternative topic: hems/personal/biometrics/{provider}/steps — updates activity."""
        if "count" in payload:
            bio.activity.steps = int(payload["count"])
        if "daily_goal" in payload:
            bio.activity.steps_goal = int(payload["daily_goal"])
        bio.activity.last_update = now
        bio.bridge_connected = True

    # Dispatch table: metric name → handler method name
    _BIOMETRIC_HANDLERS: dict[str, str] = {
        "heart_rate": "_handle_biometric_heart_rate",
        "spo2": "_handle_biometric_spo2",
        "sleep": "_handle_biometric_sleep",
        "activity": "_handle_biometric_activity",
        "stress": "_handle_biometric_stress",
        "fatigue": "_handle_biometric_fatigue",
        "hrv": "_handle_biometric_hrv",
        "body_temperature": "_handle_biometric_body_temperature",
        "respiratory_rate": "_handle_biometric_respiratory_rate",
        "steps": "_handle_biometric_steps",
    }

    def _update_biometric_state(self, path_parts: list[str], payload: dict):
        """Handle hems/personal/biometrics/* topics from biometric bridge.

        Thin dispatcher: bridge/status handled first, then metric routed via
        _BIOMETRIC_HANDLERS table to individual helper methods.
        """
        if not path_parts:
            return

        bio = self.biometric_state
        now = _world_model.time.time()

        # hems/personal/biometrics/bridge/status
        if path_parts[0] == "bridge" and len(path_parts) >= 2 and path_parts[1] == "status":
            bio.bridge_connected = payload.get("connected", False)
            bio.provider = payload.get("provider", "")
            return

        # hems/personal/biometrics/{provider}/{metric}
        if len(path_parts) < 2:
            return

        metric = path_parts[1]
        handler_name = self._BIOMETRIC_HANDLERS.get(metric)
        if handler_name is not None:
            getattr(self, handler_name)(bio, payload, now)

    def _check_biometric_thresholds(self, metric: str, value: float, prev: float | None):
        """Generate events from biometric threshold crossings."""
        bio = self.biometric_state

        if metric == "heart_rate":
            if value > self.thresholds.hr_high and (prev is None or prev <= self.thresholds.hr_high):
                bio.add_event(
                    _world_model.Event(
                        event_type="hr_high",
                        description=f"心拍数上昇: {int(value)}bpm",
                        severity=1,
                        data={"bpm": value},
                    )
                )
            elif value < self.thresholds.hr_low and (prev is None or prev >= self.thresholds.hr_low):
                bio.add_event(
                    _world_model.Event(
                        event_type="hr_low",
                        description=f"心拍数低下: {int(value)}bpm",
                        severity=1,
                        data={"bpm": value},
                    )
                )

        elif metric == "spo2":
            if value < self.thresholds.spo2_low and (prev is None or prev >= self.thresholds.spo2_low):
                bio.add_event(
                    _world_model.Event(
                        event_type="spo2_low",
                        description=f"SpO2低下: {int(value)}%",
                        severity=2,
                        data={"percent": value},
                    )
                )

        elif metric == "stress":
            if value > self.thresholds.stress_high and (prev is None or prev <= self.thresholds.stress_high):
                bio.add_event(
                    _world_model.Event(
                        event_type="stress_high",
                        description=f"ストレス高: {int(value)}",
                        severity=1,
                        data={"level": value},
                    )
                )
