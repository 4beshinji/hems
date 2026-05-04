"""Test biometric-bridge does not double-publish steps on /steps and /activity."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def bridge_main():
    bridge_src = str(Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src")
    if bridge_src not in sys.path:
        sys.path.insert(0, bridge_src)
    import importlib

    import main as bridge_main_module

    importlib.reload(bridge_main_module)
    bridge_main_module.processor._recent.clear()
    return bridge_main_module


def _make_reading(bridge_main):
    from data_processor import BiometricReading

    return BiometricReading(
        heart_rate=72,
        steps=5000,
        steps_goal=10000,
        active_minutes=30,
        calories=250,
        activity_level="moderate",
        provider="test",
    )


def test_steps_published_only_to_steps_topic(bridge_main):
    """When reading has steps, /activity payload should NOT include steps."""
    reading = _make_reading(bridge_main)

    published = []

    def fake_publish(topic, data, retain=True):
        published.append((topic, dict(data)))

    with patch.object(bridge_main, "_mqtt_publish", side_effect=fake_publish):
        bridge_main._publish_reading(reading)

    by_topic = {t.split("/")[-1]: payload for t, payload in published}

    assert "steps" in by_topic, "steps topic should be published"
    assert by_topic["steps"]["count"] == 5000
    assert by_topic["steps"]["daily_goal"] == 10000

    assert "activity" in by_topic, "activity topic should be published when level/calories/active_minutes set"
    assert "steps" not in by_topic["activity"], (
        "activity payload must NOT include steps (avoid double publish)"
    )
    assert by_topic["activity"]["calories"] == 250
    assert by_topic["activity"]["active_minutes"] == 30


def test_no_activity_publish_when_only_steps(bridge_main):
    """When reading has only steps and HR (no activity_level/calories/active_minutes), no /activity message."""
    from data_processor import BiometricReading

    reading = BiometricReading(heart_rate=72, steps=5000, provider="test")

    published = []

    def fake_publish(topic, data, retain=True):
        published.append((topic, dict(data)))

    with patch.object(bridge_main, "_mqtt_publish", side_effect=fake_publish):
        bridge_main._publish_reading(reading)

    topics = {t.split("/")[-1] for t, _ in published}
    assert "steps" in topics
    assert "activity" not in topics, "activity should not be published when no activity fields are set"
