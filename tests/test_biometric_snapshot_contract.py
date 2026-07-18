"""Fast biometric snapshot contract tests without a database fixture."""

from types import SimpleNamespace

import pytest

from dashboard_mappers import map_biometric_payload
from models import BiometricReading
from routers.biometric import update_biometric
from schemas import BiometricSnapshotIn


def _brain_payload() -> dict:
    bio = SimpleNamespace(
        bridge_connected=True,
        provider="healthconnect",
        last_update=1000.0,
        heart_rate=SimpleNamespace(bpm=81, zone="fat_burn", resting_bpm=59),
        spo2=SimpleNamespace(percent=97),
        sleep=SimpleNamespace(
            last_update=1000.0,
            stage="deep",
            duration_minutes=430,
            deep_minutes=95,
            rem_minutes=90,
            light_minutes=245,
            quality_score=84,
        ),
        activity=SimpleNamespace(
            last_update=1000.0,
            steps=8123,
            steps_goal=10000,
            calories=320,
            active_minutes=44,
            level="moderate",
        ),
        stress=SimpleNamespace(last_update=1000.0, level=35, category="normal"),
        fatigue=SimpleNamespace(last_update=1000.0, score=22, factors=["poor_sleep"]),
    )
    return map_biometric_payload(SimpleNamespace(biometric_state=bio))


def test_real_mapper_payload_validates_and_flattens():
    snapshot = BiometricSnapshotIn.model_validate(_brain_payload())

    assert snapshot.to_flat_columns() == {
        "provider": "healthconnect",
        "heart_rate": 81,
        "resting_heart_rate": 59,
        "spo2": 97,
        "steps": 8123,
        "calories": 320,
        "active_minutes": 44,
        "stress_level": 35,
        "fatigue_score": 22,
        "sleep_duration_minutes": 430,
        "sleep_quality_score": 84,
        "hrv_ms": None,
        "body_temperature": None,
        "respiratory_rate": None,
    }


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self):
        self.row = None
        self.add_calls = 0
        self.commit_calls = 0

    async def execute(self, _statement):
        return _FakeResult(self.row)

    def add(self, row):
        self.add_calls += 1
        self.row = row

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_route_updates_one_latest_row_across_100_cycles():
    session = _FakeSession()

    for index in range(100):
        snapshot = BiometricSnapshotIn(
            provider="healthconnect",
            heart_rate={"bpm": 40 + index},
        )
        assert await update_biometric(snapshot, session) == {"updated": True}

    assert session.add_calls == 1
    assert session.commit_calls == 100
    assert isinstance(session.row, BiometricReading)
    assert session.row.heart_rate == 139
    assert session.row.provider == "healthconnect"
