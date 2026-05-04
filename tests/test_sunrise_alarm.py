"""
Tests for SunriseAlarm — gradual brightness ramp via dispatcher / direct MQTT.
"""

import asyncio
import importlib
import json
import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sa_mod(monkeypatch):
    """Load sunrise_alarm with a configured device + tight test timings."""
    monkeypatch.setenv("SUNRISE_ALARM_DEVICE", "zigbee.0xTEST")
    monkeypatch.setenv("SUNRISE_ALARM_START_SEC", "60")
    monkeypatch.setenv("SUNRISE_ALARM_END_SEC", "30")
    monkeypatch.setenv("SUNRISE_ALARM_STEP_SEC", "1")
    monkeypatch.setenv("SUNRISE_ALARM_MIN_BRIGHTNESS", "10")
    monkeypatch.setenv("SUNRISE_ALARM_MAX_BRIGHTNESS", "50")
    import sunrise_alarm

    importlib.reload(sunrise_alarm)
    return sunrise_alarm


class _MqttInfoOK:
    rc = 0


class _MqttInfoFail:
    rc = 1


class StubMqtt:
    def __init__(self, fail_count: int = 0):
        self.sent: list[tuple[str, str]] = []
        self._fail_count = fail_count
        self._calls = 0

    def publish(self, topic, body):
        self._calls += 1
        self.sent.append((topic, body))
        if self._calls <= self._fail_count:
            return _MqttInfoFail()
        return _MqttInfoOK()


class StubDispatcher:
    def __init__(self, succeed: bool = True):
        self.calls: list[tuple] = []
        self._succeed = succeed

    async def dispatch(self, device_id, action, params):
        self.calls.append((device_id, action, params))
        if self._succeed:
            return {"success": True}
        return {"success": False, "error": "device not registered"}


class TestShouldStart:
    def test_no_device_returns_false(self, monkeypatch):
        monkeypatch.delenv("SUNRISE_ALARM_DEVICE", raising=False)
        import sunrise_alarm

        importlib.reload(sunrise_alarm)
        sa = sunrise_alarm.SunriseAlarm()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 600
        assert sa.should_start(sl) is False

    def test_within_window_true(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 30  # within 60s START_BEFORE
        assert sa.should_start(sl) is True

    def test_outside_window_false(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 9999
        assert sa.should_start(sl) is False

    def test_already_run_today_false(self, sa_mod):
        from datetime import datetime

        sa = sa_mod.SunriseAlarm()
        sa._last_run_date = datetime.now().strftime("%Y-%m-%d")
        sl = MagicMock()
        sl.get_wake_time.return_value = time.time() + 30
        assert sa.should_start(sl) is False


class TestRampOutputPath:
    def test_dispatcher_used_when_present(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        mqtt = StubMqtt()
        disp = StubDispatcher(succeed=True)

        async def run():
            sa.start(mqtt, time.time() + 35, dispatcher=disp)
            await asyncio.sleep(8)

        asyncio.run(run())
        assert len(disp.calls) >= 1
        assert mqtt.sent == []

    def test_falls_back_to_mqtt_on_dispatcher_failure(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        mqtt = StubMqtt()
        disp = StubDispatcher(succeed=False)

        async def run():
            sa.start(mqtt, time.time() + 35, dispatcher=disp)
            await asyncio.sleep(8)

        asyncio.run(run())
        assert len(disp.calls) >= 1
        assert len(mqtt.sent) >= 1
        # Verify Z2M topic format
        topic, body = mqtt.sent[0]
        assert topic == "zigbee2mqtt/0xTEST/set"
        payload = json.loads(body)
        assert payload["state"] == "ON"
        assert "brightness" in payload

    def test_direct_publish_retries_once_on_rc_failure(self, sa_mod):
        """First publish returns rc!=0, second succeeds → no error log."""
        sa = sa_mod.SunriseAlarm()
        mqtt = StubMqtt(fail_count=1)
        ok = sa._direct_publish(mqtt, {"state": "ON", "brightness": 10})
        assert ok is True
        assert len(mqtt.sent) == 2  # one failed + one retry

    def test_direct_publish_returns_false_after_two_failures(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        mqtt = StubMqtt(fail_count=99)
        ok = sa._direct_publish(mqtt, {"state": "ON"})
        assert ok is False
        assert len(mqtt.sent) == 2  # initial + 1 retry only


class TestStop:
    def test_stop_publishes_off_and_resets_state(self, sa_mod):
        sa = sa_mod.SunriseAlarm()
        sa._state = sa_mod.SunriseState.RAMPING
        mqtt = StubMqtt()
        sa.stop(mqtt)
        assert sa.state == sa_mod.SunriseState.IDLE
        # Last publish is the OFF command
        assert any(json.loads(body)["state"] == "OFF" for _, body in mqtt.sent)
