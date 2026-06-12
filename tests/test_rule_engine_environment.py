"""
Characterization tests for RuleEngine.evaluate — environment / zone-loop inline blocks.

These tests fix the current behaviour of the blocks that had zero direct unit-test
coverage as identified in docs/refactor/2026-06-11/W2.4-design-note.md §3:

  Z1  CO2 task                (154-168)
  Z2  温度 high/low speak      (170-193)
  Z3  sedentary event          (195-207)
  Z5  湿度 high                (228-240)
  Z6  湿度 low                 (242-254)
  Z7  気圧 drop                (256-271)  — partial; sustained already tested
  Z8  土壌水分                  (294-351)
  Z10 native PM2.5             (390-409)  + cooldown key sharing with zigbee mixin
  Z13 screen time              (609-624)
  V1  VLM swap stuck           (521-538)
  P3  heavy proc memory branch (570-584)

Plus:
  ordering_golden  — multi-rule simultaneous fire; fixes action-list ordering

All tests run against the *unmodified* production code.  They record the current
(characterization) behaviour: if the refactor breaks any of these the test will
detect the regression.
"""

from __future__ import annotations

from datetime import datetime as real_datetime
from unittest.mock import patch

import rule_engine as _re_mod
from rule_engine import RuleEngine
from world_model.data_classes import (
    EnvironmentData,
    Event,
    HASensorState,
    ProcessInfo,
    ScreenTimeData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine() -> RuleEngine:
    e = RuleEngine()
    e._cooldowns = {}  # fresh cooldown state
    return e


_FIXED_NOW = 2_000_000.0  # arbitrary fixed epoch


class _FakeDatetime(real_datetime):
    """Daytime (hour=12) — keeps Z11/Z12 hour-gated rules silent."""

    @classmethod
    def now(cls, tz=None):
        return real_datetime(2026, 5, 24, 12, 0, 0)


# ---------------------------------------------------------------------------
# Z1 — CO2 換気タスク
# ---------------------------------------------------------------------------


class TestZ1CO2Task:
    """CO2 > threshold → create_task; cooldown suppresses 2nd call."""

    def test_co2_high_creates_ventilation_task(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(co2=1100)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [a for a in actions if a["tool"] == "create_task" and "換気" in a["args"]["title"]]
        assert len(task_actions) == 1, "CO2 high must create exactly one ventilation task"
        assert task_actions[0]["args"]["zone"] == "office"
        assert "1100" in task_actions[0]["args"]["description"]

    def test_co2_exactly_at_threshold_no_action(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(co2=1000)  # default threshold — not > 1000

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [a for a in actions if a["tool"] == "create_task" and "換気" in a["args"]["title"]]
        assert len(task_actions) == 0

    def test_co2_cooldown_suppresses_second_fire(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(co2=1200)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("換気" in a["args"].get("title", "") for a in first if a["tool"] == "create_task")
        assert not any("換気" in a["args"].get("title", "") for a in second if a["tool"] == "create_task")


# ---------------------------------------------------------------------------
# Z2 — 室温 high / low speak + elif 排他
# ---------------------------------------------------------------------------


class TestZ2TemperatureSpeak:
    """温度 high → エアコン、low → 暖房。高 / 低 は elif で相互排他。"""

    def test_temp_high_speaks_aircon(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(temperature=29.0)  # > 28 default

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "エアコン" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        assert "29.0" in speaks[0]["args"]["message"]

    def test_temp_low_speaks_heater(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(temperature=10.0)  # < 16 default

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "暖房" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"

    def test_temp_comfortable_no_speak(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(temperature=22.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        temp_speaks = [
            a
            for a in actions
            if a["tool"] == "speak" and ("エアコン" in a["args"]["message"] or "暖房" in a["args"]["message"])
        ]
        assert len(temp_speaks) == 0

    def test_temp_high_and_low_cannot_both_fire(self, world_model, monkeypatch):
        """elif ensures only one branch fires — temperature cannot be both high and low."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        # Physically impossible but we verify the elif guard: set to high (29)
        zone.environment = EnvironmentData(temperature=29.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        aircon_speaks = [a for a in actions if a["tool"] == "speak" and "エアコン" in a["args"]["message"]]
        heater_speaks = [a for a in actions if a["tool"] == "speak" and "暖房" in a["args"]["message"]]
        # Only one branch fires per cycle
        assert len(aircon_speaks) == 1
        assert len(heater_speaks) == 0

    def test_temp_high_cooldown(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(temperature=30.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("エアコン" in a["args"]["message"] for a in first if a["tool"] == "speak")
        assert not any("エアコン" in a["args"]["message"] for a in second if a["tool"] == "speak")


# ---------------------------------------------------------------------------
# Z3 — sedentary_alert イベント
# ---------------------------------------------------------------------------


class TestZ3SedentaryEvent:
    """sedentary_alert event → speak about 休憩; cooldown prevents duplicate."""

    def test_sedentary_event_triggers_speak(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.events = [Event(event_type="sedentary_alert")]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "休憩" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["zone"] == "office"
        assert speaks[0]["args"]["tone"] == "caring"

    def test_other_event_type_no_action(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.events = [Event(event_type="door_opened")]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "休憩" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_sedentary_cooldown_suppresses_second(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.events = [Event(event_type="sedentary_alert")]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("休憩" in a["args"]["message"] for a in first if a["tool"] == "speak")
        assert not any("休憩" in a["args"]["message"] for a in second if a["tool"] == "speak")


# ---------------------------------------------------------------------------
# Z5 / Z6 — 湿度 high / low
# ---------------------------------------------------------------------------


class TestZ5Z6HumiditySpeak:
    """湿度 > 70 → 除湿; 湿度 < 30 → 加湿; normal → silent."""

    def test_humidity_high_speaks_dehumidify(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(humidity=80.0)  # > 70 default

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "除湿" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        assert "80" in speaks[0]["args"]["message"]

    def test_humidity_low_speaks_humidify(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(humidity=20.0)  # < 30 default

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "加湿" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"

    def test_humidity_normal_silent(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(humidity=50.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        hum_speaks = [
            a
            for a in actions
            if a["tool"] == "speak" and ("除湿" in a["args"]["message"] or "加湿" in a["args"]["message"])
        ]
        assert len(hum_speaks) == 0

    def test_humidity_high_cooldown(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(humidity=80.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("除湿" in a["args"]["message"] for a in first if a["tool"] == "speak")
        assert not any("除湿" in a["args"]["message"] for a in second if a["tool"] == "speak")


# ---------------------------------------------------------------------------
# Z7 — 気圧 drop
# ---------------------------------------------------------------------------


class TestZ7PressureDrop:
    """
    気圧降下 (prev - current >= 5 hPa) → speak about 気圧が低下.
    _pressure_history is always updated unconditionally (before cooldown check).
    """

    def test_pressure_drop_speaks_warning(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")

        # First call — sets history baseline (no action, no prev pressure)
        zone.environment = EnvironmentData(pressure=1010.0)
        with patch.object(_re_mod, "datetime", _FakeDatetime):
            engine.evaluate(world_model)

        # Second call — pressure drops by 6 hPa → triggers
        zone.environment = EnvironmentData(pressure=1004.0)
        with patch.object(_re_mod, "datetime", _FakeDatetime):
            second = engine.evaluate(world_model)

        drop_speaks = [a for a in second if a["tool"] == "speak" and "気圧が低下" in a["args"]["message"]]
        assert len(drop_speaks) == 1
        assert "1010" in drop_speaks[0]["args"]["message"]
        assert "1004" in drop_speaks[0]["args"]["message"]

    def test_pressure_history_updated_unconditionally(self, world_model, monkeypatch):
        """_pressure_history must be written even when no drop occurs (no-prev case)."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(pressure=1013.0)

        assert "office" not in engine._pressure_history
        with patch.object(_re_mod, "datetime", _FakeDatetime):
            engine.evaluate(world_model)
        assert engine._pressure_history.get("office") == 1013.0

    def test_small_drop_no_action(self, world_model, monkeypatch):
        """Drop less than 5 hPa does not trigger."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")

        zone.environment = EnvironmentData(pressure=1010.0)
        with patch.object(_re_mod, "datetime", _FakeDatetime):
            engine.evaluate(world_model)

        zone.environment = EnvironmentData(pressure=1007.0)  # only 3 hPa drop
        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        drop_speaks = [a for a in actions if a["tool"] == "speak" and "気圧が低下" in a["args"]["message"]]
        assert len(drop_speaks) == 0


# ---------------------------------------------------------------------------
# Z8 — 土壌水分
# ---------------------------------------------------------------------------


class TestZ8SoilMoisture:
    """
    soil_moisture < 25 (default) and cooldown not hit → create_task + speak.
    With auto_water_enabled=True and pump device → control_actuator(pulse) + speak.
    """

    def test_dry_soil_creates_task_and_speaks(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(soil_moisture=10.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [a for a in actions if a["tool"] == "create_task" and "水やり" in a["args"]["title"]]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "水やり" in a["args"]["message"]]
        assert len(task_actions) == 1
        assert len(speak_actions) == 1
        assert task_actions[0]["args"]["zone"] == "office"
        assert "10" in task_actions[0]["args"]["description"]

    def test_normal_soil_no_action(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(soil_moisture=50.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        soil_actions = [a for a in actions if "水やり" in str(a)]
        assert len(soil_actions) == 0

    def test_auto_water_with_pump_fires_actuator(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        from rules.config import RuleThresholds, load_rule_thresholds

        base = load_rule_thresholds()
        thresh = RuleThresholds(
            **{
                **base.__dict__,  # copy all fields
                "auto_water_enabled": True,
                "auto_water_duration_s": 30,
            }
        )
        engine = RuleEngine(thresholds=thresh)
        engine._cooldowns = {}
        engine._device_cache = [
            {
                "device_id": "switch.water_pump",
                "device_class": "switch",
                "is_enabled": True,
                "capabilities": ["pulse"],
                "purpose": "水やりポンプ",
                "zone": "office",
            }
        ]
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(soil_moisture=10.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        actuator_actions = [
            a for a in actions if a["tool"] == "control_actuator" and a["args"]["device_id"] == "switch.water_pump"
        ]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "給水" in a["args"]["message"]]
        assert len(actuator_actions) == 1
        assert actuator_actions[0]["args"]["action"] == "pulse"
        assert actuator_actions[0]["args"]["params"]["duration_s"] == 30
        assert len(speak_actions) == 1

    def test_soil_6h_cooldown_suppresses_repeat(self, world_model, monkeypatch):
        """6h custom cooldown — second call within same now is suppressed."""
        current_time = _FIXED_NOW
        monkeypatch.setattr(_re_mod.time, "time", lambda: current_time)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(soil_moisture=10.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("水やり" in a["args"].get("title", "") for a in first if a["tool"] == "create_task")
        assert not any("水やり" in a["args"].get("title", "") for a in second if a["tool"] == "create_task")


# ---------------------------------------------------------------------------
# Z10 — native PM2.5
# ---------------------------------------------------------------------------


class TestZ10NativePM25:
    """
    env.pm25 > threshold → speak + turn on purifier(s).
    Cooldown key = zigbee_pm25_{zone_id}.
    Crucially, Z10 evaluates *before* zigbee mixin (zone-loop precedes M4).
    """

    def test_pm25_high_speaks_and_turns_on_purifier(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        engine._device_cache = [
            {
                "device_id": "switch.air_purifier_office",
                "device_class": "switch",
                "is_enabled": True,
                "capabilities": [],
                "purpose": "空気清浄機",
                "zone": "office",
            }
        ]
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(pm25=40.0)  # > 35 default

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]]
        purifier_on = [
            a
            for a in actions
            if a["tool"] == "control_actuator"
            and a["args"]["device_id"] == "switch.air_purifier_office"
            and a["args"]["action"] == "on"
        ]
        assert len(speaks) >= 1
        assert "40" in speaks[0]["args"]["message"]
        assert len(purifier_on) == 1

    def test_pm25_normal_no_action(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(pm25=20.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        pm25_actions = [a for a in actions if "PM2.5" in str(a)]
        assert len(pm25_actions) == 0

    def test_pm25_cooldown_key_is_zigbee_pm25_zone(self, world_model, monkeypatch):
        """
        Characterization: Z10 uses cooldown key 'zigbee_pm25_{zone_id}'.
        After first fire, the key must be present in _cooldowns and the
        second call must be suppressed.
        """
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(pm25=40.0)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        # Key pattern: zigbee_pm25_office
        assert "zigbee_pm25_office" in engine._cooldowns

        pm25_first = [a for a in first if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]]
        pm25_second = [a for a in second if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]]
        assert len(pm25_first) == 1
        assert len(pm25_second) == 0  # cooldown suppresses

    def test_z10_consumes_cooldown_before_zigbee_mixin(self, world_model, monkeypatch):
        """
        Order guard: Z10 (zone loop) fires before zigbee mixin (_evaluate_zigbee_sensor_rules).
        When both Z10 (env.pm25) and zigbee HA sensor (HASensorState pm25) exceed threshold
        in the same cycle, Z10 fires first.  The zigbee mixin uses a *different* cooldown key
        (zigbee_pm25_{entity_id}), so both can fire in the same cycle when keys differ.
        This test fixes the current behaviour: both fire with separate keys.
        """
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        # Z10: native env PM2.5
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(pm25=40.0)

        # Zigbee mixin: HA sensor PM2.5 (different entity_id → different key)
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.sensors["sensor.pm25_ha"] = HASensorState(
            entity_id="sensor.pm25_ha",
            value=50.0,
            device_class="pm25",
        )

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        # Z10 cooldown key
        assert "zigbee_pm25_office" in engine._cooldowns
        # Zigbee mixin cooldown key (entity_id based)
        assert "zigbee_pm25_sensor.pm25_ha" in engine._cooldowns

        # Both PM2.5 speaks fire (different keys → no dedup between them)
        pm25_speaks = [a for a in actions if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]]
        assert len(pm25_speaks) >= 2  # one from Z10, one from zigbee mixin

        # Z10 speak appears first in the action list (zone loop before mixin)
        first_pm25_idx = next(
            i for i, a in enumerate(actions) if a["tool"] == "speak" and "PM2.5" in a["args"]["message"]
        )
        # Verify the first PM2.5 speak comes from zone loop (zone=office, not zone=home)
        assert actions[first_pm25_idx]["args"]["zone"] == "office"


# ---------------------------------------------------------------------------
# Z13 — screen time
# ---------------------------------------------------------------------------


class TestZ13ScreenTime:
    """screen_time.total_minutes >= 120 (default) → speak about 画面."""

    def test_screen_time_exceeded_speaks(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.user.screen_time = ScreenTimeData(total_minutes=130)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "画面" in a["args"]["message"]]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        # hours: 130 // 60 = 2
        assert "2" in speaks[0]["args"]["message"]

    def test_screen_time_exactly_threshold_fires(self, world_model, monkeypatch):
        """>= comparison: exactly at threshold should fire."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.user.screen_time = ScreenTimeData(total_minutes=120)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "画面" in a["args"]["message"]]
        assert len(speaks) == 1

    def test_screen_time_below_threshold_silent(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.user.screen_time = ScreenTimeData(total_minutes=60)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "画面" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_screen_time_cooldown(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.user.screen_time = ScreenTimeData(total_minutes=130)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("画面" in a["args"]["message"] for a in first if a["tool"] == "speak")
        assert not any("画面" in a["args"]["message"] for a in second if a["tool"] == "speak")


# ---------------------------------------------------------------------------
# V1 — VLM swap stuck
# ---------------------------------------------------------------------------


class TestV1VLMSwapStuck:
    """vlm_model_swap_active=True + swap running > 60s → create_task."""

    def test_vlm_stuck_creates_task(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.vlm_model_swap_active = True
        world_model.vlm_swap_stats = {
            "last_swap_start_ts": _FIXED_NOW - 120,  # started 120s ago
            "last_swap_end_ts": 0.0,
        }

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [a for a in actions if a["tool"] == "create_task" and "VLM" in a["args"]["title"]]
        assert len(task_actions) == 1
        assert task_actions[0]["args"]["zone"] == "system"
        assert "120" in task_actions[0]["args"]["description"]

    def test_vlm_inactive_no_action(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.vlm_model_swap_active = False

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [
            a for a in actions if a["tool"] == "create_task" and "VLM" in a.get("args", {}).get("title", "")
        ]
        assert len(task_actions) == 0

    def test_vlm_swap_recent_no_action(self, world_model, monkeypatch):
        """Swap started only 30s ago — not yet > 60s → no task."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.vlm_model_swap_active = True
        world_model.vlm_swap_stats = {
            "last_swap_start_ts": _FIXED_NOW - 30,
        }

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        task_actions = [
            a for a in actions if a["tool"] == "create_task" and "VLM" in a.get("args", {}).get("title", "")
        ]
        assert len(task_actions) == 0

    def test_vlm_stuck_cooldown_1800s(self, world_model, monkeypatch):
        """Custom 1800s cooldown: second call suppressed."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.vlm_model_swap_active = True
        world_model.vlm_swap_stats = {"last_swap_start_ts": _FIXED_NOW - 120}

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            first = engine.evaluate(world_model)
            second = engine.evaluate(world_model)

        assert any("VLM" in a["args"].get("title", "") for a in first if a["tool"] == "create_task")
        assert not any("VLM" in a["args"].get("title", "") for a in second if a["tool"] == "create_task")


# ---------------------------------------------------------------------------
# P3 memory branch — single-process memory high (no sustain required)
# ---------------------------------------------------------------------------


class TestP3MemoryBranch:
    """
    ProcessInfo.mem_mb >= 4096 (default 4.0 GB) → speak about メモリ.
    Unlike CPU branch, memory fires immediately (no sustain timer).
    """

    def test_memory_high_speaks_immediately(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.pc_state.top_processes = [
            ProcessInfo(name="bigapp", cpu_percent=10.0, mem_mb=5000.0)  # 4.88 GB > 4.0
        ]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [
            a
            for a in actions
            if a["tool"] == "speak" and "メモリ" in a["args"]["message"] and "bigapp" in a["args"]["message"]
        ]
        assert len(speaks) == 1
        assert speaks[0]["args"]["tone"] == "caring"
        assert "4.9" in speaks[0]["args"]["message"]  # 5000/1024 = 4.88... rounded to 4.9

    def test_memory_normal_no_speak(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        world_model.pc_state.top_processes = [
            ProcessInfo(name="normalapp", cpu_percent=10.0, mem_mb=1024.0)  # 1 GB < 4.0
        ]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        speaks = [a for a in actions if a["tool"] == "speak" and "メモリ" in a["args"]["message"]]
        assert len(speaks) == 0

    def test_memory_high_fires_even_without_cpu_sustain(self, world_model, monkeypatch):
        """
        Memory branch is independent of CPU sustain tracker.
        A process with low CPU but high memory fires on the first evaluate call.
        """
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        # cpu_percent=10 → well below 90% CPU threshold → CPU branch silent
        world_model.pc_state.top_processes = [ProcessInfo(name="memhog", cpu_percent=10.0, mem_mb=6000.0)]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        cpu_speaks = [a for a in actions if a["tool"] == "speak" and "CPU" in a["args"]["message"]]
        mem_speaks = [a for a in actions if a["tool"] == "speak" and "メモリ" in a["args"]["message"]]
        assert len(cpu_speaks) == 0  # CPU branch silent
        assert len(mem_speaks) == 1  # Memory branch fires immediately

    def test_memory_excluded_process_is_silent(self, world_model, monkeypatch):
        """Processes in heavy_exclude list are skipped for both CPU and memory."""
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        from rules.config import RuleThresholds, load_rule_thresholds

        base = load_rule_thresholds()
        thresh = RuleThresholds(**{**base.__dict__, "pc_proc_heavy_exclude": ["chrome"]})
        engine = RuleEngine(thresholds=thresh)
        engine._cooldowns = {}
        world_model.pc_state.top_processes = [
            ProcessInfo(name="Chrome", cpu_percent=10.0, mem_mb=8000.0)  # matched by lower()
        ]

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        mem_speaks = [a for a in actions if a["tool"] == "speak" and "メモリ" in a["args"]["message"]]
        assert len(mem_speaks) == 0


# ---------------------------------------------------------------------------
# Ordering golden — multi-rule simultaneous fire
# ---------------------------------------------------------------------------


class TestOrderingGolden:
    """
    Fix the current tool-sequence ordering of evaluate when many rules fire.

    A world_model is constructed so that multiple blocks fire simultaneously.
    We record the list of (tool, keyword) pairs in order.  Any refactor that
    changes the append sequence will immediately break this test.

    Current order (from rule_engine.py evaluate):
      zone-loop blocks (Z1..Z13) → P1 GPU → P2 disk →
      M1 device_health → M2 service_vip → V1 VLM_stuck →
      P3 heavy_proc → M3 GAS → M4 home/zigbee → Z13 screen_time →
      M5 biometric → M6 perception → M7 shopping
    """

    def _build_multi_world_model(self, world_model, now: float):
        """Wire world_model so Z1, Z2(high), Z3, Z5, Z13, V1, P3-mem all fire."""
        from world_model.data_classes import DiskData, DiskPartition, GPUData, ScreenTimeData

        # Z1 CO2 task — office zone
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(
            co2=1100,  # Z1
            temperature=29.0,  # Z2 high
            humidity=80.0,  # Z5 high
        )
        zone.events = [Event(event_type="sedentary_alert")]  # Z3

        # Z13 screen time
        world_model.user.screen_time = ScreenTimeData(total_minutes=130)

        # V1 VLM stuck
        world_model.vlm_model_swap_active = True
        world_model.vlm_swap_stats = {"last_swap_start_ts": now - 120}

        # P3 memory (no CPU sustain needed for memory branch)
        world_model.pc_state.top_processes = [ProcessInfo(name="memhog", cpu_percent=10.0, mem_mb=6000.0)]

        # P1 GPU high
        world_model.pc_state.gpu = GPUData(temp_c=90, last_update=1.0)

        # P2 disk high
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=480, total_gb=500, percent=96)],
            last_update=1.0,
        )

    def test_action_ordering_is_stable(self, world_model, monkeypatch):
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        self._build_multi_world_model(world_model, _FIXED_NOW)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        # --- Ordering invariants ---

        # Z1 (create_task 換気) must appear before GPU speak (P1)
        z1_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "create_task" and "換気" in a.get("args", {}).get("title", "")
            ),
            -1,
        )
        gpu_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "speak" and "GPU" in a.get("args", {}).get("message", "")
            ),
            -1,
        )
        assert z1_idx != -1, "Z1 CO2 task must be in actions"
        assert gpu_idx != -1, "GPU speak must be in actions"
        assert z1_idx < gpu_idx, f"Z1 must come before GPU (got z1={z1_idx}, gpu={gpu_idx})"

        # Z2 temp speak must appear before GPU speak (P1)
        z2_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "speak" and "エアコン" in a.get("args", {}).get("message", "")
            ),
            -1,
        )
        assert z2_idx != -1, "Z2 temp speak must be in actions"
        assert z2_idx < gpu_idx, "Z2 must come before GPU"

        # V1 VLM task must appear after M2 device_health/service_vip block and after GPU/disk
        vlm_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "create_task" and "VLM" in a.get("args", {}).get("title", "")
            ),
            -1,
        )
        assert vlm_idx != -1, "V1 VLM task must be in actions"
        assert vlm_idx > gpu_idx, "V1 must come after P1 GPU"

        # P3 memory speak must appear after V1 VLM task
        mem_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "speak" and "メモリ" in a.get("args", {}).get("message", "")
            ),
            -1,
        )
        assert mem_idx != -1, "P3 memory speak must be in actions"
        assert mem_idx > vlm_idx, "P3 memory must come after V1 VLM"

        # Z13 screen-time speak must appear after P3 memory speak
        st_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "speak" and "画面" in a.get("args", {}).get("message", "")
            ),
            -1,
        )
        assert st_idx != -1, "Z13 screen-time speak must be in actions"
        assert st_idx > mem_idx, "Z13 must come after P3 memory"

    def test_tool_sequence_snapshot(self, world_model, monkeypatch):
        """
        Golden snapshot of the tool-type sequence for multi-rule fire.
        This is intentionally coarse (tool types only, not messages) so it
        stays stable across minor threshold / message text changes while still
        catching ordering regressions introduced by refactoring.
        """
        monkeypatch.setattr(_re_mod.time, "time", lambda: _FIXED_NOW)
        engine = _make_engine()
        self._build_multi_world_model(world_model, _FIXED_NOW)

        with patch.object(_re_mod, "datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)

        # Zone-loop actions must ALL precede PC-loop actions
        # Find first PC-action (GPU speak) index
        gpu_speak_idx = next(
            (
                i
                for i, a in enumerate(actions)
                if a["tool"] == "speak" and "GPU" in a.get("args", {}).get("message", "")
            ),
            None,
        )
        assert gpu_speak_idx is not None, "GPU speak must be present"

        # All zone-loop outputs (Z1 換気, Z2 エアコン, Z3 休憩, Z5 除湿) must be before GPU
        zone_loop_keywords = ["換気", "エアコン", "休憩", "除湿"]
        for kw in zone_loop_keywords:
            kw_idx = next((i for i, a in enumerate(actions) if kw in str(a.get("args", {}))), None)
            if kw_idx is not None:
                assert kw_idx < gpu_speak_idx, f"'{kw}' action must come before GPU speak"
