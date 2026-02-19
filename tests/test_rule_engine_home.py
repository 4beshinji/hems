"""
Tests for Home Assistant automation rules in RuleEngine.
"""
import time
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest
from rule_engine import RuleEngine
from schedule_learner import ScheduleLearner
from world_model.data_classes import (
    LightState, ClimateState, CoverState, HomeDevicesState, OccupancyData,
)


@pytest.fixture
def schedule_learner():
    return ScheduleLearner()


@pytest.fixture
def engine(schedule_learner):
    e = RuleEngine(schedule_learner=schedule_learner)
    e._cooldowns = {}
    return e


class TestSleepDetection:
    def test_sleep_detection_lights_off(self, engine, world_model):
        """Deep night + idle + static posture > 10 min → turn off lights."""
        engine._cooldowns = {}
        # Set up zone with idle, static occupancy
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1, activity_class="idle",
            posture_status="static", posture_duration_sec=700,
        )
        # Set up lights
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=True, brightness=200,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 23, 30)
            actions = engine.evaluate(world_model)

        light_actions = [a for a in actions if a["tool"] == "control_light"]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "おやすみ" in a["args"]["message"]]
        assert len(light_actions) >= 1
        assert light_actions[0]["args"]["on"] is False
        assert len(speak_actions) >= 1

    def test_no_sleep_detection_during_day(self, engine, world_model):
        """No sleep detection during daytime."""
        engine._cooldowns = {}
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1, activity_class="idle",
            posture_status="static", posture_duration_sec=700,
        )
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=True,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 14, 0)
            actions = engine.evaluate(world_model)

        light_actions = [a for a in actions if a["tool"] == "control_light"]
        assert len(light_actions) == 0

    def test_no_sleep_when_lights_already_off(self, engine, world_model):
        """No action when lights are already off."""
        engine._cooldowns = {}
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1, activity_class="idle",
            posture_status="static", posture_duration_sec=700,
        )
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=False,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 23, 30)
            actions = engine.evaluate(world_model)

        light_actions = [a for a in actions if a["tool"] == "control_light"]
        assert len(light_actions) == 0


class TestPreArrivalHVAC:
    def test_prearrival_hvac_summer(self, engine, world_model, schedule_learner):
        """Predicted arrival in 20 min + nobody home → climate turn on (cool mode in summer)."""
        engine._cooldowns = {}
        now = time.time()
        # Nobody home
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=0)

        # Climate device exists
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.climates["climate.living_room"] = ClimateState(
            entity_id="climate.living_room", mode="off",
        )

        # Mock schedule learner to predict arrival in 20 minutes
        schedule_learner.predict_next_arrival = MagicMock(return_value=now + 20 * 60)

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 17, 40)
            actions = engine.evaluate(world_model)

        climate_actions = [a for a in actions if a["tool"] == "control_climate"]
        assert len(climate_actions) >= 1
        assert climate_actions[0]["args"]["mode"] == "cool"
        assert climate_actions[0]["args"]["temperature"] == 26

    def test_prearrival_hvac_winter(self, engine, world_model, schedule_learner):
        """Winter → heat mode."""
        engine._cooldowns = {}
        now = time.time()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=0)
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.climates["climate.living_room"] = ClimateState(
            entity_id="climate.living_room", mode="off",
        )
        schedule_learner.predict_next_arrival = MagicMock(return_value=now + 20 * 60)

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 15, 17, 40)
            actions = engine.evaluate(world_model)

        climate_actions = [a for a in actions if a["tool"] == "control_climate"]
        assert len(climate_actions) >= 1
        assert climate_actions[0]["args"]["mode"] == "heat"

    def test_no_hvac_when_home(self, engine, world_model, schedule_learner):
        """No pre-arrival HVAC when someone is already home."""
        engine._cooldowns = {}
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=1)
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.climates["climate.living_room"] = ClimateState(
            entity_id="climate.living_room", mode="off",
        )
        schedule_learner.predict_next_arrival = MagicMock(return_value=time.time() + 20 * 60)

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 17, 40)
            actions = engine.evaluate(world_model)

        climate_actions = [a for a in actions if a["tool"] == "control_climate"]
        assert len(climate_actions) == 0


class TestWakeUpCurtain:
    def test_wake_curtain_opens(self, engine, world_model, schedule_learner):
        """60 min before predicted wake → open curtains."""
        engine._cooldowns = {}
        now = time.time()
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.covers["cover.bedroom"] = CoverState(
            entity_id="cover.bedroom", position=0, is_open=False,
        )
        schedule_learner.get_wake_time = MagicMock(return_value=now + 45 * 60)

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 6, 15)
            actions = engine.evaluate(world_model)

        cover_actions = [a for a in actions if a["tool"] == "control_cover"]
        assert len(cover_actions) >= 1
        assert cover_actions[0]["args"]["action"] == "open"

    def test_no_curtain_when_already_open(self, engine, world_model, schedule_learner):
        """No action when covers are already open."""
        engine._cooldowns = {}
        now = time.time()
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.covers["cover.bedroom"] = CoverState(
            entity_id="cover.bedroom", position=100, is_open=True,
        )
        schedule_learner.get_wake_time = MagicMock(return_value=now + 45 * 60)

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 6, 15)
            actions = engine.evaluate(world_model)

        cover_actions = [a for a in actions if a["tool"] == "control_cover"]
        assert len(cover_actions) == 0


class TestWakeDetection:
    def test_wake_detection_lights_on(self, engine, world_model):
        """Morning + activity detected → turn on lights + greeting."""
        engine._cooldowns = {}
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1, activity_class="moderate",
        )
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=False,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 7, 0)
            actions = engine.evaluate(world_model)

        light_actions = [a for a in actions if a["tool"] == "control_light"]
        speak_actions = [a for a in actions if a["tool"] == "speak" and "おはよう" in a["args"]["message"]]
        assert len(light_actions) >= 1
        assert light_actions[0]["args"]["on"] is True
        assert len(speak_actions) >= 1

    def test_no_wake_detection_afternoon(self, engine, world_model):
        """No wake detection in the afternoon."""
        engine._cooldowns = {}
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(count=1, activity_class="moderate")
        world_model.home_devices.bridge_connected = True
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=False,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 15, 0)
            actions = engine.evaluate(world_model)

        wake_lights = [a for a in actions if a["tool"] == "control_light" and a["args"].get("on")]
        assert len(wake_lights) == 0


class TestCooldownAndBridgeDisconnected:
    def test_no_rules_when_bridge_disconnected(self, engine, world_model):
        """No HA rules when bridge is not connected."""
        engine._cooldowns = {}
        world_model.home_devices.bridge_connected = False
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1, activity_class="idle",
            posture_status="static", posture_duration_sec=700,
        )
        world_model.home_devices.lights["light.bedroom"] = LightState(
            entity_id="light.bedroom", on=True,
        )

        with patch("rule_engine.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 20, 23, 30)
            actions = engine.evaluate(world_model)

        light_actions = [a for a in actions if a["tool"] == "control_light"]
        assert len(light_actions) == 0
