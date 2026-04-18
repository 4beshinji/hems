"""
Tests for backend timeseries router — SQLite-backed time series storage.
Requires sqlalchemy to be installed (pip install sqlalchemy aiosqlite).
"""

import pytest

try:
    import sqlalchemy  # noqa: F401

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with a file-backed SQLite database."""
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    db_file = tmp_path / "hems_timeseries_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    # Reimport database module to pick up test DB URL
    if "database" in sys.modules:
        del sys.modules["database"]
    if "models" in sys.modules:
        del sys.modules["models"]
    if "routers.timeseries" in sys.modules:
        del sys.modules["routers.timeseries"]

    from fastapi import FastAPI

    import database
    from routers.timeseries import router

    app = FastAPI()
    app.include_router(router)

    import asyncio

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create())
    loop.close()

    from fastapi.testclient import TestClient

    return TestClient(app)


class TestTimeSeriesIngest:
    def test_ingest_single_point(self, client):
        resp = client.post(
            "/timeseries/ingest", json={"points": [{"metric": "temperature", "value": 25.3, "zone": "living_room"}]}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ingested": 1}

    def test_ingest_batch(self, client):
        resp = client.post(
            "/timeseries/ingest",
            json={
                "points": [
                    {"metric": "temperature", "value": 25.3, "zone": "living_room"},
                    {"metric": "co2", "value": 800, "zone": "living_room"},
                    {"metric": "humidity", "value": 55.0, "zone": "living_room"},
                ]
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"ingested": 3}


class TestTimeSeriesQuery:
    def test_query_returns_ingested_data(self, client):
        client.post(
            "/timeseries/ingest",
            json={
                "points": [
                    {"metric": "temperature", "value": 25.3, "zone": "living_room"},
                    {"metric": "temperature", "value": 25.5, "zone": "living_room"},
                ]
            },
        )
        resp = client.get("/timeseries/", params={"metric": "temperature", "hours": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["value"] == 25.3
        assert data[1]["value"] == 25.5

    def test_query_filters_by_zone(self, client):
        client.post(
            "/timeseries/ingest",
            json={
                "points": [
                    {"metric": "temperature", "value": 25.0, "zone": "living_room"},
                    {"metric": "temperature", "value": 22.0, "zone": "bedroom"},
                ]
            },
        )
        resp = client.get(
            "/timeseries/",
            params={
                "metric": "temperature",
                "zone": "bedroom",
                "hours": 1,
            },
        )
        data = resp.json()
        assert len(data) == 1
        assert data[0]["value"] == 22.0

    def test_query_empty_result(self, client):
        resp = client.get("/timeseries/", params={"metric": "nonexistent", "hours": 1})
        assert resp.status_code == 200
        assert resp.json() == []


class TestTimeSeriesMetrics:
    def test_metrics_list(self, client):
        client.post(
            "/timeseries/ingest",
            json={
                "points": [
                    {"metric": "temperature", "value": 25.0},
                    {"metric": "co2", "value": 800},
                    {"metric": "heart_rate.bpm", "value": 72},
                ]
            },
        )
        resp = client.get("/timeseries/metrics")
        assert resp.status_code == 200
        metrics = resp.json()
        assert "temperature" in metrics
        assert "co2" in metrics
        assert "heart_rate.bpm" in metrics

    def test_metrics_empty(self, client):
        resp = client.get("/timeseries/metrics")
        assert resp.status_code == 200
        assert resp.json() == []
