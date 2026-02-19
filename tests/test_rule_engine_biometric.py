"""
Tests for RuleEngine biometric rules.
"""
import time
from datetime import datetime
from unittest.mock import patch

import pytest
from world_model.data_classes import (
    BiometricState, HeartRateData, SleepData, ActivityData,
    StressData, FatigueData, LightState, HomeDevicesState,
)


class TestRuleEngineBiometricRules:
    """Test biometric-specific rules in the rule engine."""

    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    # --- Rule 1: High heart rate ---

    def test_high_hr_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.heart_rate.bpm = 130
        world_model.biometric_state.heart_rate.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        assert "130" in speaks[0]["args"]["message"]

    def test_normal_hr_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.heart_rate.bpm = 80
        world_model.biometric_state.heart_rate.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_hr_exactly_120_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.heart_rate.bpm = 120
        world_model.biometric_state.heart_rate.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_hr_none_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.heart_rate.bpm = None

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        assert len(speaks) == 0

    # --- Rule 2: High stress ---

    def test_high_stress_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.stress.level = 85
        world_model.biometric_state.stress.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "ストレス" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"

    def test_normal_stress_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.stress.level = 50
        world_model.biometric_state.stress.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "ストレス" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_high_stress_no_update_no_action(self, world_model):
        """Stress > 80 but last_update == 0 should not trigger."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.stress.level = 90
        world_model.biometric_state.stress.last_update = 0

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "ストレス" in a["args"]["message"]]
        assert len(speaks) == 0

    # --- Rule 3: High fatigue ---

    def test_high_fatigue_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 80
        world_model.biometric_state.fatigue.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "疲" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"

    def test_high_fatigue_evening_message(self, world_model):
        """Between 21-23h, fatigue message suggests sleeping early."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 80
        world_model.biometric_state.fatigue.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 22, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "早めに休み" in a["args"]["message"]]
        assert len(speaks) == 1

    def test_high_fatigue_daytime_message(self, world_model):
        """Outside 21-23h, fatigue message suggests a break."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 80
        world_model.biometric_state.fatigue.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 14, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "休憩しましょう" in a["args"]["message"]]
        assert len(speaks) == 1

    def test_normal_fatigue_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 40
        world_model.biometric_state.fatigue.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "疲" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_high_fatigue_no_update_no_action(self, world_model):
        """Fatigue > 70 but last_update == 0 should not trigger."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 80
        world_model.biometric_state.fatigue.last_update = 0

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "疲" in a["args"]["message"]]
        assert len(speaks) == 0

    # --- Rule 4: Poor sleep quality morning notification ---

    def test_poor_sleep_morning_triggers_speak(self, world_model):
        """Between 8-10 AM, poor sleep quality triggers notification."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.quality_score = 35
        world_model.biometric_state.sleep.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 9, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        assert "35" in speaks[0]["args"]["message"]

    def test_poor_sleep_outside_morning_no_action(self, world_model):
        """Outside 8-10 AM, poor sleep quality does not trigger."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.quality_score = 35
        world_model.biometric_state.sleep.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 14, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_good_sleep_morning_no_action(self, world_model):
        """Good sleep quality (>= 50) does not trigger even in morning."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.quality_score = 75
        world_model.biometric_state.sleep.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 9, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_sleep_quality_zero_no_action(self, world_model):
        """Sleep quality_score == 0 should not trigger (guard: > 0)."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.quality_score = 0

        mock_dt = datetime(2026, 2, 20, 9, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_poor_sleep_daily_cooldown(self, world_model):
        """Poor sleep morning notification has daily cooldown (24h)."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.quality_score = 30
        world_model.biometric_state.sleep.last_update = time.time()

        mock_dt = datetime(2026, 2, 20, 9, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions1 = engine.evaluate(world_model)
            actions2 = engine.evaluate(world_model)

        speaks1 = [a for a in actions1 if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        speaks2 = [a for a in actions2 if a["tool"] == "speak" and "睡眠品質" in a["args"]["message"]]
        assert len(speaks1) == 1
        assert len(speaks2) == 0

    # --- Rule 5: Step goal achievement ---

    def test_step_goal_reached_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 10500
        world_model.biometric_state.activity.steps_goal = 10000
        world_model.biometric_state.activity.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "humorous"
        assert "10500" in speaks[0]["args"]["message"]

    def test_step_goal_exact_triggers_speak(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 10000
        world_model.biometric_state.activity.steps_goal = 10000
        world_model.biometric_state.activity.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks) == 1

    def test_step_goal_not_reached_no_action(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 5000
        world_model.biometric_state.activity.steps_goal = 10000
        world_model.biometric_state.activity.last_update = time.time()

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_step_goal_zero_steps_no_action(self, world_model):
        """Steps == 0 should not trigger even if goal is 0."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 0
        world_model.biometric_state.activity.steps_goal = 10000

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_step_goal_zero_goal_no_action(self, world_model):
        """steps_goal == 0 should not trigger."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 5000
        world_model.biometric_state.activity.steps_goal = 0

        actions = engine.evaluate(world_model)
        speaks = [a for a in actions if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_step_goal_daily_cooldown(self, world_model):
        """Step goal achievement has daily cooldown."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.activity.steps = 12000
        world_model.biometric_state.activity.steps_goal = 10000
        world_model.biometric_state.activity.last_update = time.time()

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        speaks1 = [a for a in actions1 if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        speaks2 = [a for a in actions2 if a["tool"] == "speak" and "目標達成" in a["args"]["message"]]
        assert len(speaks1) == 1
        assert len(speaks2) == 0

    # --- Rule 6: Sleep stage + HA lights off ---

    def test_sleep_stage_ha_lights_off(self, world_model):
        """Sleep stage detection with HA connected turns off lights."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=200),
            "light.living": LightState(entity_id="light.living", on=True, brightness=150),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light" and a["args"]["on"] is False]
        speaks = [a for a in actions if a["tool"] == "speak" and "おやすみ" in a["args"]["message"]]
        assert len(light_offs) == 2
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"

    def test_sleep_stage_light_turns_off_lights(self, world_model):
        """Light sleep stage also triggers lights off."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "light"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=100),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light" and a["args"]["on"] is False]
        assert len(light_offs) == 1

    def test_sleep_stage_rem_turns_off_lights(self, world_model):
        """REM sleep stage also triggers lights off."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "rem"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=100),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light"]
        assert len(light_offs) == 1

    def test_sleep_stage_awake_no_lights_off(self, world_model):
        """Awake stage should not turn off lights."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "awake"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=200),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light" and a["args"].get("on") is False]
        assert len(light_offs) == 0

    def test_sleep_stage_no_ha_no_lights_off(self, world_model):
        """Sleep stage without HA bridge should not turn off lights."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = False
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=200),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light"]
        assert len(light_offs) == 0

    def test_sleep_stage_no_lights_on_no_action(self, world_model):
        """Sleep stage with all lights already off produces no control_light."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=False, brightness=0),
        }

        actions = engine.evaluate(world_model)
        light_offs = [a for a in actions if a["tool"] == "control_light"]
        speaks = [a for a in actions if a["tool"] == "speak" and "おやすみ" in a["args"]["message"]]
        assert len(light_offs) == 0
        assert len(speaks) == 0

    def test_sleep_stage_daily_cooldown(self, world_model):
        """Sleep stage lights off has daily cooldown."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.sleep.stage = "deep"
        world_model.biometric_state.sleep.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.bedroom": LightState(entity_id="light.bedroom", on=True, brightness=200),
        }

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        light_offs1 = [a for a in actions1 if a["tool"] == "control_light"]
        light_offs2 = [a for a in actions2 if a["tool"] == "control_light"]
        assert len(light_offs1) >= 1
        assert len(light_offs2) == 0

    # --- Rule 7: Fatigue-linked dimming ---

    def test_fatigue_dimming_evening(self, world_model):
        """Evening + high fatigue + HA lights on with high brightness -> dim."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 75
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=200),
        }

        mock_dt = datetime(2026, 2, 20, 22, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        assert len(dims) == 1
        assert dims[0]["args"]["entity_id"] == "light.living"
        assert dims[0]["args"]["on"] is True
        assert dims[0]["args"]["color_temp"] == 400

    def test_fatigue_dimming_multiple_lights(self, world_model):
        """Multiple bright lights should all be dimmed."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 75
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=200),
            "light.kitchen": LightState(entity_id="light.kitchen", on=True, brightness=150),
            "light.dim_one": LightState(entity_id="light.dim_one", on=True, brightness=50),
        }

        mock_dt = datetime(2026, 2, 20, 21, 30, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        # Only lights with brightness > 100 should be dimmed
        assert len(dims) == 2
        dimmed_ids = {a["args"]["entity_id"] for a in dims}
        assert "light.living" in dimmed_ids
        assert "light.kitchen" in dimmed_ids
        assert "light.dim_one" not in dimmed_ids

    def test_fatigue_dimming_not_outside_evening(self, world_model):
        """Dimming should not trigger outside 21-23h."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 75
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=200),
        }

        mock_dt = datetime(2026, 2, 20, 15, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        assert len(dims) == 0

    def test_fatigue_dimming_low_fatigue_no_action(self, world_model):
        """Fatigue <= 60 should not trigger dimming."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 55
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=200),
        }

        mock_dt = datetime(2026, 2, 20, 22, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        assert len(dims) == 0

    def test_fatigue_dimming_no_ha_no_action(self, world_model):
        """Dimming should not trigger without HA bridge."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 75
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = False
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=200),
        }

        mock_dt = datetime(2026, 2, 20, 22, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        assert len(dims) == 0

    def test_fatigue_dimming_light_already_dim_no_action(self, world_model):
        """Lights already dim (brightness <= 100) should not be dimmed further."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 75
        world_model.biometric_state.fatigue.last_update = time.time()

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights = {
            "light.living": LightState(entity_id="light.living", on=True, brightness=80),
        }

        mock_dt = datetime(2026, 2, 20, 22, 0, 0)
        with patch("rule_engine.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
            actions = engine.evaluate(world_model)

        dims = [a for a in actions if a["tool"] == "control_light"
                and a["args"].get("brightness") == 80]
        assert len(dims) == 0

    # --- Cooldown prevents repeated actions ---

    def test_hr_cooldown_prevents_duplicate(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.heart_rate.bpm = 130
        world_model.biometric_state.heart_rate.last_update = time.time()

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        hr1 = [a for a in actions1 if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        hr2 = [a for a in actions2 if a["tool"] == "speak" and "心拍数" in a["args"]["message"]]
        assert len(hr1) == 1
        assert len(hr2) == 0

    def test_stress_cooldown_prevents_duplicate(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.stress.level = 90
        world_model.biometric_state.stress.last_update = time.time()

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        stress1 = [a for a in actions1 if a["tool"] == "speak" and "ストレス" in a["args"]["message"]]
        stress2 = [a for a in actions2 if a["tool"] == "speak" and "ストレス" in a["args"]["message"]]
        assert len(stress1) == 1
        assert len(stress2) == 0

    def test_fatigue_cooldown_prevents_duplicate(self, world_model):
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.fatigue.score = 80
        world_model.biometric_state.fatigue.last_update = time.time()

        actions1 = engine.evaluate(world_model)
        actions2 = engine.evaluate(world_model)

        fatigue1 = [a for a in actions1 if a["tool"] == "speak" and "疲" in a["args"]["message"]]
        fatigue2 = [a for a in actions2 if a["tool"] == "speak" and "疲" in a["args"]["message"]]
        assert len(fatigue1) == 1
        assert len(fatigue2) == 0

    # --- No actions when bridge disconnected ---

    def test_no_biometric_rules_when_disconnected(self, world_model):
        """No biometric rules fire when bridge_connected is False."""
        engine = self._make_engine()
        world_model.biometric_state.bridge_connected = False
        world_model.biometric_state.heart_rate.bpm = 150
        world_model.biometric_state.heart_rate.last_update = time.time()
        world_model.biometric_state.stress.level = 95
        world_model.biometric_state.stress.last_update = time.time()
        world_model.biometric_state.fatigue.score = 90
        world_model.biometric_state.fatigue.last_update = time.time()
        world_model.biometric_state.sleep.quality_score = 20
        world_model.biometric_state.sleep.last_update = time.time()
        world_model.biometric_state.activity.steps = 15000
        world_model.biometric_state.activity.steps_goal = 10000
        world_model.biometric_state.activity.last_update = time.time()

        actions = engine.evaluate(world_model)
        bio_actions = [a for a in actions if any(
            kw in a["args"].get("message", "")
            for kw in ("心拍数", "ストレス", "疲", "睡眠品質", "目標達成", "おやすみ")
        )]
        assert len(bio_actions) == 0
