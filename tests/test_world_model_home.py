"""
Tests for WorldModel Home Assistant topic processing.
"""
import pytest


class TestWorldModelHomeDevices:
    def test_light_state_from_mqtt(self, world_model):
        """hems/home/{zone}/light/{entity_id}/state updates light state."""
        world_model.update_from_mqtt(
            "hems/home/living_room/light/light.living_room/state",
            {"state": "on", "on": True, "brightness": 200, "color_temp": 300},
        )
        hd = world_model.home_devices
        assert hd.bridge_connected is True
        assert "light.living_room" in hd.lights
        light = hd.lights["light.living_room"]
        assert light.on is True
        assert light.brightness == 200
        assert light.color_temp == 300

    def test_climate_state_from_mqtt(self, world_model):
        """hems/home/{zone}/climate/{entity_id}/state updates climate state."""
        world_model.update_from_mqtt(
            "hems/home/living_room/climate/climate.living_room/state",
            {"state": "cool", "hvac_mode": "cool", "temperature": 26,
             "current_temperature": 28.5, "fan_mode": "auto"},
        )
        hd = world_model.home_devices
        assert "climate.living_room" in hd.climates
        climate = hd.climates["climate.living_room"]
        assert climate.mode == "cool"
        assert climate.target_temp == 26
        assert climate.current_temp == 28.5

    def test_cover_state_from_mqtt(self, world_model):
        """hems/home/{zone}/cover/{entity_id}/state updates cover state."""
        world_model.update_from_mqtt(
            "hems/home/bedroom/cover/cover.bedroom/state",
            {"state": "open", "is_open": True, "current_position": 100},
        )
        hd = world_model.home_devices
        assert "cover.bedroom" in hd.covers
        cover = hd.covers["cover.bedroom"]
        assert cover.is_open is True
        assert cover.position == 100

    def test_switch_state_from_mqtt(self, world_model):
        """hems/home/{zone}/switch/{entity_id}/state updates switch state."""
        world_model.update_from_mqtt(
            "hems/home/living_room/switch/switch.plug/state",
            {"state": "on", "on": True},
        )
        hd = world_model.home_devices
        assert hd.switches.get("switch.plug") is True

    def test_bridge_status(self, world_model):
        """hems/home/bridge/status updates bridge_connected."""
        world_model.update_from_mqtt(
            "hems/home/bridge/status",
            {"connected": True, "mode": "websocket"},
        )
        assert world_model.home_devices.bridge_connected is True

        world_model.update_from_mqtt(
            "hems/home/bridge/status",
            {"connected": False, "mode": "disconnected"},
        )
        assert world_model.home_devices.bridge_connected is False

    def test_light_off_state(self, world_model):
        """Light turning off updates correctly."""
        world_model.update_from_mqtt(
            "hems/home/bedroom/light/light.bedroom/state",
            {"state": "off", "on": False, "brightness": 0},
        )
        light = world_model.home_devices.lights["light.bedroom"]
        assert light.on is False
        assert light.brightness == 0

    def test_multiple_devices(self, world_model):
        """Multiple devices coexist in home_devices."""
        world_model.update_from_mqtt(
            "hems/home/living/light/light.living/state",
            {"on": True, "brightness": 200},
        )
        world_model.update_from_mqtt(
            "hems/home/bedroom/light/light.bedroom/state",
            {"on": False, "brightness": 0},
        )
        world_model.update_from_mqtt(
            "hems/home/living/climate/climate.living/state",
            {"hvac_mode": "cool", "temperature": 26, "current_temperature": 28},
        )
        hd = world_model.home_devices
        assert len(hd.lights) == 2
        assert len(hd.climates) == 1


class TestWorldModelHomeLLMContext:
    def test_no_context_when_disconnected(self, world_model):
        """No smart home section when bridge not connected."""
        context = world_model.get_llm_context()
        assert "スマートホーム" not in context

    def test_context_with_devices(self, world_model):
        """Smart home section appears when bridge is connected with devices."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        from world_model.data_classes import LightState, ClimateState, CoverState
        hd.lights["light.living_room"] = LightState(
            entity_id="light.living_room", on=True, brightness=200,
        )
        hd.climates["climate.living_room"] = ClimateState(
            entity_id="climate.living_room", mode="cool",
            target_temp=26, current_temp=28.5,
        )
        hd.covers["cover.bedroom"] = CoverState(
            entity_id="cover.bedroom", position=100, is_open=True,
        )

        context = world_model.get_llm_context()
        assert "スマートホーム" in context
        assert "照明" in context
        assert "エアコン" in context
        assert "カーテン" in context

    def test_context_light_percentage(self, world_model):
        """Light brightness shown as percentage."""
        hd = world_model.home_devices
        hd.bridge_connected = True
        from world_model.data_classes import LightState
        hd.lights["light.test"] = LightState(
            entity_id="light.test", on=True, brightness=128,
        )
        context = world_model.get_llm_context()
        # 128/255 * 100 ≈ 50%
        assert "50%" in context
