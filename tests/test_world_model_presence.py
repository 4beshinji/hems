"""
Direct regression tests for WorldModel presence reconciliation.
"""

import importlib

from world_model.data_classes import CPUData, HeartRateData, OccupancyData

wm_mod = importlib.import_module("world_model.world_model")


def test_reconcile_presence_uses_camera_first(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    zone = world_model._get_zone("office")
    zone.occupancy = OccupancyData(count=1, presence_state=True, motion_event_count_5min=2)

    summary = world_model.reconcile_presence()

    assert summary["office"]["occupied"] is True
    assert zone.occupancy.inference_sources == ["camera", "presence_sensor", "motion"]
    assert zone.occupancy.inference_source == "camera"


def test_reconcile_presence_uses_presence_sensor(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    zone = world_model._get_zone("living")
    zone.occupancy = OccupancyData(presence_state=True)

    summary = world_model.reconcile_presence()

    assert summary["living"]["occupied"] is True
    assert zone.occupancy.inference_sources == ["presence_sensor"]


def test_reconcile_presence_uses_recent_motion(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    zone = world_model._get_zone("kitchen")
    zone.occupancy = OccupancyData(last_motion_ts=900.0)

    summary = world_model.reconcile_presence()

    assert summary["kitchen"]["occupied"] is True
    assert zone.occupancy.inference_sources == ["motion"]


def test_reconcile_presence_creates_home_zone_from_fresh_pc(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    world_model.pc_state.cpu = CPUData(usage_percent=20.0, last_update=950.0)

    summary = world_model.reconcile_presence()

    assert "home" in world_model.zones
    assert summary["home"]["occupied"] is True
    assert world_model.zones["home"].occupancy.inference_sources == ["pc_activity"]


def test_reconcile_presence_creates_home_zone_from_fresh_biometric(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    world_model.biometric_state.heart_rate = HeartRateData(bpm=72, last_update=950.0)

    summary = world_model.reconcile_presence()

    assert "home" in world_model.zones
    assert summary["home"]["occupied"] is True
    assert world_model.zones["home"].occupancy.inference_sources == ["biometric"]


def test_is_anyone_home_reconciles_before_returning(world_model, monkeypatch):
    monkeypatch.setattr(wm_mod.time, "time", lambda: 1000.0)
    zone = world_model._get_zone("entry")
    zone.occupancy = OccupancyData(presence_state=True)

    assert world_model.is_anyone_home() is True
    assert zone.occupancy.inferred_occupied is True


def test_presence_sources_returns_unique_sources(world_model):
    world_model._get_zone("office").occupancy.inference_sources = ["camera", "motion"]
    world_model._get_zone("living").occupancy.inference_sources = ["motion", "biometric"]

    assert world_model.presence_sources() == ["camera", "motion", "biometric"]
