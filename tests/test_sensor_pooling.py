"""
Tests for sensor pooling: channel classification, EventCounter,
StateTracker, TrendDetector, and WorldModel integration.
"""

import time

from world_model.sensor_fusion import (
    ChannelType,
    EventCounter,
    StateTracker,
    TrendDetector,
    classify_channel,
)


# ── Channel Classification ──────────────────────────────────────────


class TestChannelClassification:
    def test_analog_channels(self):
        assert classify_channel("temperature") == ChannelType.ANALOG
        assert classify_channel("humidity") == ChannelType.ANALOG
        assert classify_channel("co2") == ChannelType.ANALOG
        assert classify_channel("illuminance") == ChannelType.ANALOG
        assert classify_channel("light") == ChannelType.ANALOG
        assert classify_channel("voc") == ChannelType.ANALOG
        assert classify_channel("pm25") == ChannelType.ANALOG

    def test_event_channels(self):
        assert classify_channel("motion") == ChannelType.EVENT
        assert classify_channel("motion_count") == ChannelType.EVENT
        assert classify_channel("vibration") == ChannelType.EVENT

    def test_state_channels(self):
        assert classify_channel("door") == ChannelType.STATE
        assert classify_channel("presence") == ChannelType.STATE
        assert classify_channel("contact") == ChannelType.STATE
        assert classify_channel("occupancy") == ChannelType.STATE

    def test_unknown_is_passthrough(self):
        assert classify_channel("linkquality") == ChannelType.PASSTHROUGH
        assert classify_channel("battery") == ChannelType.PASSTHROUGH
        assert classify_channel("unknown_sensor") == ChannelType.PASSTHROUGH


# ── EventCounter ────────────────────────────────────────────────────


class TestEventCounter:
    def test_single_event(self):
        ec = EventCounter()
        now = time.time()
        ec.record_event("room:motion", now)
        assert ec.get_count("room:motion") == 1

    def test_multiple_events(self):
        ec = EventCounter()
        now = time.time()
        for i in range(5):
            ec.record_event("room:motion", now + i)
        assert ec.get_count("room:motion") == 5

    def test_window_expiry(self):
        ec = EventCounter()
        old = time.time() - 400  # Beyond 300s window
        ec.record_event("room:motion", old)
        assert ec.get_count("room:motion") == 0

    def test_mixed_old_and_new(self):
        ec = EventCounter()
        now = time.time()
        ec.record_event("room:motion", now - 400)  # expired
        ec.record_event("room:motion", now - 100)  # in window
        ec.record_event("room:motion", now)  # in window
        # Trim only happens on record, so manually check count
        assert ec.get_count("room:motion") == 2

    def test_record_count(self):
        ec = EventCounter()
        now = time.time()
        ec.record_count("room:motion_count", 3, now)
        assert ec.get_count("room:motion_count") == 3

    def test_frequency_per_min(self):
        ec = EventCounter()
        now = time.time()
        for i in range(10):
            ec.record_event("room:motion", now + i)
        assert ec.get_frequency_per_min("room:motion") == 10 / 5.0

    def test_nonexistent_key(self):
        ec = EventCounter()
        assert ec.get_count("nonexistent") == 0
        assert ec.get_frequency_per_min("nonexistent") == 0.0


# ── StateTracker ────────────────────────────────────────────────────


class TestStateTracker:
    def test_initial_state(self):
        st = StateTracker()
        now = time.time()
        changed = st.update("room:dev:door", True, now)
        assert changed is True
        state = st.get_state("room:dev:door")
        assert state["state"] is True
        assert state["changes_1h"] == 0

    def test_state_transition(self):
        st = StateTracker()
        now = time.time()
        st.update("room:dev:door", True, now)
        changed = st.update("room:dev:door", False, now + 10)
        assert changed is True
        state = st.get_state("room:dev:door")
        assert state["state"] is False
        assert state["changes_1h"] == 1

    def test_no_change(self):
        st = StateTracker()
        now = time.time()
        st.update("room:dev:door", True, now)
        changed = st.update("room:dev:door", True, now + 10)
        assert changed is False

    def test_duration(self):
        st = StateTracker()
        now = time.time() - 60  # 60 seconds ago
        st.update("room:dev:door", True, now)
        state = st.get_state("room:dev:door")
        assert state["duration_sec"] >= 59

    def test_change_count_1h(self):
        st = StateTracker()
        now = time.time()
        st.update("k:d:door", True, now)
        for i in range(1, 6):
            st.update("k:d:door", i % 2 == 0, now + i)
        state = st.get_state("k:d:door")
        assert state["changes_1h"] == 5

    def test_old_changes_trimmed(self):
        st = StateTracker()
        old = time.time() - 4000  # Beyond 1h
        st.update("k:d:door", True, old)
        st.update("k:d:door", False, old + 1)
        # Now make a recent change to trigger trim
        now = time.time()
        st.update("k:d:door", True, now)
        state = st.get_state("k:d:door")
        # The old change should be trimmed
        assert state["changes_1h"] == 1  # only the recent one

    def test_nonexistent_key(self):
        st = StateTracker()
        assert st.get_state("nonexistent") is None


# ── TrendDetector ───────────────────────────────────────────────────


class TestTrendDetector:
    def test_stable_few_readings(self):
        td = TrendDetector()
        now = time.time()
        td.record("room:temp", 22.0, now)
        assert td.get_trend("room:temp", 22.0, "temperature") == "stable"

    def test_rising(self):
        td = TrendDetector()
        now = time.time()
        td.record("room:temp", 22.0, now - 310)  # old enough
        td.record("room:temp", 23.0, now)
        assert td.get_trend("room:temp", 23.0, "temperature") == "rising"

    def test_falling(self):
        td = TrendDetector()
        now = time.time()
        td.record("room:temp", 23.0, now - 310)
        td.record("room:temp", 22.0, now)
        assert td.get_trend("room:temp", 22.0, "temperature") == "falling"

    def test_stable_within_threshold(self):
        td = TrendDetector()
        now = time.time()
        td.record("room:temp", 22.0, now - 310)
        td.record("room:temp", 22.3, now)
        assert td.get_trend("room:temp", 22.3, "temperature") == "stable"

    def test_history_trimmed(self):
        td = TrendDetector()
        now = time.time()
        # Records older than 600s should be trimmed
        td.record("room:temp", 20.0, now - 700)
        td.record("room:temp", 22.0, now)
        # Only the recent record remains
        assert len(td._history["room:temp"]) == 1


# ── WorldModel Integration ──────────────────────────────────────────


class TestWorldModelEventChannel:
    def test_zigbee_pir_occupancy(self, world_model):
        """Zigbee PIR occupancy=true increments motion count."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/pir_entrance",
            {"occupancy": True, "zone": "entrance"},
        )
        zone = world_model.zones["entrance"]
        assert zone.occupancy.motion_event_count_5min >= 1

    def test_zigbee_motion_count(self, world_model):
        """Multiple occupancy events accumulate."""
        for _ in range(3):
            world_model.update_from_mqtt(
                "zigbee2mqtt/pir_living",
                {"occupancy": True, "zone": "living_room"},
            )
        zone = world_model.zones["living_room"]
        assert zone.occupancy.motion_event_count_5min == 3
        assert zone.occupancy.motion_frequency_per_min == 3 / 5.0

    def test_zigbee_analog_still_works(self, world_model):
        """Analog channels still processed correctly."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/sensor_living",
            {"temperature": 22.5, "humidity": 45.0, "zone": "living_room"},
        )
        zone = world_model.zones["living_room"]
        assert zone.environment.temperature is not None
        assert zone.environment.humidity is not None


class TestWorldModelStateChannel:
    def test_zigbee_contact_sensor(self, world_model):
        """Zigbee contact=false → door open."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/door_entrance",
            {"contact": False, "zone": "entrance"},
        )
        zone = world_model.zones["entrance"]
        dev_id = "zigbee.door_entrance"
        assert dev_id in zone.occupancy.door_states
        assert zone.occupancy.door_states[dev_id]["open"] is True

    def test_zigbee_contact_closed(self, world_model):
        """Zigbee contact=true → door closed."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/door_entrance",
            {"contact": True, "zone": "entrance"},
        )
        zone = world_model.zones["entrance"]
        dev_id = "zigbee.door_entrance"
        assert dev_id in zone.occupancy.door_states
        assert zone.occupancy.door_states[dev_id]["open"] is False

    def test_zigbee_presence_sensor(self, world_model):
        """Zigbee presence=true → presence_state=True."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/presence_living",
            {"presence": True, "zone": "living_room"},
        )
        zone = world_model.zones["living_room"]
        assert zone.occupancy.presence_state is True

    def test_zigbee_skip_keys(self, world_model):
        """Metadata keys like linkquality are skipped."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/sensor_test",
            {
                "temperature": 22.0,
                "linkquality": 120,
                "battery": 85,
                "voltage": 3100,
                "zone": "bedroom",
            },
        )
        zone = world_model.zones["bedroom"]
        assert zone.environment.temperature is not None
        # linkquality/battery should not create events or state


class TestWorldModelTrends:
    def test_trend_recorded(self, world_model):
        """Temperature updates record trend in EnvironmentData."""
        world_model.update_from_mqtt(
            "office/living_room/sensor/dev01/temperature",
            {"temperature": 22.0},
        )
        zone = world_model.zones["living_room"]
        assert "temperature" in zone.environment.trends

    def test_trend_in_llm_context(self, world_model):
        """Trend arrow appears in LLM context."""
        # Simulate rising temperature
        import time as _t

        now = _t.time()
        world_model._trend_detector.record("living_room/temperature", 22.0, now - 310)
        world_model.update_from_mqtt(
            "office/living_room/sensor/dev01/temperature",
            {"temperature": 23.5},
        )
        context = world_model.get_llm_context()
        assert "↑" in context


class TestWorldModelOfficeSensorRouting:
    def test_office_motion_event(self, world_model):
        """office/{zone}/sensor/{dev}/motion routes to EventCounter."""
        world_model.update_from_mqtt(
            "office/living_room/sensor/pir01/motion",
            {"motion": True},
        )
        zone = world_model.zones["living_room"]
        assert zone.occupancy.motion_event_count_5min >= 1

    def test_office_door_state(self, world_model):
        """office/{zone}/sensor/{dev}/door routes to StateTracker."""
        world_model.update_from_mqtt(
            "office/entrance/sensor/door01/door",
            {"door": True},
        )
        zone = world_model.zones["entrance"]
        assert "door01" in zone.occupancy.door_states


class TestLLMContextPooling:
    def test_motion_count_in_context(self, world_model):
        """Motion event count appears in LLM context."""
        for _ in range(5):
            world_model.update_from_mqtt(
                "zigbee2mqtt/pir_living",
                {"occupancy": True, "zone": "living_room"},
            )
        context = world_model.get_llm_context()
        assert "動体検知" in context
        assert "5回" in context

    def test_door_state_in_context(self, world_model):
        """Door state appears in LLM context."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/door_entrance",
            {"contact": False, "zone": "entrance"},
        )
        context = world_model.get_llm_context()
        assert "ドア" in context
        assert "開放中" in context

    def test_presence_in_context(self, world_model):
        """Presence state appears in LLM context."""
        world_model.update_from_mqtt(
            "zigbee2mqtt/presence_living",
            {"presence": True, "zone": "living_room"},
        )
        context = world_model.get_llm_context()
        assert "在室センサー" in context
        assert "在室検知中" in context
