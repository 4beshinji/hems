"""
Tests for perception-related rules in RuleEngine.
"""
import time
from datetime import datetime as _real_dt
from unittest.mock import patch

import pytest

from rule_engine import RuleEngine
from world_model.data_classes import ZoneState, LightState


class _FakeDatetime(_real_dt):
    """datetime subclass that freezes .now() to 14:00 (inside 6-21h daytime window)."""
    @classmethod
    def now(cls, tz=None):
        if tz:
            return _real_dt(2026, 2, 21, 14, 0, 0, tzinfo=tz)
        return _real_dt(2026, 2, 21, 14, 0, 0)


@pytest.fixture
def engine():
    e = RuleEngine()
    e._cooldowns.clear()
    return e


class TestSittingDetection:
    def test_sitting_over_threshold_triggers_speak(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.posture_status = "sitting"
        zone.occupancy.posture_duration_sec = 3601  # just over 60 min threshold
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        actions = engine.evaluate(world_model)
        sitting_actions = [a for a in actions if "座りっぱなし" in a.get("args", {}).get("message", "")]
        assert len(sitting_actions) == 1
        assert sitting_actions[0]["tool"] == "speak"
        assert sitting_actions[0]["args"]["tone"] == "caring"

    def test_sitting_under_threshold_no_action(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.posture_status = "sitting"
        zone.occupancy.posture_duration_sec = 60  # 1 min
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        actions = engine.evaluate(world_model)
        sitting_actions = [a for a in actions if "座りっぱなし" in a.get("args", {}).get("message", "")]
        assert len(sitting_actions) == 0


class TestEmptyRoomDetection:
    def test_empty_room_with_lights_on_turns_off(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 0
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.living_room"] = LightState(on=True, brightness=200)

        actions = engine.evaluate(world_model)
        light_off = [a for a in actions if a.get("tool") == "control_light"
                     and a.get("args", {}).get("on") is False]
        assert len(light_off) >= 1

    def test_occupied_room_no_light_off(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.living_room"] = LightState(on=True, brightness=200)

        actions = engine.evaluate(world_model)
        # Perception empty-room rule should not fire when room is occupied
        percep_light_off = [a for a in actions if a.get("tool") == "control_light"
                            and "living_room" in a.get("args", {}).get("entity_id", "")]
        # Filter to only perception-based light off actions (associated with "空室" speak)
        empty_speaks = [a for a in actions if "空室" in a.get("args", {}).get("message", "")]
        assert len(empty_speaks) == 0


class TestLyingDetection:
    def test_daytime_lying_triggers_health_check(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.posture_status = "lying"
        zone.occupancy.posture_duration_sec = 900  # 15 min
        zone.occupancy.count = 1
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        with patch("rule_engine.datetime", _FakeDatetime):
            actions = engine.evaluate(world_model)
        lying_actions = [a for a in actions if "横になって" in a.get("args", {}).get("message", "")]
        assert len(lying_actions) == 1
        assert lying_actions[0]["tool"] == "speak"
        assert lying_actions[0]["args"]["tone"] == "caring"


class TestActivityDrop:
    def test_low_activity_with_presence_triggers_check(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.activity_level = 0.05
        zone.occupancy.count = 1
        zone.occupancy.posture_duration_sec = 1200  # 20 min
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        actions = engine.evaluate(world_model)
        drop_actions = [a for a in actions if "動きがない" in a.get("args", {}).get("message", "")]
        assert len(drop_actions) == 1
        assert drop_actions[0]["tool"] == "speak"

    def test_low_activity_empty_room_no_trigger(self, world_model, engine):
        zone = ZoneState(zone_id="living_room")
        zone.occupancy.activity_level = 0.05
        zone.occupancy.count = 0
        zone.occupancy.posture_duration_sec = 1200
        zone.occupancy.last_update = time.time()
        world_model.zones["living_room"] = zone

        actions = engine.evaluate(world_model)
        drop_actions = [a for a in actions if "動きがない" in a.get("args", {}).get("message", "")]
        assert len(drop_actions) == 0
