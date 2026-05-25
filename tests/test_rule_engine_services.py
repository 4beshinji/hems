"""
Regression tests for RuleEngine service/device-health rules.
"""

from rule_engine import RuleEngine


def _engine_with_devices(devices: list[dict]) -> RuleEngine:
    engine = RuleEngine()
    engine._cooldowns = {}
    engine._device_cache = devices
    return engine


def test_low_battery_device_creates_maintenance_task():
    engine = _engine_with_devices(
        [
            {
                "device_id": "zigbee.remote",
                "display_name": "Remote",
                "battery_pct": 10,
                "zone": "living",
            }
        ]
    )

    actions = engine._evaluate_device_health_rules(now=2_000_000.0)

    assert len(actions) == 1
    assert actions[0]["tool"] == "create_task"
    assert actions[0]["args"]["title"] == "電池切れ間近: Remote"
    assert actions[0]["args"]["zone"] == "living"


def test_low_zigbee_lqi_creates_maintenance_task():
    engine = _engine_with_devices(
        [
            {
                "device_id": "zigbee.sensor",
                "display_name": "Sensor",
                "vendor": "zigbee",
                "link_quality": 49,
                "zone": "office",
            }
        ]
    )

    actions = engine._evaluate_device_health_rules(now=2_000_000.0)

    assert len(actions) == 1
    assert actions[0]["args"]["title"] == "信号弱: Sensor"
    assert "LQI=49" in actions[0]["args"]["description"]


def test_low_non_zigbee_lqi_is_ignored():
    engine = _engine_with_devices(
        [
            {
                "device_id": "tapo.plug",
                "display_name": "Plug",
                "vendor": "tapo",
                "link_quality": 1,
            }
        ]
    )

    assert engine._evaluate_device_health_rules(now=2_000_000.0) == []


def test_stale_device_creates_maintenance_task():
    engine = _engine_with_devices(
        [
            {
                "device_id": "zigbee.motion",
                "display_name": "Motion",
                "last_seen": 1_000_000.0,
                "zone": "entry",
            }
        ]
    )

    actions = engine._evaluate_device_health_rules(now=2_000_000.0)

    assert len(actions) == 1
    assert actions[0]["args"]["title"] == "反応なし: Motion"
    assert actions[0]["args"]["zone"] == "entry"


def test_disabled_devices_are_ignored():
    engine = _engine_with_devices(
        [
            {
                "device_id": "zigbee.disabled",
                "display_name": "Disabled",
                "is_enabled": False,
                "battery_pct": 1,
                "vendor": "zigbee",
                "link_quality": 1,
                "last_seen": "2026-01-01T00:00:00Z",
            }
        ]
    )

    assert engine._evaluate_device_health_rules(now=1_767_228_800.0) == []


def test_device_health_cooldowns_are_per_device():
    engine = _engine_with_devices(
        [
            {"device_id": "zigbee.one", "display_name": "One", "battery_pct": 5},
            {"device_id": "zigbee.two", "display_name": "Two", "battery_pct": 5},
        ]
    )

    first = engine._evaluate_device_health_rules(now=2_000_000.0)
    second = engine._evaluate_device_health_rules(now=2_000_001.0)

    assert {action["args"]["title"] for action in first} == {
        "電池切れ間近: One",
        "電池切れ間近: Two",
    }
    assert second == []
    assert "dev_battery_zigbee.one" in engine._cooldowns
    assert "dev_battery_zigbee.two" in engine._cooldowns
