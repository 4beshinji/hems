"""
Tests for WorldModel tri-domain structure (PhysicalSpace / DigitalSpace / UserState)
and the guest mode feature.
"""

from world_model.data_classes import (
    PhysicalSpace, DigitalSpace, UserState,
    ZoneState, HomeDevicesState, LightState,
    PCState, ServicesState, GASState, KnowledgeState,
    BiometricState, HeartRateData, SleepData, ActivityData,
    StressData, FatigueData, SpO2Data,
    CPUData,
)


class TestTriDomainStructure:
    """WorldModel exposes three domain facade objects."""

    def test_physical_domain_exists(self, world_model):
        assert isinstance(world_model.physical, PhysicalSpace)

    def test_digital_domain_exists(self, world_model):
        assert isinstance(world_model.digital, DigitalSpace)

    def test_user_domain_exists(self, world_model):
        assert isinstance(world_model.user, UserState)


class TestPhysicalSpaceFields:
    def test_zones_is_dict(self, world_model):
        assert isinstance(world_model.physical.zones, dict)

    def test_home_devices_is_home_devices_state(self, world_model):
        assert isinstance(world_model.physical.home_devices, HomeDevicesState)


class TestDigitalSpaceFields:
    def test_pc_state_type(self, world_model):
        assert isinstance(world_model.digital.pc_state, PCState)

    def test_services_state_type(self, world_model):
        assert isinstance(world_model.digital.services_state, ServicesState)

    def test_gas_state_type(self, world_model):
        assert isinstance(world_model.digital.gas_state, GASState)

    def test_knowledge_state_type(self, world_model):
        assert isinstance(world_model.digital.knowledge_state, KnowledgeState)


class TestUserStateFields:
    def test_biometrics_type(self, world_model):
        assert isinstance(world_model.user.biometrics, BiometricState)

    def test_biometrics_has_sub_fields(self, world_model):
        bio = world_model.user.biometrics
        assert isinstance(bio.heart_rate, HeartRateData)
        assert isinstance(bio.sleep, SleepData)
        assert isinstance(bio.activity, ActivityData)
        assert isinstance(bio.stress, StressData)
        assert isinstance(bio.fatigue, FatigueData)
        assert isinstance(bio.spo2, SpO2Data)


class TestMQTTUpdatesPopulateDomains:
    """MQTT updates land on the correct domain."""

    def test_zone_update_via_occupancy(self, world_model):
        world_model.update_from_mqtt("office/main/camera/cam01/status", {
            "person_count": 2,
        })
        assert "main" in world_model.physical.zones
        assert world_model.physical.zones["main"].occupancy.count == 2

    def test_pc_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 60.0, "core_count": 12,
        })
        assert world_model.digital.pc_state.cpu.usage_percent == 60.0

    def test_home_device_mqtt_update(self, world_model):
        world_model.update_from_mqtt(
            "hems/home/living/light/light.living/state",
            {"on": True, "brightness": 180},
        )
        assert world_model.physical.home_devices.lights["light.living"].on is True
        assert world_model.physical.home_devices.lights["light.living"].brightness == 180

    def test_gas_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/gas/bridge/status", {"connected": True})
        assert world_model.digital.gas_state.bridge_connected is True

    def test_biometric_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 75,
        })
        assert world_model.user.biometrics.heart_rate.bpm == 75


class TestDomainMutation:
    """Direct mutation of domain fields works as expected."""

    def test_add_zone(self, world_model):
        world_model.physical.zones["kitchen"] = ZoneState(zone_id="kitchen")
        assert world_model.physical.zones["kitchen"].zone_id == "kitchen"

    def test_mutate_pc_state_cpu(self, world_model):
        world_model.digital.pc_state.cpu = CPUData(usage_percent=55.0, core_count=8)
        assert world_model.digital.pc_state.cpu.usage_percent == 55.0

    def test_mutate_home_devices_lights(self, world_model):
        world_model.physical.home_devices.lights["light.test"] = LightState(
            entity_id="light.test", on=True, brightness=200,
        )
        assert world_model.physical.home_devices.lights["light.test"].on is True

    def test_mutate_biometrics_heart_rate(self, world_model):
        world_model.user.biometrics.heart_rate.bpm = 72
        assert world_model.user.biometrics.heart_rate.bpm == 72


class TestExistingFunctionalityPreserved:
    def test_get_zone(self, world_model):
        from world_model.data_classes import EnvironmentData
        world_model.physical.zones["lab"] = ZoneState(
            zone_id="lab",
            environment=EnvironmentData(temperature=22.0),
        )
        zone = world_model.get_zone("lab")
        assert zone is not None
        assert zone.environment.temperature == 22.0

    def test_get_zone_returns_none_for_unknown(self, world_model):
        assert world_model.get_zone("nonexistent") is None

    def test_get_all_zones(self, world_model):
        world_model.physical.zones["a"] = ZoneState(zone_id="a")
        world_model.physical.zones["b"] = ZoneState(zone_id="b")
        assert set(world_model.get_all_zones()) == {"a", "b"}

    def test_get_llm_context_empty(self, world_model):
        assert world_model.get_llm_context() == ""

    def test_get_llm_context_tri_domain_headers(self, world_model):
        from world_model.data_classes import EnvironmentData
        world_model.physical.zones["main"] = ZoneState(
            zone_id="main",
            environment=EnvironmentData(temperature=24.0),
        )
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 30.0, "core_count": 4,
        })
        world_model.update_from_mqtt("hems/personal/biometrics/watch/heart_rate", {
            "bpm": 68,
        })
        ctx = world_model.get_llm_context()
        assert "## 現実空間" in ctx
        assert "## 電子空間" in ctx
        assert "## ユーザー状態" in ctx


class TestGuestMode:
    """Guest mode: temporary suppression of private automation for visitors."""

    def test_default_off(self, world_model):
        assert world_model.is_guest_mode is False
        assert world_model.guest_mode_expiry == 0.0

    def test_enable_activates(self, world_model):
        world_model.set_guest_mode(True, duration_hours=2)
        assert world_model.is_guest_mode is True
        assert world_model.guest_mode_expiry > 0.0

    def test_enable_default_duration_is_four_hours(self, world_model):
        import time
        before = time.time()
        world_model.set_guest_mode(True)
        after = time.time()
        window = world_model.guest_mode_expiry - before
        assert 4 * 3600 - 1 <= window <= 4 * 3600 + (after - before) + 1

    def test_disable_clears(self, world_model):
        world_model.set_guest_mode(True, duration_hours=4)
        world_model.set_guest_mode(False)
        assert world_model.is_guest_mode is False
        assert world_model.guest_mode_expiry == 0.0

    def test_auto_expiry(self, world_model):
        """Passing the expiry timestamp auto-disables without a manual call."""
        import time
        world_model._guest_mode_expiry = time.time() - 10
        assert world_model.is_guest_mode is False

    def test_re_enable_extends_window(self, world_model):
        world_model.set_guest_mode(True, duration_hours=1)
        first = world_model.guest_mode_expiry
        world_model.set_guest_mode(True, duration_hours=5)
        assert world_model.guest_mode_expiry > first

    def test_negative_duration_clamped_to_zero(self, world_model):
        world_model.set_guest_mode(True, duration_hours=-3)
        assert world_model.is_guest_mode is False
