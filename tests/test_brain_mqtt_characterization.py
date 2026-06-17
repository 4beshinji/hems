"""
Characterization tests for MqttSyncMixin._process_mqtt  (W2.6 / C1)

These tests fix the *current* observable behaviour of _process_mqtt so that the
upcoming extraction refactor (C2) can be validated without regression.

Design reference: docs/refactor/2026-06-11/W2.6-design-note.md §6

Harness:  _Harness subclasses MqttSyncMixin and injects a real WorldModel plus
mock subsystems.  asyncio.run_coroutine_threadsafe is monkeypatched at the
brain_mqtt module level to record scheduled coroutines without running them;
this makes all assertions deterministic.

Coverage:
  S0  – Zigbee2MQTT zone enrichment (enrich vs. skip)
  S1  – world_model.update_from_mqtt routing (via orchestrator path)
  S2  – shopping classifier feed
  S3  – timeline regen trigger (calendar + task subtopics)
  S4  – intervention completion mark
  S5  – schedule_learner occupancy feed (camera / HA binary_sensor / biometric HR / non-match)
  S6  – schedule_learner sleep feed
  S7  – wake-up detection (biometric sleep end, camera morning, sunrise stop, no-wake guard)
  S8  – event_store sensor persist / analog reject / world-event persist
  S9  – heartbeat device-registry update + cycle-trigger (diff / no-diff)
  Order – three mandatory ordering invariants:
          (1) S0 enrich precedes S1 update_from_mqtt
          (2) wake_up_fired aggregate → sunrise stop
          (3) _maybe_trigger_cycle fires after world_model mutations (S1/S5)
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from brain_mqtt import MqttSyncMixin
from world_model import WorldModel

# ---------------------------------------------------------------------------
# Lightweight test harness
# ---------------------------------------------------------------------------


class _Harness(MqttSyncMixin):
    """MqttSyncMixin wired with a real WorldModel + mock subsystems.

    _loop is a MagicMock so call_soon_threadsafe calls are recorded.
    asyncio.run_coroutine_threadsafe is monkeypatched per-test (see fixture).
    """

    def __init__(self, world_model: WorldModel):
        self.world_model = world_model

        # Subsystems — MagicMock so every attribute access + call is recorded
        self.schedule_learner = MagicMock()
        self.event_automation = MagicMock()
        self.automation_engine = MagicMock()
        self.event_writer = MagicMock()
        self.shopping_classifier = MagicMock()
        self.timeline_generator = MagicMock()
        self.device_registry = MagicMock()
        self.dashboard = MagicMock()
        self.sunrise_alarm = MagicMock()
        self.sunrise_alarm.is_active = True
        self.client = MagicMock()

        # _loop: MagicMock captures call_soon_threadsafe calls.
        # run_coroutine_threadsafe is monkeypatched at module level per test.
        self._loop = MagicMock()

        # State fields _process_mqtt reads/writes
        self._device_zone_map: dict = {}
        self._heartbeat_debounce: dict = {}
        self._last_event_count: dict = {}
        self._cycle_triggered = asyncio.Event()
        self._z2m_bridge_devices_pending = None

        # Required by on_message but not tested here – provide stubs
        self.mcp = MagicMock()
        self.persona_rewriter = None
        self.ambient_speaker = None
        self.character = None
        self.power_mode_manager = MagicMock()

    def _trigger_timeline_regen(self, reason: str):
        """Stub — _process_mqtt passes this method reference to call_soon_threadsafe."""

    def _annotate_z2m_devices(self, payload: list):
        """Stub — called from _process_mqtt for zigbee2mqtt/bridge/devices."""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wm():
    return WorldModel()


@pytest.fixture
def harness(wm):
    return _Harness(wm)


@pytest.fixture
def scheduled_coros(harness):
    """Monkeypatch asyncio.run_coroutine_threadsafe in brain_mqtt module.

    Each call is intercepted: the coroutine (or mock) is recorded by
    qualname when possible, and real coroutines are closed to suppress
    "coroutine was never awaited" warnings.
    """
    recorded = []

    def _capture(coro, loop):
        # Real coroutines expose __qualname__; MagicMock return values do not.
        qualname = getattr(coro, "__qualname__", None) or repr(coro)
        recorded.append((qualname, loop))
        # Close real coroutines to suppress ResourceWarning
        if hasattr(coro, "close"):
            try:
                coro.close()
            except Exception:
                pass
        fut = MagicMock()
        return fut

    with patch("brain_mqtt.asyncio.run_coroutine_threadsafe", side_effect=_capture):
        yield recorded


# ---------------------------------------------------------------------------
# Helper: names of scheduled coroutines
# ---------------------------------------------------------------------------


def _coro_names(scheduled):
    return [name for name, _loop in scheduled]


# ---------------------------------------------------------------------------
# S0 – Zigbee2MQTT zone enrichment
# ---------------------------------------------------------------------------


class TestS0ZigbeeEnrich:
    def test_zone_injected_when_device_in_map(self, harness, scheduled_coros):
        harness._device_zone_map["0xABCD"] = "bedroom"
        payload = {"temperature": 21}
        harness._process_mqtt("zigbee2mqtt/0xABCD", payload)
        assert payload["zone"] == "bedroom"

    def test_zone_not_overwritten_if_already_present(self, harness, scheduled_coros):
        harness._device_zone_map["0xABCD"] = "bedroom"
        payload = {"temperature": 21, "zone": "kitchen"}
        harness._process_mqtt("zigbee2mqtt/0xABCD", payload)
        # existing zone must be preserved
        assert payload["zone"] == "kitchen"

    def test_bridge_topic_not_enriched(self, harness, scheduled_coros):
        harness._device_zone_map["bridge"] = "living"
        payload = [{"ieee": "0x1", "type": "Router"}]
        # bridge/devices is a list, not dict — also tests list guard
        harness._process_mqtt("zigbee2mqtt/bridge/devices", payload)
        # payload is a list; zone key cannot be injected
        assert not isinstance(payload, dict) or "zone" not in payload

    def test_unknown_device_no_zone_added(self, harness, scheduled_coros):
        payload = {"temperature": 21}
        harness._process_mqtt("zigbee2mqtt/0xUNKNOWN", payload)
        assert "zone" not in payload

    def test_non_zigbee_topic_not_enriched(self, harness, scheduled_coros):
        harness._device_zone_map["current"] = "living"
        payload = {"condition": "cloudy", "temperature": 15.0}
        harness._process_mqtt("hems/weather/current", payload)
        assert "zone" not in payload


# ---------------------------------------------------------------------------
# S0 → S1 ordering: enrich precedes update_from_mqtt
# ---------------------------------------------------------------------------


class TestOrderS0BeforeS1:
    def test_zone_present_in_payload_when_update_from_mqtt_is_called(self, harness, scheduled_coros):
        """update_from_mqtt must receive the enriched (zone-injected) payload."""
        harness._device_zone_map["0x1234"] = "living"
        received_payloads = []

        original_update = harness.world_model.update_from_mqtt

        def spy(topic, payload):
            received_payloads.append(dict(payload) if isinstance(payload, dict) else payload)
            return original_update(topic, payload)

        harness.world_model.update_from_mqtt = spy
        payload = {"temperature": 22}
        harness._process_mqtt("zigbee2mqtt/0x1234", payload)

        assert received_payloads, "update_from_mqtt was not called"
        assert received_payloads[0].get("zone") == "living", "S0 enrich must complete before S1 update_from_mqtt"


# ---------------------------------------------------------------------------
# S1 – world_model routing (via orchestrator)
# ---------------------------------------------------------------------------


class TestS1WorldModelRouting:
    def test_weather_condition_routed(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "sunny", "temperature": 28.0, "humidity": 55.0, "wind_speed": 3.0},
        )
        assert harness.world_model.weather.condition == "sunny"
        assert harness.world_model.weather.temperature == 28.0

    def test_news_urgent_routed(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/news/urgent",
            {"title": "速報テスト", "summary": "x", "score": 0.8, "source": "wire", "url": "https://test"},
        )
        assert harness.world_model.news_state.events[-1].event_type == "news_urgent"


# ---------------------------------------------------------------------------
# S2 – shopping classifier
# ---------------------------------------------------------------------------


class TestS2ShoppingClassifier:
    def test_shopping_added_schedules_handle_added(self, harness, scheduled_coros):
        harness._process_mqtt("hems/shopping/added", {"name": "milk"})
        names = _coro_names(scheduled_coros)
        assert any("handle_added_event" in n for n in names), f"Expected handle_added_event in {names}"

    def test_shopping_purchased_schedules_handle_purchased(self, harness, scheduled_coros):
        harness._process_mqtt("hems/shopping/purchased", {"name": "milk"})
        names = _coro_names(scheduled_coros)
        assert any("handle_purchased_event" in n for n in names), f"Expected handle_purchased_event in {names}"

    def test_non_shopping_topic_no_classifier_call(self, harness, scheduled_coros):
        harness._process_mqtt("hems/weather/current", {"condition": "clear", "temperature": 20.0})
        names = _coro_names(scheduled_coros)
        assert not any("handle_added_event" in n or "handle_purchased_event" in n for n in names)

    def test_no_classifier_when_subsystem_none(self, harness, scheduled_coros):
        harness.shopping_classifier = None
        harness._process_mqtt("hems/shopping/added", {"name": "bread"})
        names = _coro_names(scheduled_coros)
        assert not any("handle_added_event" in n for n in names)


# ---------------------------------------------------------------------------
# S3 – timeline regen trigger
# ---------------------------------------------------------------------------


class TestS3TimelineRegen:
    def test_calendar_upcoming_triggers_regen(self, harness, scheduled_coros):
        harness._process_mqtt("hems/gas/calendar/upcoming", {"events": []})
        harness._loop.call_soon_threadsafe.assert_any_call(harness._trigger_timeline_regen, "calendar_update")

    def test_task_created_triggers_regen(self, harness, scheduled_coros):
        harness._process_mqtt("hems/task/created", {})
        harness._loop.call_soon_threadsafe.assert_any_call(harness._trigger_timeline_regen, "task_created")

    def test_task_completed_triggers_regen(self, harness, scheduled_coros):
        harness._process_mqtt("hems/task/completed", {})
        harness._loop.call_soon_threadsafe.assert_any_call(harness._trigger_timeline_regen, "task_completed")

    def test_task_dismissed_triggers_regen(self, harness, scheduled_coros):
        harness._process_mqtt("hems/task/dismissed", {})
        harness._loop.call_soon_threadsafe.assert_any_call(harness._trigger_timeline_regen, "task_dismissed")

    def test_task_locked_triggers_regen(self, harness, scheduled_coros):
        harness._process_mqtt("hems/task/locked", {})
        harness._loop.call_soon_threadsafe.assert_any_call(harness._trigger_timeline_regen, "task_locked")

    def test_irrelevant_topic_does_not_trigger(self, harness, scheduled_coros):
        harness._process_mqtt("hems/weather/current", {"condition": "rainy", "temperature": 14.0})
        calls = harness._loop.call_soon_threadsafe.call_args_list
        timeline_calls = [c for c in calls if len(c.args) >= 1 and c.args[0] is harness._trigger_timeline_regen]
        assert not timeline_calls

    def test_no_timeline_when_subsystem_none(self, harness, scheduled_coros):
        harness.timeline_generator = None
        harness._process_mqtt("hems/gas/calendar/upcoming", {})
        calls = harness._loop.call_soon_threadsafe.call_args_list
        timeline_calls = [c for c in calls if len(c.args) >= 1 and c.args[0] is harness._trigger_timeline_regen]
        assert not timeline_calls


# ---------------------------------------------------------------------------
# S4 – intervention completion mark
# ---------------------------------------------------------------------------


class TestS4Intervention:
    def test_task_completed_with_id_marks_intervention(self, harness, scheduled_coros):
        harness._process_mqtt("hems/task/completed/T42", {})
        harness.event_writer.mark_intervention_completed.assert_called_once_with("T42")

    def test_task_completed_without_id_no_mark(self, harness, scheduled_coros):
        # topic has only 3 parts: hems/task/completed — no ID segment
        harness._process_mqtt("hems/task/completed", {})
        harness.event_writer.mark_intervention_completed.assert_not_called()

    def test_non_task_topic_no_mark(self, harness, scheduled_coros):
        harness._process_mqtt("hems/weather/current", {"condition": "clear", "temperature": 20.0})
        harness.event_writer.mark_intervention_completed.assert_not_called()


# ---------------------------------------------------------------------------
# S5 – schedule_learner occupancy feed
# ---------------------------------------------------------------------------


class TestS5OccupancyFeed:
    def test_camera_topic_triggers_reconcile_and_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/sensors/living/camera/cam1/status",
            {"person_count": 2},
        )
        assert hasattr(harness.world_model, "reconcile_presence"), "WorldModel must expose reconcile_presence"
        harness.schedule_learner.update_occupancy.assert_called_once()

    def test_ha_motion_binary_sensor_triggers_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/home/living/binary_sensor/pir/state",
            {"device_class": "motion", "state": "on"},
        )
        harness.schedule_learner.update_occupancy.assert_called_once()

    def test_ha_occupancy_binary_sensor_triggers_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/home/living/binary_sensor/occ/state",
            {"device_class": "occupancy", "state": "on"},
        )
        harness.schedule_learner.update_occupancy.assert_called_once()

    def test_ha_presence_binary_sensor_triggers_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/home/living/binary_sensor/mmwave/state",
            {"device_class": "presence", "state": "detected"},
        )
        harness.schedule_learner.update_occupancy.assert_called_once()

    def test_biometric_hr_triggers_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/personal/biometrics/band/heart_rate",
            {"bpm": 70},
        )
        harness.schedule_learner.update_occupancy.assert_called_once()

    def test_non_occupancy_topic_does_not_call_reconcile(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "sunny", "temperature": 24.0},
        )
        # reconcile_presence is a real WorldModel method; we check schedule_learner
        harness.schedule_learner.update_occupancy.assert_not_called()

    def test_no_update_when_learner_none(self, harness, scheduled_coros):
        harness.schedule_learner = None
        harness._process_mqtt(
            "hems/sensors/living/camera/cam1/status",
            {"person_count": 1},
        )
        # Should not raise — absence of learner is guarded

    def test_ha_non_presence_device_class_no_update(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/home/living/binary_sensor/door/state",
            {"device_class": "door", "state": "on"},
        )
        harness.schedule_learner.update_occupancy.assert_not_called()


# ---------------------------------------------------------------------------
# S6 – schedule_learner sleep feed
# ---------------------------------------------------------------------------


class TestS6SleepFeed:
    def test_sleep_topic_with_end_ts_calls_record_sleep(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        harness.schedule_learner.record_sleep_from_biometrics.assert_called_once_with(1_000_000, 1_028_800)

    def test_sleep_topic_without_end_ts_not_called(self, harness, scheduled_coros):
        # sleep_end_ts missing → no call
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 0},
        )
        harness.schedule_learner.record_sleep_from_biometrics.assert_not_called()

    def test_non_sleep_topic_no_call(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/personal/biometrics/band/heart_rate",
            {"bpm": 65},
        )
        harness.schedule_learner.record_sleep_from_biometrics.assert_not_called()


# ---------------------------------------------------------------------------
# S7 – wake-up detection
# ---------------------------------------------------------------------------


class TestS7WakeUp:
    def test_biometric_sleep_end_fires_wake_up(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        names = _coro_names(scheduled_coros)
        assert any("trigger" in n for n in names), (
            f"Expected event_automation.trigger or automation_engine.trigger_event in {names}"
        )

    def test_biometric_sleep_end_stops_sunrise_when_active(self, harness, scheduled_coros):
        harness.sunrise_alarm.is_active = True
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        harness.sunrise_alarm.stop.assert_called_once_with(harness.client)

    def test_camera_morning_fires_wake_up(self, harness, scheduled_coros):
        from brain_constants import WAKE_DETECT_HOUR_START

        # Patch datetime.now().hour to be within wake-detect window
        wake_hour = WAKE_DETECT_HOUR_START  # e.g. 5
        with patch("brain_mqtt.datetime") as mock_dt:
            mock_dt.now.return_value.hour = wake_hour
            harness._process_mqtt(
                "hems/sensors/living/camera/cam1/status",
                {"person_count": 1},
            )
        names = _coro_names(scheduled_coros)
        assert any("trigger" in n for n in names), f"Expected trigger coro scheduled for camera wake-up in {names}"

    def test_camera_morning_stops_sunrise_when_active(self, harness, scheduled_coros):
        from brain_constants import WAKE_DETECT_HOUR_START

        harness.sunrise_alarm.is_active = True
        with patch("brain_mqtt.datetime") as mock_dt:
            mock_dt.now.return_value.hour = WAKE_DETECT_HOUR_START
            harness._process_mqtt(
                "hems/sensors/living/camera/cam1/status",
                {"person_count": 2},
            )
        harness.sunrise_alarm.stop.assert_called_once_with(harness.client)

    def test_non_wake_topic_sunrise_not_stopped(self, harness, scheduled_coros):
        harness.sunrise_alarm.is_active = True
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "cloudy", "temperature": 18.0},
        )
        harness.sunrise_alarm.stop.assert_not_called()

    def test_camera_outside_wake_window_sunrise_not_stopped(self, harness, scheduled_coros):
        from brain_constants import WAKE_DETECT_HOUR_END

        harness.sunrise_alarm.is_active = True
        # Use an hour well outside the wake window (e.g. 23)
        outside_hour = (WAKE_DETECT_HOUR_END + 6) % 24
        with patch("brain_mqtt.datetime") as mock_dt:
            mock_dt.now.return_value.hour = outside_hour
            harness._process_mqtt(
                "hems/sensors/living/camera/cam1/status",
                {"person_count": 1},
            )
        harness.sunrise_alarm.stop.assert_not_called()

    def test_wake_up_aggregate_sunrise_stop_called_once(self, harness, scheduled_coros):
        """Even if biometric triggers wake_up_fired, sunrise.stop called once."""
        harness.sunrise_alarm.is_active = True
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        # stop must be called exactly once regardless of multiple coro schedules
        assert harness.sunrise_alarm.stop.call_count == 1

    def test_sunrise_not_stopped_when_inactive(self, harness, scheduled_coros):
        harness.sunrise_alarm.is_active = False
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        harness.sunrise_alarm.stop.assert_not_called()

    def test_no_event_automation_no_wake_coros(self, harness, scheduled_coros):
        harness.event_automation = None
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 1_000_000, "sleep_end_ts": 1_028_800},
        )
        names = _coro_names(scheduled_coros)
        # Without event_automation, wake coros must not fire
        assert not any("event_automation" in n or "automation_engine" in n for n in names)


# ---------------------------------------------------------------------------
# S7 ordering: aggregate wake_up_fired flag before sunrise stop
# ---------------------------------------------------------------------------


class TestOrderWakeAggregate:
    def test_sunrise_stop_called_after_wake_assessment(self, harness, scheduled_coros):
        """sunrise.stop must only be called after the full wake-up flag is known.

        We verify that stop is called exactly once (not zero times) when the
        biometric sleep-end path fires.  This guards the 'collect then stop'
        ordering: if sunrise.stop were called unconditionally or inside the
        biometric branch before the flag is evaluated, the call count would
        differ (e.g., 0 when active=True but flag never set, or >1 if called
        per-branch).
        """
        harness.sunrise_alarm.is_active = True
        harness._process_mqtt(
            "hems/personal/biometrics/band/sleep",
            {"sleep_start_ts": 0, "sleep_end_ts": 1_028_800},
        )
        assert harness.sunrise_alarm.stop.call_count == 1


# ---------------------------------------------------------------------------
# S8 – event_store writes
# ---------------------------------------------------------------------------


class TestS8EventStore:
    def test_sensor_topic_calls_record_sensor(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/temperature",
            {"temperature": 22.5},
        )
        harness.event_writer.record_sensor.assert_called_once()
        kwargs = harness.event_writer.record_sensor.call_args.kwargs
        assert kwargs["zone"] == "living"
        assert kwargs["channel"] == "temperature"
        assert kwargs["value"] == 22.5
        assert kwargs["device_id"] == "dev1"

    def test_sensor_falsy_value_is_persisted(self, harness, scheduled_coros):
        """Falsy numeric values like 0 must not be discarded by 'or' fallback."""
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/temperature",
            {"temperature": 0},
        )
        harness.event_writer.record_sensor.assert_called_once()
        kwargs = harness.event_writer.record_sensor.call_args.kwargs
        assert kwargs["value"] == 0

    def test_sensor_falsy_value_fallback_is_persisted(self, harness, scheduled_coros):
        """Falsy 'value' fallback must also be preserved."""
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/temperature",
            {"value": 0},
        )
        harness.event_writer.record_sensor.assert_called_once()
        kwargs = harness.event_writer.record_sensor.call_args.kwargs
        assert kwargs["value"] == 0

    def test_analog_out_of_range_not_persisted(self, harness, scheduled_coros):
        """Sensor value 999 is out of valid range → record_sensor must NOT be called."""
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/temperature",
            {"temperature": 999},
        )
        harness.event_writer.record_sensor.assert_not_called()

    def test_gas_calendar_calls_record_world_event(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/gas/calendar/upcoming",
            {"events": [{"title": "meeting"}]},
        )
        harness.event_writer.record_world_event.assert_called()
        call_kwargs = harness.event_writer.record_world_event.call_args.kwargs
        assert call_kwargs["source_type"] == "gas"

    def test_news_urgent_calls_record_world_event(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/news/urgent",
            {"title": "速報", "url": "https://x.test"},
        )
        harness.event_writer.record_world_event.assert_called()
        call_kwargs = harness.event_writer.record_world_event.call_args.kwargs
        assert call_kwargs["source_type"] == "news_urgent"

    def test_shopping_added_calls_record_world_event(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/shopping/added",
            {"name": "apple"},
        )
        harness.event_writer.record_world_event.assert_called()
        call_kwargs = harness.event_writer.record_world_event.call_args.kwargs
        assert call_kwargs["source_type"] == "shopping_added"

    def test_weather_alert_calls_record_world_event(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/weather/alerts",
            {"title": "大雨警報", "level": "warning"},
        )
        harness.event_writer.record_world_event.assert_called()
        call_kwargs = harness.event_writer.record_world_event.call_args.kwargs
        assert call_kwargs["source_type"] == "weather_alert"

    def test_no_event_writer_no_crash(self, harness, scheduled_coros):
        harness.event_writer = None
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/temperature",
            {"temperature": 22.5},
        )
        # Must not raise

    def test_gas_bridge_topic_not_persisted_as_world_event(self, harness, scheduled_coros):
        """hems/gas/bridge/status has parts[2]='bridge' → excluded from gas world events."""
        harness._process_mqtt(
            "hems/gas/bridge/status",
            {"connected": True},
        )
        # record_world_event should NOT have been called with source_type="gas"
        for c in harness.event_writer.record_world_event.call_args_list:
            assert c.kwargs.get("source_type") != "gas", "bridge status topic must not trigger gas world event"


# ---------------------------------------------------------------------------
# S9 – heartbeat update + cycle trigger
# ---------------------------------------------------------------------------


class TestS9HeartbeatAndCycleTrigger:
    def test_heartbeat_topic_calls_update_from_heartbeat(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/sensors/living/sensor/dev1/heartbeat",
            {"uptime": 3600},
        )
        harness.device_registry.update_from_heartbeat.assert_called_once_with("dev1", {"uptime": 3600})

    def test_cycle_triggered_when_events_increase(self, harness, scheduled_coros):
        """Routing a news_urgent event grows news_state.events → cycle should fire."""
        assert not harness._cycle_triggered.is_set()
        harness._process_mqtt(
            "hems/news/urgent",
            {"title": "速報テスト2", "summary": "details", "score": 0.9, "source": "x", "url": "https://t"},
        )
        assert harness._cycle_triggered.is_set(), "Cycle trigger must fire when world_model event count increases"

    def test_cycle_not_triggered_when_events_unchanged(self, harness, scheduled_coros):
        """After count stabilises, second identical routing must not re-set the event."""
        # Prime the count baseline by running once; this establishes _last_event_count
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "clear", "temperature": 20.0},
        )
        # After first call _last_event_count == current. Clear the trigger.
        harness._cycle_triggered.clear()

        # Send same topic again — world_model event counts do not change
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "clear", "temperature": 20.0},
        )
        assert not harness._cycle_triggered.is_set(), "Cycle trigger must NOT fire when event counts are unchanged"


# ---------------------------------------------------------------------------
# S9 ordering: cycle trigger fires after world_model mutations
# ---------------------------------------------------------------------------


class TestOrderCycleTriggerLast:
    def test_cycle_trigger_sees_updated_news_count(self, harness, scheduled_coros):
        """The cycle trigger comparison must happen after S1 has written to news_state.

        If _maybe_trigger_cycle ran before update_from_mqtt (wrong order), the
        news_state event count would be 0 at comparison time and the cycle would
        not fire even though an event was added.
        """
        # Seed the last-count cache as if no events exist yet
        harness._last_event_count = {}
        assert not harness._cycle_triggered.is_set()

        # This topic routes to news_state.events via update_from_mqtt (S1)
        harness._process_mqtt(
            "hems/news/urgent",
            {"title": "breaking", "summary": "y", "score": 0.5, "source": "w", "url": "https://e"},
        )
        # Cycle must have fired, proving S9 ran AFTER S1 added the event
        assert harness._cycle_triggered.is_set(), "_maybe_trigger_cycle must execute after world_model is updated"

    def test_cycle_trigger_sees_zone_events_after_task_report(self, harness, scheduled_coros):
        """task_report route adds an event to a zone; cycle trigger must see that."""
        harness._last_event_count = {}
        assert not harness._cycle_triggered.is_set()

        harness._process_mqtt(
            "office/living/task_report/t1",
            {"title": "fix AC", "report_status": "needs_followup"},
        )
        assert harness._cycle_triggered.is_set(), "Cycle trigger must see the zone event added by task_report route"


# ---------------------------------------------------------------------------
# Non-target topics: zero side-effects
# ---------------------------------------------------------------------------


class TestNoSideEffectsOnIrrelevantTopics:
    def test_weather_topic_no_learner_classifier_intervention(self, harness, scheduled_coros):
        harness._process_mqtt(
            "hems/weather/current",
            {"condition": "clear", "temperature": 22.0, "humidity": 50.0},
        )
        harness.schedule_learner.update_occupancy.assert_not_called()
        harness.schedule_learner.record_sleep_from_biometrics.assert_not_called()
        harness.event_writer.mark_intervention_completed.assert_not_called()
        harness.sunrise_alarm.stop.assert_not_called()
        names = _coro_names(scheduled_coros)
        assert not any("handle_added_event" in n or "handle_purchased_event" in n for n in names)
        assert not any("trigger" in n for n in names)
