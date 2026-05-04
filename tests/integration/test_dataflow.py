"""
Backend HTTP data-flow integration tests using FastAPI ASGI TestClient.

Spins up the backend app against an in-memory SQLite DB — no live services
required, but the in-process app boot is heavier than a typical unit test, so
this file is gated behind the `integration` marker (excluded by default in
`make test` / CI; run via `pytest -m integration`).

Coverage:
  - Snapshot POST → GET round-trip for zones / pc / biometric / home
  - Snapshot overwrite semantics
  - Task CRUD lifecycle (create / accept / complete / dedup / errors)
  - Stats endpoint reflects task changes
  - Voice events
  - Time-series ingest + query
  - User CRUD
  - HA control 503 + climate validation
  - End-to-end Brain cycle simulation
"""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# conftest.py adds services/backend to sys.path
from database import Base, get_db
from main import app

pytestmark = pytest.mark.integration

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # In-memory snapshot stores must be cleared between tests; biometric is DB-backed.
    from routers import gas, home, knowledge, pc, perception, services, zones

    zones._zone_store.clear()
    pc._pc_store.clear()
    services._services_store.clear()
    knowledge._knowledge_store.clear()
    gas._gas_store.clear()
    perception._perception_store.clear()
    home._home_store.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Health ──────────────────────────────────────────────────────────────────


async def test_root_endpoint(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "HEMS Backend"
    assert data["status"] == "running"


# ── Snapshot data flow ──────────────────────────────────────────────────────


async def test_zone_snapshot_flow(client):
    r = await client.get("/zones/")
    assert r.status_code == 200
    assert r.json() == []

    snapshot = {
        "zones": [
            {
                "zone_id": "living_room",
                "environment": {"temperature": 24.5, "humidity": 55.0, "co2": 600.0},
                "occupancy": {"count": 1},
            },
            {
                "zone_id": "bedroom",
                "environment": {"temperature": 22.0, "humidity": 50.0, "co2": 450.0},
                "occupancy": {"count": 0},
            },
        ]
    }
    r = await client.post("/zones/snapshot", json=snapshot)
    assert r.status_code == 200
    assert r.json()["updated"] == 2

    r = await client.get("/zones/")
    zones = r.json()
    assert {z["zone_id"] for z in zones} == {"living_room", "bedroom"}

    living = next(z for z in zones if z["zone_id"] == "living_room")
    assert living["environment"]["temperature"] == 24.5
    assert living["environment"]["co2"] == 600.0
    assert living["occupancy"]["count"] == 1


async def test_pc_snapshot_flow(client):
    r = await client.get("/pc/")
    assert r.json()["status"] == "no_data"

    r = await client.post("/pc/snapshot", json={"cpu": 45.2, "memory": 68.5, "gpu": 30.0, "disk": 52.1})
    assert r.status_code == 200

    data = (await client.get("/pc/")).json()
    assert data["cpu"] == 45.2
    assert data["memory"] == 68.5


async def test_biometric_snapshot_flow(client):
    r = await client.get("/biometric/")
    assert r.json()["status"] == "no_data"

    r = await client.post("/biometric/snapshot", json={"heart_rate": 72, "spo2": 98, "stress": 35, "fatigue": 0.3})
    assert r.status_code == 200

    data = (await client.get("/biometric/")).json()
    assert data["heart_rate"] == 72
    assert data["spo2"] == 98


async def test_home_snapshot_flow(client):
    r = await client.get("/home/")
    assert r.json()["status"] == "no_data"

    home_data = {
        "devices": [
            {"entity_id": "light.living_room", "state": "on", "brightness": 200},
            {"entity_id": "climate.bedroom", "state": "cool", "temperature": 25},
        ]
    }
    r = await client.post("/home/snapshot", json=home_data)
    assert r.status_code == 200

    data = (await client.get("/home/")).json()
    assert len(data["devices"]) == 2


async def test_snapshot_overwrite(client):
    await client.post("/pc/snapshot", json={"cpu": 10, "extra_field": "old"})
    await client.post("/pc/snapshot", json={"cpu": 99})

    data = (await client.get("/pc/")).json()
    assert data["cpu"] == 99
    assert "extra_field" not in data


# ── Task CRUD ───────────────────────────────────────────────────────────────


async def test_task_create_and_list(client):
    r = await client.post(
        "/tasks/",
        json={
            "title": "Fix air conditioner",
            "description": "Temperature too high",
            "zone": "living_room",
            "urgency": 3,
            "task_type": ["hvac", "maintenance"],
        },
    )
    assert r.status_code == 200
    created = r.json()
    assert created["title"] == "Fix air conditioner"
    assert created["is_completed"] is False
    task_id = created["id"]

    tasks = (await client.get("/tasks/")).json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id


async def test_task_accept_and_complete(client):
    r = await client.post("/users/", json={"username": "tester", "display_name": "Tester"})
    assert r.status_code == 201
    user_id = r.json()["id"]

    r = await client.post("/tasks/", json={"title": "Refill water"})
    task_id = r.json()["id"]

    r = await client.put(f"/tasks/{task_id}/accept", json={"user_id": user_id})
    assert r.status_code == 200
    assert r.json()["assigned_to"] == user_id
    assert r.json()["accepted_at"] is not None

    r = await client.put(
        f"/tasks/{task_id}/complete",
        json={"report_status": "done", "completion_note": "Filled up"},
    )
    assert r.status_code == 200
    completed = r.json()
    assert completed["is_completed"] is True
    assert completed["report_status"] == "done"


async def test_task_duplicate_detection_stage1(client):
    task = {"title": "Open window", "location": "living_room"}
    id1 = (await client.post("/tasks/", json=task)).json()["id"]
    id2 = (await client.post("/tasks/", json=task)).json()["id"]
    assert id1 == id2
    assert len((await client.get("/tasks/")).json()) == 1


async def test_task_duplicate_detection_stage2(client):
    """Same zone + overlapping task_type → updates instead of duplicate."""
    id1 = (
        await client.post(
            "/tasks/",
            json={
                "title": "Lower temperature",
                "zone": "bedroom",
                "task_type": ["hvac", "comfort"],
            },
        )
    ).json()["id"]

    id2 = (
        await client.post(
            "/tasks/",
            json={
                "title": "Fix AC",
                "zone": "bedroom",
                "task_type": ["hvac", "repair"],
            },
        )
    ).json()["id"]

    assert id1 == id2
    assert len((await client.get("/tasks/")).json()) == 1


async def test_task_404_on_missing(client):
    assert (await client.put("/tasks/9999/accept", json={"user_id": 1})).status_code == 404
    assert (await client.put("/tasks/9999/complete", json={})).status_code == 404


async def test_task_cannot_accept_completed(client):
    task_id = (await client.post("/tasks/", json={"title": "Done task"})).json()["id"]
    await client.put(f"/tasks/{task_id}/complete", json={})
    r = await client.put(f"/tasks/{task_id}/accept", json={"user_id": 1})
    assert r.status_code == 400


# ── Stats ───────────────────────────────────────────────────────────────────


async def test_stats_reflect_task_changes(client):
    assert (await client.get("/tasks/stats")).json()["tasks_created"] == 0

    await client.post("/tasks/", json={"title": "Task A"})
    task_b_id = (await client.post("/tasks/", json={"title": "Task B"})).json()["id"]

    stats = (await client.get("/tasks/stats")).json()
    assert stats["tasks_created"] == 2
    assert stats["tasks_active"] == 2

    await client.put(f"/tasks/{task_b_id}/complete", json={})

    stats = (await client.get("/tasks/stats")).json()
    assert stats["tasks_completed"] == 1
    assert stats["tasks_active"] == 1


# ── Voice events ────────────────────────────────────────────────────────────


async def test_voice_event_create_and_recent(client):
    r = await client.post(
        "/voice-events/",
        json={
            "message": "Temperature is high!",
            "audio_url": "/audio/alert_001.wav",
            "zone": "living_room",
            "tone": "urgent",
        },
    )
    assert r.status_code == 200
    created = r.json()
    assert created["message"] == "Temperature is high!"
    assert created["tone"] == "urgent"

    events = (await client.get("/voice-events/recent")).json()
    assert len(events) >= 1
    assert events[0]["message"] == "Temperature is high!"


# ── Time series ─────────────────────────────────────────────────────────────


async def test_timeseries_ingest_and_query(client):
    now = datetime.now(UTC).isoformat()
    ingest = {
        "points": [
            {"metric": "temperature", "value": 25.5, "zone": "living_room", "recorded_at": now},
            {"metric": "temperature", "value": 26.0, "zone": "living_room", "recorded_at": now},
            {"metric": "co2", "value": 800.0, "zone": "living_room", "recorded_at": now},
        ]
    }
    r = await client.post("/timeseries/ingest", json=ingest)
    assert r.status_code == 200
    assert r.json()["ingested"] == 3

    points = (await client.get("/timeseries/", params={"metric": "temperature", "hours": 1})).json()
    assert len(points) == 2
    assert points[0]["value"] == 25.5
    assert points[0]["zone"] == "living_room"

    points = (await client.get("/timeseries/", params={"metric": "co2", "zone": "living_room", "hours": 1})).json()
    assert len(points) == 1
    assert points[0]["value"] == 800.0

    metrics = (await client.get("/timeseries/metrics")).json()
    assert "temperature" in metrics
    assert "co2" in metrics


# ── User CRUD ───────────────────────────────────────────────────────────────


async def test_user_crud(client):
    r = await client.post("/users/", json={"username": "alice", "display_name": "Alice"})
    assert r.status_code == 201
    user_id = r.json()["id"]
    assert r.json()["username"] == "alice"

    r = await client.post("/users/", json={"username": "alice"})
    assert r.status_code == 409

    assert len((await client.get("/users/")).json()) == 1
    assert (await client.get(f"/users/{user_id}")).json()["username"] == "alice"


# ── HA control validation ───────────────────────────────────────────────────


async def test_home_control_without_bridge(client):
    r = await client.post("/home/light/control", json={"entity_id": "light.test", "on": True})
    assert r.status_code == 503

    r = await client.post(
        "/home/climate/control",
        json={"entity_id": "climate.test", "temperature": 25},
    )
    assert r.status_code == 503


async def test_home_climate_validation(client):
    r = await client.post("/home/climate/control", json={"entity_id": "climate.test", "temperature": 10})
    assert r.status_code == 422

    r = await client.post("/home/climate/control", json={"entity_id": "climate.test", "temperature": 35})
    assert r.status_code == 422


# ── Full Brain → Dashboard simulation ───────────────────────────────────────


async def test_full_brain_cycle_simulation(client):
    """Simulate one Brain cognitive cycle: push all snapshots → verify frontend reads."""
    await client.post(
        "/zones/snapshot",
        json={
            "zones": [
                {
                    "zone_id": "main",
                    "environment": {"temperature": 28.0, "humidity": 60.0, "co2": 1200.0},
                    "occupancy": {"count": 1},
                }
            ]
        },
    )
    await client.post("/pc/snapshot", json={"cpu": 55, "memory": 70, "gpu": 20})
    await client.post("/biometric/snapshot", json={"heart_rate": 80, "stress": 40})
    await client.post("/home/snapshot", json={"devices": [{"entity_id": "light.desk", "state": "on"}]})

    r = await client.post(
        "/tasks/",
        json={
            "title": "Ventilate room",
            "description": "CO2 level above 1000ppm",
            "zone": "main",
            "urgency": 3,
            "task_type": ["ventilation"],
        },
    )
    task_id = r.json()["id"]

    await client.post(
        "/voice-events/",
        json={
            "message": "CO2レベルが高いです。換気してください。",
            "audio_url": "/audio/co2_alert.wav",
            "zone": "main",
            "tone": "warning",
        },
    )

    now = datetime.now(UTC).isoformat()
    await client.post(
        "/timeseries/ingest",
        json={
            "points": [
                {"metric": "temperature", "value": 28.0, "zone": "main", "recorded_at": now},
                {"metric": "co2", "value": 1200.0, "zone": "main", "recorded_at": now},
            ]
        },
    )

    zones = (await client.get("/zones/")).json()
    assert len(zones) == 1
    assert zones[0]["environment"]["co2"] == 1200.0

    assert (await client.get("/pc/")).json()["cpu"] == 55
    assert (await client.get("/biometric/")).json()["heart_rate"] == 80
    assert (await client.get("/home/")).json()["devices"][0]["entity_id"] == "light.desk"

    tasks = (await client.get("/tasks/")).json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Ventilate room"

    events = (await client.get("/voice-events/recent")).json()
    assert "CO2" in events[0]["message"]

    assert len((await client.get("/timeseries/", params={"metric": "co2", "hours": 1})).json()) == 1

    stats = (await client.get("/tasks/stats")).json()
    assert stats["tasks_created"] == 1
    assert stats["tasks_active"] == 1

    r = await client.put(
        f"/tasks/{task_id}/complete",
        json={
            "report_status": "done",
            "completion_note": "Opened window, CO2 dropping",
        },
    )
    assert r.json()["is_completed"] is True

    assert (await client.get("/tasks/stats")).json()["tasks_completed"] == 1
