"""
Tests for backend biometric router — in-memory store.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client for the backend app with a file-backed SQLite database."""
    import asyncio
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    db_file = tmp_path / "hems_biometric_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    # Reimport database module to pick up test DB URL
    for mod_name in ("database", "models", "routers.biometric"):
        sys.modules.pop(mod_name, None)

    from fastapi import FastAPI

    import database
    from routers.biometric import router

    app = FastAPI()
    app.include_router(router)

    async def _create_tables():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    asyncio.run(_create_tables())

    return TestClient(app)


class TestBiometricRouterGetStatus:
    def test_returns_no_data_initially(self, client):
        resp = client.get("/biometric/")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "no_data"

    def test_returns_data_after_snapshot(self, client):
        snapshot = {
            "heart_rate": 72,
            "steps": 8432,
            "provider": "fitbit",
        }
        resp = client.post("/biometric/snapshot", json=snapshot)
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        resp = client.get("/biometric/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["heart_rate"] == 72
        assert data["steps"] == 8432


class TestBiometricRouterSnapshot:
    def test_overwrites_previous_data(self, client):
        client.post("/biometric/snapshot", json={"heart_rate": 60})
        client.post("/biometric/snapshot", json={"heart_rate": 95})

        resp = client.get("/biometric/")
        data = resp.json()
        assert data["heart_rate"] == 95

    def test_empty_snapshot(self, client):
        client.post("/biometric/snapshot", json={})
        resp = client.get("/biometric/")
        data = resp.json()
        assert data.get("provider") == "unknown"
