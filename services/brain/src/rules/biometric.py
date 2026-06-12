"""Domain-specific RuleEngine rules.

Extracted as a mixin to keep RuleEngine public methods stable.
"""

from datetime import datetime

import rule_engine as _rule_engine


class BiometricRulesMixin:
    def _evaluate_biometric_rules(self, world_model, now: float) -> list[dict]:
        """Evaluate biometric health rules."""
        actions = []
        bio = world_model.biometric_state
        hour = _rule_engine.datetime.now().hour

        # 0. Stale biometric data alert
        if (
            bio.bridge_connected
            and bio.last_update > 0
            and (now - bio.last_update) > self.thresholds.biometric_stale_minutes * 60
            and self._check_cooldown("bio_stale_data", now)
        ):
            stale_minutes = int((now - bio.last_update) / 60)
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"バイオメトリクスデータが{stale_minutes}分間更新されていません。スマートバンドの接続を確認してください。",
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )

        # 1. High heart rate alert
        if bio.heart_rate.bpm is not None and bio.heart_rate.bpm > 120 and self._check_cooldown("bio_hr_high", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"心拍数が{bio.heart_rate.bpm}bpmです。少し休憩しましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 2. High stress alert
        if bio.stress.level > 80 and bio.stress.last_update > 0 and self._check_cooldown("bio_stress_high", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "ストレスが高めです。深呼吸してリラックスしましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
            # Stress spike → request VLM scan (Wave 4.7) so we can confirm the
            # user is actually OK (e.g., not just sitting still elevated).
            # Only when MQTT publisher available; cooldown 30min via ad-hoc key.
            if self.mqtt_publisher is not None and self._check_cooldown_custom("bio_stress_vlm_request", now, 1800):
                try:
                    self.mqtt_publisher(
                        "hems/perception/vlm/request",
                        {"reason": "stress_spike", "stress_level": bio.stress.level},
                    )
                except Exception:
                    pass

        # 3. High fatigue alert
        if bio.fatigue.score > 70 and bio.fatigue.last_update > 0 and self._check_cooldown("bio_fatigue_high", now):
            if 21 <= hour <= 23:
                msg = "疲労が溜まっていますね。今日は早めに休みましょう。"
            else:
                msg = "疲れが溜まっていますね。少し休憩しましょう。"
            actions.append(
                {
                    "tool": "speak",
                    "args": {"message": msg, "zone": "home", "tone": "caring"},
                }
            )

        # 4. Poor sleep quality morning notification (8-10 AM)
        if (
            8 <= hour < 10
            and bio.sleep.quality_score > 0
            and bio.sleep.quality_score < 50
            and self._check_cooldown_daily("bio_sleep_poor", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"昨夜の睡眠品質が{bio.sleep.quality_score}点でした。今日は無理しないでくださいね。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 5. Step goal achievement
        if (
            bio.activity.steps > 0
            and bio.activity.steps_goal > 0
            and bio.activity.steps >= bio.activity.steps_goal
            and self._check_cooldown_daily("bio_steps_goal", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"歩数{bio.activity.steps}歩で目標達成です！お疲れさまでした！",
                        "zone": "home",
                        "tone": "humorous",
                    },
                }
            )

        # 6. Enhanced sleep detection (biometric) → turn off lights
        if (
            bio.sleep.stage in ("deep", "light", "rem")
            and self._device_cache
            and self._check_cooldown_daily("bio_sleep_lights", now)
        ):
            lights_on = [d for d in self._get_devices(device_class="light") if self._device_is_on(d)]
            if lights_on:
                for d in lights_on:
                    actions.append(self._make_action(d["device_id"], "off"))
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "おやすみなさい。照明を消しますね。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )

        # 8. Low HRV alert (autonomic stress)
        if (
            bio.hrv.rmssd_ms is not None
            and bio.hrv.rmssd_ms < self.thresholds.hrv_low
            and bio.hrv.last_update > 0
            and self._check_cooldown("bio_hrv_low", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"HRVが{bio.hrv.rmssd_ms}msと低めです。自律神経の疲れが出ています。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 9. Body temperature high
        if (
            bio.body_temperature.celsius is not None
            and bio.body_temperature.celsius > self.thresholds.body_temp_high
            and bio.body_temperature.last_update > 0
            and self._check_cooldown("bio_body_temp_high", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": f"体温が{bio.body_temperature.celsius:.1f}°Cです。体調に気をつけてください。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 10. Respiratory rate high
        if (
            bio.respiratory_rate.breaths_per_minute is not None
            and bio.respiratory_rate.breaths_per_minute > self.thresholds.respiratory_rate_high
            and bio.respiratory_rate.last_update > 0
            and self._check_cooldown("bio_resp_high", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": "呼吸が速くなっています。落ち着いて深呼吸しましょう。",
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )

        # 11. Fatigue-linked dimming (21-23h, fatigue > 60)
        if (
            self._device_cache
            and 21 <= hour <= 23
            and bio.fatigue.score > 60
            and bio.fatigue.last_update > 0
            and self._check_cooldown("bio_fatigue_dim", now)
        ):
            for d in self._get_devices(device_class="light"):
                if self._device_is_on(d) and self._device_brightness(d) > 100:
                    actions.append(self._make_action(d["device_id"], "set_brightness", {"value": 80}))
                    if "color_temp" in (d.get("capabilities") or []):
                        actions.append(self._make_action(d["device_id"], "set_color_temp", {"value": 400}))

        # --- Trend rules (Wave 3.2) ---
        # Fatigue streak: 3 consecutive days fatigue >= 70 (sample at distinct days)
        actions.extend(self._evaluate_fatigue_streak(bio, now))
        # Sleep decline: 7-day quality drop -15% vs prior 7-day baseline
        actions.extend(self._evaluate_sleep_decline(bio, now))
        # Stress + HR coupling: 15min stress > 70 AND HR baseline +20%
        actions.extend(self._evaluate_stress_hr_coupling(bio, now))

        return actions

    def _evaluate_fatigue_streak(self, bio, now: float) -> list[dict]:
        """3 consecutive days with peak fatigue ≥ 70."""
        actions = []
        history = bio.history.get("fatigue") if bio.history else None
        if not history or len(history) < 3:
            return actions

        # Group samples by date (local), keep peak per day
        peaks_by_day: dict[str, float] = {}
        for ts, value in history:
            day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            peaks_by_day[day] = max(peaks_by_day.get(day, 0), value)

        # Need 3 most recent calendar days
        sorted_days = sorted(peaks_by_day.keys(), reverse=True)
        if len(sorted_days) < 3:
            return actions

        recent_3 = [peaks_by_day[d] for d in sorted_days[:3]]
        if all(v >= 70 for v in recent_3):
            if self._check_cooldown_daily("bio_fatigue_streak", now):
                actions.append(
                    {
                        "tool": "speak",
                        "args": {
                            "message": "3日連続で疲労度が高い状態が続いています。今日は早めに休んでください。",
                            "zone": "home",
                            "tone": "caring",
                        },
                    }
                )
                actions.append(
                    {
                        "tool": "create_task",
                        "args": {
                            "title": "疲労蓄積アラート: 3日連続で疲労度70以上",
                            "description": (
                                f"直近3日の疲労度ピーク: {recent_3[0]:.0f}, {recent_3[1]:.0f}, {recent_3[2]:.0f}。"
                                f"休息計画の見直しを検討してください。"
                            ),
                            "urgency": 3,
                            "zone": "home",
                            "task_type": ["fatigue_streak"],
                        },
                    }
                )
        return actions

    def _evaluate_sleep_decline(self, bio, now: float) -> list[dict]:
        """7-day rolling sleep quality average vs prior 7-day baseline. Trigger if drop ≥ 15%."""
        actions = []
        history = bio.history.get("sleep_quality") if bio.history else None
        if not history or len(history) < 14:
            return actions

        recent = [v for _, v in list(history)[-7:]]
        prior = [v for _, v in list(history)[-14:-7]]
        if not recent or not prior:
            return actions

        avg_recent = sum(recent) / len(recent)
        avg_prior = sum(prior) / len(prior)
        if avg_prior < 30:  # baseline too noisy
            return actions

        decline_pct = (avg_prior - avg_recent) / avg_prior
        if decline_pct >= 0.15 and self._check_cooldown_custom("bio_sleep_decline", now, 3 * 86400):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"睡眠の質が直近7日で{int(decline_pct * 100)}%低下しています。"
                            f"就寝時刻や環境を見直しましょう。"
                        ),
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
        return actions

    def _evaluate_stress_hr_coupling(self, bio, now: float) -> list[dict]:
        """15min sustained stress > 70 AND HR > resting baseline + 20%."""
        actions = []
        stress_hist = bio.history.get("stress") if bio.history else None
        hr_hist = bio.history.get("heart_rate") if bio.history else None
        if not stress_hist or not hr_hist:
            return actions

        cutoff_15min = now - 15 * 60
        recent_stress = [v for ts, v in stress_hist if ts >= cutoff_15min]
        recent_hr = [v for ts, v in hr_hist if ts >= cutoff_15min]

        if len(recent_stress) < 3 or len(recent_hr) < 3:
            return actions

        sustained_stress = sum(recent_stress) / len(recent_stress) > 70
        if not sustained_stress:
            return actions

        baseline_hr = bio.heart_rate.resting_bpm
        if not baseline_hr or baseline_hr <= 0:
            # Estimate baseline from HR history (lowest 10% over the window we have)
            all_hr = sorted(v for _, v in hr_hist)
            if len(all_hr) >= 10:
                baseline_hr = all_hr[len(all_hr) // 10]
            else:
                return actions

        avg_recent_hr = sum(recent_hr) / len(recent_hr)
        if avg_recent_hr >= baseline_hr * 1.2 and self._check_cooldown("bio_stress_hr_coupling", now):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"ストレスと心拍が連動して上昇しています。"
                            f"(平均ストレス{int(sum(recent_stress) / len(recent_stress))}, "
                            f"平均心拍{int(avg_recent_hr)}bpm)。深呼吸や休憩をどうぞ。"
                        ),
                        "zone": "home",
                        "tone": "caring",
                    },
                }
            )
        return actions

    def _eval_critical_spo2(self, bio, now: float) -> list[dict]:
        """C4 SpO2 critical drop (sleep apnea risk) — evaluate_critical block.

        Fires when SpO2 is below the critical threshold AND the reading is fresh
        (within 300 s).  Uses cooldown key ``critical_spo2``.
        """
        actions: list[dict] = []
        if (
            bio.spo2.percent is not None
            and bio.spo2.percent < self.thresholds.spo2_critical_low
            and bio.spo2.last_update > now - 300
            and self._check_cooldown("critical_spo2", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (
                            f"緊急！血中酸素濃度が{bio.spo2.percent}%まで低下しています！目を覚ましてください！"
                        ),
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )
        return actions

    def _eval_critical_hr_sleep(self, bio, now: float) -> list[dict]:
        """C5 Very high heart rate during sleep — evaluate_critical block.

        Fires when HR exceeds the sleep-critical threshold AND sleep stage is
        active AND the reading is fresh (within 120 s).  Uses cooldown key
        ``critical_hr_sleep``.
        """
        actions: list[dict] = []
        if (
            bio.heart_rate.bpm is not None
            and bio.heart_rate.bpm > self.thresholds.hr_critical_sleep
            and bio.sleep.stage in ("deep", "light", "rem")
            and bio.heart_rate.last_update > now - 120
            and self._check_cooldown("critical_hr_sleep", now)
        ):
            actions.append(
                {
                    "tool": "speak",
                    "args": {
                        "message": (f"睡眠中に心拍数が{bio.heart_rate.bpm}bpmに達しています！体調を確認してください！"),
                        "zone": "home",
                        "tone": "alert",
                    },
                }
            )
        return actions
