"""Tests for the freshness gate + blind guard (Group C, ported from SOMS).

hems tracks freshness via ``EnvironmentState.last_update`` and
``EnvironmentState.channel_last_seen`` (SOMS used ZoneState.last_update +
environment.timestamps). The blind guard itself lives in main.py's cognitive
loop; here we cover the world-model primitives it relies on (is_blind, stale
display) plus the fusion hard age cap.
"""

import time

import pytest

from world_model.data_classes import ZoneState
from world_model.sensor_fusion import SensorFusion
from world_model.world_model import ENV_STALE_SEC, ZONE_BLIND_SEC, WorldModel


def _make_zone(wm, zone_id, *, temperature=None, co2=None, age_sec=0.0):
    """Insert a zone with an environment reading aged `age_sec` seconds."""
    now = time.time()
    zone = ZoneState(zone_id=zone_id)
    if temperature is not None:
        zone.environment.temperature = temperature
        zone.environment.channel_last_seen["temperature"] = now - age_sec
    if co2 is not None:
        zone.environment.co2 = co2
        zone.environment.channel_last_seen["co2"] = now - age_sec
    zone.environment.last_update = now - age_sec
    wm.zones[zone_id] = zone
    return zone


class TestStaleDisplay:
    def test_stale_zone_shows_age(self):
        wm = WorldModel()
        _make_zone(wm, "kitchen", temperature=24.0, age_sec=ENV_STALE_SEC + 120)
        context = wm.get_llm_context()
        assert "データ更新なし" in context
        assert "分前" in context

    def test_fresh_zone_no_stale_note(self):
        wm = WorldModel()
        _make_zone(wm, "kitchen", temperature=24.0, age_sec=5)
        context = wm.get_llm_context()
        assert "データ更新なし" not in context
        assert "古い" not in context

    def test_stale_value_gets_inline_age_note(self):
        wm = WorldModel()
        _make_zone(wm, "kitchen", temperature=24.0, age_sec=ENV_STALE_SEC + 60)
        context = wm.get_llm_context()
        # The temperature line itself is annotated as old, and the value is
        # still visible for situational awareness.
        assert "温度" in context
        assert "古い" in context


class TestIsBlind:
    def test_no_zones_is_blind(self):
        wm = WorldModel()
        assert wm.is_blind() is True

    def test_all_stale_is_blind(self):
        wm = WorldModel()
        _make_zone(wm, "kitchen", temperature=24.0, age_sec=ZONE_BLIND_SEC + 60)
        _make_zone(wm, "office", temperature=22.0, age_sec=ZONE_BLIND_SEC + 300)
        assert wm.is_blind() is True

    def test_one_fresh_zone_not_blind(self):
        wm = WorldModel()
        _make_zone(wm, "kitchen", temperature=24.0, age_sec=ZONE_BLIND_SEC + 60)
        _make_zone(wm, "office", temperature=22.0, age_sec=5)  # fresh
        assert wm.is_blind() is False

    def test_zone_with_no_update_counts_as_blind(self):
        wm = WorldModel()
        # last_update == 0 (never updated) must count toward blindness.
        wm.zones["ghost"] = ZoneState(zone_id="ghost")
        assert wm.is_blind() is True


class TestFusionMaxAge:
    def test_recent_reading_fused(self):
        f = SensorFusion()
        now = time.time()
        result = f.fuse_generic([("s1", 22.0, now - 10)], sensor_type="temperature")
        assert result == pytest.approx(22.0, abs=0.5)

    def test_all_stale_readings_return_none(self):
        f = SensorFusion()
        now = time.time()
        old = now - (SensorFusion.MAX_FUSION_AGE_SEC + 120)
        assert f.fuse_generic([("s1", 22.0, old)], sensor_type="temperature") is None

    def test_mixed_age_keeps_only_fresh(self):
        f = SensorFusion()
        now = time.time()
        old = now - (SensorFusion.MAX_FUSION_AGE_SEC + 120)
        result = f.fuse_generic(
            [("s1", 50.0, old), ("s2", 20.0, now - 5)],
            sensor_type="temperature",
        )
        # Stale 50.0 excluded — result should track the fresh 20.0 reading.
        assert result == pytest.approx(20.0, abs=1.0)
