"""
Tests for WorldModel tri-domain facade pattern and backward-compatible property accessors.
"""
import pytest

from world_model.data_classes import (
    PhysicalSpace, DigitalSpace, UserState,
    ZoneState, HomeDevicesState, LightState,
    PCState, ServicesState, GASState, KnowledgeState,
    BiometricState, HeartRateData, SleepData, ActivityData,
    StressData, FatigueData, SpO2Data,
    CPUData, MemoryData, GPUData, DiskData,
)


class TestTriDomainStructure:
    """Test that WorldModel exposes three domain facade objects."""

    def test_physical_domain_exists(self, world_model):
        assert hasattr(world_model, "physical")
        assert isinstance(world_model.physical, PhysicalSpace)

    def test_digital_domain_exists(self, world_model):
        assert hasattr(world_model, "digital")
        assert isinstance(world_model.digital, DigitalSpace)

    def test_user_domain_exists(self, world_model):
        assert hasattr(world_model, "user")
        assert isinstance(world_model.user, UserState)


class TestPhysicalSpaceFields:
    """Test PhysicalSpace facade has correct field types."""

    def test_zones_is_dict(self, world_model):
        assert isinstance(world_model.physical.zones, dict)

    def test_home_devices_is_home_devices_state(self, world_model):
        assert isinstance(world_model.physical.home_devices, HomeDevicesState)


class TestDigitalSpaceFields:
    """Test DigitalSpace facade has correct field types."""

    def test_pc_state_type(self, world_model):
        assert isinstance(world_model.digital.pc_state, PCState)

    def test_services_state_type(self, world_model):
        assert isinstance(world_model.digital.services_state, ServicesState)

    def test_gas_state_type(self, world_model):
        assert isinstance(world_model.digital.gas_state, GASState)

    def test_knowledge_state_type(self, world_model):
        assert isinstance(world_model.digital.knowledge_state, KnowledgeState)


class TestUserStateFields:
    """Test UserState facade has correct field types."""

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


class TestPropertyAccessorsReturnSameObject:
    """Property accessors must return the exact same object as the domain field."""

    def test_zones_is_physical_zones(self, world_model):
        assert world_model.zones is world_model.physical.zones

    def test_pc_state_is_digital_pc_state(self, world_model):
        assert world_model.pc_state is world_model.digital.pc_state

    def test_services_state_is_digital_services_state(self, world_model):
        assert world_model.services_state is world_model.digital.services_state

    def test_knowledge_state_is_digital_knowledge_state(self, world_model):
        assert world_model.knowledge_state is world_model.digital.knowledge_state

    def test_gas_state_is_digital_gas_state(self, world_model):
        assert world_model.gas_state is world_model.digital.gas_state

    def test_home_devices_is_physical_home_devices(self, world_model):
        assert world_model.home_devices is world_model.physical.home_devices

    def test_biometric_state_is_user_biometrics(self, world_model):
        assert world_model.biometric_state is world_model.user.biometrics


class TestPropertySetters:
    """Setting via property must update the domain object."""

    def test_set_zones(self, world_model):
        new_zones = {"living": ZoneState(zone_id="living")}
        world_model.zones = new_zones
        assert world_model.physical.zones is new_zones
        assert world_model.zones is new_zones

    def test_set_pc_state(self, world_model):
        new_pc = PCState(bridge_connected=True)
        world_model.pc_state = new_pc
        assert world_model.digital.pc_state is new_pc
        assert world_model.pc_state is new_pc

    def test_set_services_state(self, world_model):
        new_ss = ServicesState()
        world_model.services_state = new_ss
        assert world_model.digital.services_state is new_ss
        assert world_model.services_state is new_ss

    def test_set_knowledge_state(self, world_model):
        new_ks = KnowledgeState(total_notes=42)
        world_model.knowledge_state = new_ks
        assert world_model.digital.knowledge_state is new_ks
        assert world_model.knowledge_state is new_ks

    def test_set_gas_state(self, world_model):
        new_gs = GASState(bridge_connected=True)
        world_model.gas_state = new_gs
        assert world_model.digital.gas_state is new_gs
        assert world_model.gas_state is new_gs

    def test_set_home_devices(self, world_model):
        new_hd = HomeDevicesState(bridge_connected=True)
        world_model.home_devices = new_hd
        assert world_model.physical.home_devices is new_hd
        assert world_model.home_devices is new_hd

    def test_set_biometric_state(self, world_model):
        new_bio = BiometricState(provider="garmin")
        world_model.biometric_state = new_bio
        assert world_model.user.biometrics is new_bio
        assert world_model.biometric_state is new_bio


class TestMutationThroughProperty:
    """Mutating via property accessor must be visible through domain object and vice versa."""

    def test_add_zone_via_property_visible_in_domain(self, world_model):
        world_model.zones["kitchen"] = ZoneState(zone_id="kitchen")
        assert "kitchen" in world_model.physical.zones
        assert world_model.physical.zones["kitchen"].zone_id == "kitchen"

    def test_add_zone_via_domain_visible_in_property(self, world_model):
        world_model.physical.zones["bedroom"] = ZoneState(zone_id="bedroom")
        assert "bedroom" in world_model.zones
        assert world_model.zones["bedroom"].zone_id == "bedroom"

    def test_mutate_pc_state_via_property(self, world_model):
        world_model.pc_state.bridge_connected = True
        assert world_model.digital.pc_state.bridge_connected is True

    def test_mutate_pc_state_via_domain(self, world_model):
        world_model.digital.pc_state.cpu = CPUData(usage_percent=55.0, core_count=8)
        assert world_model.pc_state.cpu.usage_percent == 55.0
        assert world_model.pc_state.cpu.core_count == 8

    def test_mutate_services_state_via_property(self, world_model):
        from world_model.data_classes import ServiceStatusData
        world_model.services_state.services["test"] = ServiceStatusData(
            name="test", summary="ok",
        )
        assert "test" in world_model.digital.services_state.services

    def test_mutate_services_state_via_domain(self, world_model):
        from world_model.data_classes import ServiceStatusData
        world_model.digital.services_state.services["github"] = ServiceStatusData(
            name="github", unread_count=5,
        )
        assert world_model.services_state.services["github"].unread_count == 5

    def test_mutate_gas_state_via_property(self, world_model):
        world_model.gas_state.bridge_connected = True
        assert world_model.digital.gas_state.bridge_connected is True

    def test_mutate_gas_state_via_domain(self, world_model):
        from world_model.data_classes import CalendarEvent
        ev = CalendarEvent(id="ev1", title="Meeting")
        world_model.digital.gas_state.calendar_events.append(ev)
        assert len(world_model.gas_state.calendar_events) == 1
        assert world_model.gas_state.calendar_events[0].title == "Meeting"

    def test_mutate_knowledge_state_via_property(self, world_model):
        world_model.knowledge_state.total_notes = 100
        assert world_model.digital.knowledge_state.total_notes == 100

    def test_mutate_knowledge_state_via_domain(self, world_model):
        world_model.digital.knowledge_state.bridge_connected = True
        assert world_model.knowledge_state.bridge_connected is True

    def test_mutate_home_devices_via_property(self, world_model):
        world_model.home_devices.lights["light.test"] = LightState(
            entity_id="light.test", on=True, brightness=200,
        )
        assert "light.test" in world_model.physical.home_devices.lights
        assert world_model.physical.home_devices.lights["light.test"].on is True

    def test_mutate_home_devices_via_domain(self, world_model):
        world_model.physical.home_devices.bridge_connected = True
        assert world_model.home_devices.bridge_connected is True

    def test_mutate_biometric_state_via_property(self, world_model):
        world_model.biometric_state.heart_rate.bpm = 72
        assert world_model.user.biometrics.heart_rate.bpm == 72

    def test_mutate_biometric_state_via_domain(self, world_model):
        world_model.user.biometrics.stress.level = 45
        assert world_model.biometric_state.stress.level == 45


class TestMQTTUpdatesThroughDomains:
    """MQTT updates via WorldModel must be visible from both property and domain paths."""

    def test_zone_update_via_occupancy(self, world_model):
        """Camera/occupancy MQTT updates zone visible from both paths."""
        world_model.update_from_mqtt("office/main/camera/cam01/status", {
            "person_count": 2,
        })
        # Accessible via property
        assert "main" in world_model.zones
        assert world_model.zones["main"].occupancy.count == 2
        # Accessible via domain
        assert "main" in world_model.physical.zones
        assert world_model.physical.zones["main"].occupancy.count == 2

    def test_pc_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 60.0, "core_count": 12,
        })
        # Via property
        assert world_model.pc_state.cpu.usage_percent == 60.0
        # Via domain
        assert world_model.digital.pc_state.cpu.usage_percent == 60.0

    def test_home_device_mqtt_update(self, world_model):
        world_model.update_from_mqtt(
            "hems/home/living/light/light.living/state",
            {"on": True, "brightness": 180},
        )
        # Via property
        assert world_model.home_devices.lights["light.living"].on is True
        # Via domain
        assert world_model.physical.home_devices.lights["light.living"].brightness == 180

    def test_gas_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/gas/bridge/status", {
            "connected": True,
        })
        # Via property
        assert world_model.gas_state.bridge_connected is True
        # Via domain
        assert world_model.digital.gas_state.bridge_connected is True

    def test_biometric_mqtt_update(self, world_model):
        world_model.update_from_mqtt("hems/personal/biometrics/garmin/heart_rate", {
            "bpm": 75,
        })
        # Via property
        assert world_model.biometric_state.heart_rate.bpm == 75
        # Via domain
        assert world_model.user.biometrics.heart_rate.bpm == 75


class TestExistingFunctionalityPreserved:
    """Verify existing WorldModel methods still work after tri-domain refactor."""

    def test_get_zone(self, world_model):
        from world_model.data_classes import EnvironmentData
        world_model.zones["lab"] = ZoneState(
            zone_id="lab",
            environment=EnvironmentData(temperature=22.0),
        )
        zone = world_model.get_zone("lab")
        assert zone is not None
        assert zone.zone_id == "lab"
        assert zone.environment.temperature == 22.0

    def test_get_zone_returns_none_for_unknown(self, world_model):
        assert world_model.get_zone("nonexistent") is None

    def test_get_all_zones(self, world_model):
        world_model.zones["a"] = ZoneState(zone_id="a")
        world_model.zones["b"] = ZoneState(zone_id="b")
        all_zones = world_model.get_all_zones()
        assert len(all_zones) == 2
        assert "a" in all_zones
        assert "b" in all_zones

    def test_get_llm_context_empty(self, world_model):
        """Empty world model produces empty context."""
        assert world_model.get_llm_context() == ""

    def test_get_llm_context_tri_domain_headers(self, world_model):
        """Context includes tri-domain section headers when data present."""
        from world_model.data_classes import EnvironmentData
        # Physical: add a zone directly
        world_model.zones["main"] = ZoneState(
            zone_id="main",
            environment=EnvironmentData(temperature=24.0),
        )
        # Digital: add PC data via MQTT
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 30.0, "core_count": 4,
        })
        # User: add biometric data via MQTT
        world_model.update_from_mqtt("hems/personal/biometrics/watch/heart_rate", {
            "bpm": 68,
        })

        ctx = world_model.get_llm_context()
        assert "## 現実空間" in ctx
        assert "## 電子空間" in ctx
        assert "## ユーザー状態" in ctx
