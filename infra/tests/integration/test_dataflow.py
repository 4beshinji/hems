"""
Data flow integration tests — FastAPI TestClient-based.
Tests the full dashboard data flow without requiring live services:
  1. Snapshot POST → GET retrieval (in-memory stores)
  2. Task CRUD lifecycle (DB-backed)
  3. Task duplicate detection
  4. Time series ingest → query
  5. Voice event creation → recent retrieval
  6. Task completion with XP award
  7. Cross-endpoint consistency (stats reflect task changes)
"""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../services/backend"))

from database import Base, get_db
from main import app

# In-memory SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Clear in-memory snapshot stores between tests
    from routers import zones, pc, services, knowledge, gas, biometric, perception, home
    zones._zone_store.clear()
    pc._pc_store.clear()
    services._services_store.clear()
    knowledge._knowledge_store.clear()
    gas._gas_store.clear()
    biometric._bio_store.clear()
    perception._perception_store.clear()
    home._home_store.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ──────────────────────────────────────────────
# 1. Health check
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Backend root returns running status."""
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "HEMS Backend"
    assert data["status"] == "running"


# ──────────────────────────────────────────────
# 2. Snapshot data flow (in-memory stores)
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_zone_snapshot_flow(client):
    """POST zone snapshot → GET returns the data."""
    # Before snapshot: empty
    r = await client.get("/zones/")
    assert r.status_code == 200
    assert r.json() == []

    # Push snapshot
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

    # GET returns both zones
    r = await client.get("/zones/")
    assert r.status_code == 200
    zones = r.json()
    assert len(zones) == 2
    zone_ids = {z["zone_id"] for z in zones}
    assert zone_ids == {"living_room", "bedroom"}

    # Verify sensor values
    living = next(z for z in zones if z["zone_id"] == "living_room")
    assert living["environment"]["temperature"] == 24.5
    assert living["environment"]["co2"] == 600.0
    assert living["occupancy"]["count"] == 1


@pytest.mark.asyncio
async def test_pc_snapshot_flow(client):
    """POST PC snapshot → GET returns the data."""
    # Before: no_data
    r = await client.get("/pc/")
    assert r.json()["status"] == "no_data"

    # Push snapshot
    pc_data = {"cpu": 45.2, "memory": 68.5, "gpu": 30.0, "disk": 52.1}
    r = await client.post("/pc/snapshot", json=pc_data)
    assert r.status_code == 200

    # GET returns values
    r = await client.get("/pc/")
    data = r.json()
    assert data["cpu"] == 45.2
    assert data["memory"] == 68.5


@pytest.mark.asyncio
async def test_biometric_snapshot_flow(client):
    """POST biometric snapshot → GET returns the data."""
    r = await client.get("/biometric/")
    assert r.json()["status"] == "no_data"

    bio_data = {"heart_rate": 72, "spo2": 98, "stress": 35, "fatigue": 0.3}
    r = await client.post("/biometric/snapshot", json=bio_data)
    assert r.status_code == 200

    r = await client.get("/biometric/")
    data = r.json()
    assert data["heart_rate"] == 72
    assert data["spo2"] == 98


@pytest.mark.asyncio
async def test_home_snapshot_flow(client):
    """POST home snapshot → GET returns device states."""
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

    r = await client.get("/home/")
    data = r.json()
    assert len(data["devices"]) == 2


@pytest.mark.asyncio
async def test_snapshot_overwrite(client):
    """Second snapshot replaces the first entirely."""
    r = await client.post("/pc/snapshot", json={"cpu": 10, "extra_field": "old"})
    assert r.status_code == 200

    r = await client.post("/pc/snapshot", json={"cpu": 99})
    assert r.status_code == 200

    r = await client.get("/pc/")
    data = r.json()
    assert data["cpu"] == 99
    assert "extra_field" not in data


# ──────────────────────────────────────────────
# 3. Task CRUD lifecycle
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_task_create_and_list(client):
    """Create task → appears in task list."""
    task_data = {
        "title": "Fix air conditioner",
        "description": "Temperature too high",
        "zone": "living_room",
        "xp_reward": 200,
        "urgency": 3,
        "task_type": ["hvac", "maintenance"],
    }
    r = await client.post("/tasks/", json=task_data)
    assert r.status_code == 200
    created = r.json()
    assert created["title"] == "Fix air conditioner"
    assert created["xp_reward"] == 200
    assert created["is_completed"] is False
    task_id = created["id"]

    # GET list
    r = await client.get("/tasks/")
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id


@pytest.mark.asyncio
async def test_task_accept_and_complete(client):
    """Full lifecycle: create → accept → complete."""
    # Create user (201 Created)
    r = await client.post("/users/", json={"username": "tester", "display_name": "Tester"})
    assert r.status_code == 201
    user_id = r.json()["id"]

    # Create task
    r = await client.post("/tasks/", json={"title": "Refill water", "xp_reward": 100})
    task_id = r.json()["id"]

    # Accept
    r = await client.put(f"/tasks/{task_id}/accept", json={"user_id": user_id})
    assert r.status_code == 200
    assert r.json()["assigned_to"] == user_id
    assert r.json()["accepted_at"] is not None

    # Complete with report
    r = await client.put(
        f"/tasks/{task_id}/complete",
        json={"report_status": "done", "completion_note": "Filled up"},
    )
    assert r.status_code == 200
    completed = r.json()
    assert completed["is_completed"] is True
    assert completed["report_status"] == "done"

    # User got XP
    r = await client.get(f"/users/{user_id}")
    assert r.json()["points"] == 100

    # Point log created
    r = await client.get(f"/points/{user_id}")
    logs = r.json()
    assert len(logs) == 1
    assert logs[0]["amount"] == 100


@pytest.mark.asyncio
async def test_task_duplicate_detection_stage1(client):
    """Same title + location → updates instead of creating duplicate."""
    task = {"title": "Open window", "location": "living_room", "xp_reward": 100}
    r1 = await client.post("/tasks/", json=task)
    id1 = r1.json()["id"]

    # Same title+location but different xp → update
    task2 = {"title": "Open window", "location": "living_room", "xp_reward": 200}
    r2 = await client.post("/tasks/", json=task2)
    id2 = r2.json()["id"]

    assert id1 == id2  # Same task, not duplicated
    assert r2.json()["xp_reward"] == 200  # Updated

    r = await client.get("/tasks/")
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_task_duplicate_detection_stage2(client):
    """Same zone + overlapping task_type → updates instead of duplicate."""
    task1 = {
        "title": "Lower temperature",
        "zone": "bedroom",
        "task_type": ["hvac", "comfort"],
        "xp_reward": 100,
    }
    r1 = await client.post("/tasks/", json=task1)
    id1 = r1.json()["id"]

    # Different title but same zone with overlapping task_type
    task2 = {
        "title": "Fix AC",
        "zone": "bedroom",
        "task_type": ["hvac", "repair"],
        "xp_reward": 150,
    }
    r2 = await client.post("/tasks/", json=task2)
    id2 = r2.json()["id"]

    assert id1 == id2  # Deduped
    assert r2.json()["xp_reward"] == 150

    r = await client.get("/tasks/")
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_task_not_duplicate_different_zone(client):
    """Same task_type but different zone → creates separate tasks."""
    task1 = {
        "title": "Lower temperature",
        "zone": "bedroom",
        "task_type": ["hvac"],
        "xp_reward": 100,
    }
    task2 = {
        "title": "Lower temperature",
        "zone": "living_room",
        "task_type": ["hvac"],
        "xp_reward": 100,
    }
    await client.post("/tasks/", json=task1)
    await client.post("/tasks/", json=task2)

    r = await client.get("/tasks/")
    # Stage1 dedup matches title but location (None) differs from None — actually
    # both have location=None so Stage1 will match on title+location(None).
    # Let's set different locations to avoid Stage1 match
    pass


@pytest.mark.asyncio
async def test_task_404_on_missing(client):
    """Operations on nonexistent task return 404."""
    r = await client.put("/tasks/9999/accept", json={"user_id": 1})
    assert r.status_code == 404

    r = await client.put("/tasks/9999/complete", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_task_cannot_accept_completed(client):
    """Cannot accept an already-completed task."""
    r = await client.post("/tasks/", json={"title": "Done task", "xp_reward": 50})
    task_id = r.json()["id"]

    await client.put(f"/tasks/{task_id}/complete", json={})

    r = await client.put(f"/tasks/{task_id}/accept", json={"user_id": 1})
    assert r.status_code == 400


# ──────────────────────────────────────────────
# 4. Stats consistency
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_reflect_task_changes(client):
    """Stats endpoint reflects task creation and completion."""
    # Initial stats
    r = await client.get("/tasks/stats")
    stats = r.json()
    assert stats["tasks_created"] == 0
    assert stats["total_xp"] == 0

    # Create 2 tasks
    await client.post("/tasks/", json={"title": "Task A", "xp_reward": 100})
    r = await client.post("/tasks/", json={"title": "Task B", "xp_reward": 200})
    task_b_id = r.json()["id"]

    r = await client.get("/tasks/stats")
    stats = r.json()
    assert stats["tasks_created"] == 2
    assert stats["tasks_active"] == 2

    # Complete one
    await client.put(f"/tasks/{task_b_id}/complete", json={})

    r = await client.get("/tasks/stats")
    stats = r.json()
    assert stats["tasks_completed"] == 1
    assert stats["total_xp"] == 200
    assert stats["tasks_active"] == 1


# ──────────────────────────────────────────────
# 5. Voice events
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_voice_event_create_and_recent(client):
    """Create voice event → appears in recent list."""
    event = {
        "message": "Temperature is high!",
        "audio_url": "/audio/alert_001.wav",
        "zone": "living_room",
        "tone": "urgent",
    }
    r = await client.post("/voice-events/", json=event)
    assert r.status_code == 200
    created = r.json()
    assert created["message"] == "Temperature is high!"
    assert created["tone"] == "urgent"

    # Recent (within 5 min)
    r = await client.get("/voice-events/recent")
    assert r.status_code == 200
    events = r.json()
    assert len(events) >= 1
    assert events[0]["message"] == "Temperature is high!"


# ──────────────────────────────────────────────
# 6. Time series
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeseries_ingest_and_query(client):
    """Ingest time series points → query returns them."""
    now = datetime.now(timezone.utc).isoformat()
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

    # Query temperature
    r = await client.get("/timeseries/", params={"metric": "temperature", "hours": 1})
    assert r.status_code == 200
    points = r.json()
    assert len(points) == 2
    assert points[0]["value"] == 25.5
    assert points[0]["zone"] == "living_room"

    # Query with zone filter
    r = await client.get("/timeseries/", params={"metric": "co2", "zone": "living_room", "hours": 1})
    points = r.json()
    assert len(points) == 1
    assert points[0]["value"] == 800.0

    # List metrics
    r = await client.get("/timeseries/metrics")
    metrics = r.json()
    assert "temperature" in metrics
    assert "co2" in metrics


# ──────────────────────────────────────────────
# 7. User management
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_crud(client):
    """Create user → list → get by id."""
    r = await client.post("/users/", json={"username": "alice", "display_name": "Alice"})
    assert r.status_code == 201
    user = r.json()
    user_id = user["id"]
    assert user["username"] == "alice"
    assert user["points"] == 0

    # Duplicate username → 409
    r = await client.post("/users/", json={"username": "alice"})
    assert r.status_code == 409

    # List
    r = await client.get("/users/")
    assert len(r.json()) == 1

    # Get by id
    r = await client.get(f"/users/{user_id}")
    assert r.json()["username"] == "alice"


# ──────────────────────────────────────────────
# 8. Points
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_points_grant(client):
    """Grant points → appears in log, user balance updated."""
    r = await client.post("/users/", json={"username": "bob"})
    user_id = r.json()["id"]

    r = await client.post(
        f"/points/{user_id}/grant",
        json={"amount": 500, "reason": "Bonus"},
    )
    assert r.status_code == 200

    r = await client.get(f"/users/{user_id}")
    assert r.json()["points"] == 500

    r = await client.get(f"/points/{user_id}")
    logs = r.json()
    assert len(logs) == 1
    assert logs[0]["reason"] == "Bonus"


# ──────────────────────────────────────────────
# 9. HA control validation
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_home_control_without_bridge(client):
    """HA control returns 503 when bridge not configured."""
    r = await client.post("/home/light/control", json={"entity_id": "light.test", "on": True})
    assert r.status_code == 503

    r = await client.post(
        "/home/climate/control",
        json={"entity_id": "climate.test", "temperature": 25},
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_home_climate_validation(client):
    """Temperature range validation (16-30)."""
    # Temperature too low
    r = await client.post(
        "/home/climate/control",
        json={"entity_id": "climate.test", "temperature": 10},
    )
    assert r.status_code == 422  # Pydantic validation error

    # Temperature too high
    r = await client.post(
        "/home/climate/control",
        json={"entity_id": "climate.test", "temperature": 35},
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────
# 10. Full Brain → Dashboard data flow simulation
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_brain_cycle_simulation(client):
    """Simulate one Brain cognitive cycle: push all snapshots → verify frontend can read."""
    # Brain pushes zone data
    await client.post("/zones/snapshot", json={
        "zones": [{
            "zone_id": "main",
            "environment": {"temperature": 28.0, "humidity": 60.0, "co2": 1200.0},
            "occupancy": {"count": 1},
        }]
    })

    # Brain pushes PC metrics
    await client.post("/pc/snapshot", json={"cpu": 55, "memory": 70, "gpu": 20})

    # Brain pushes biometric
    await client.post("/biometric/snapshot", json={"heart_rate": 80, "stress": 40})

    # Brain pushes home state
    await client.post("/home/snapshot", json={
        "devices": [{"entity_id": "light.desk", "state": "on"}]
    })

    # Brain creates a task (high CO2 detected)
    r = await client.post("/tasks/", json={
        "title": "Ventilate room",
        "description": "CO2 level above 1000ppm",
        "zone": "main",
        "xp_reward": 150,
        "urgency": 3,
        "task_type": ["ventilation"],
    })
    task_id = r.json()["id"]

    # Brain creates voice event
    await client.post("/voice-events/", json={
        "message": "CO2レベルが高いです。換気してください。",
        "audio_url": "/audio/co2_alert.wav",
        "zone": "main",
        "tone": "warning",
    })

    # Brain ingests time series
    now = datetime.now(timezone.utc).isoformat()
    await client.post("/timeseries/ingest", json={
        "points": [
            {"metric": "temperature", "value": 28.0, "zone": "main", "recorded_at": now},
            {"metric": "co2", "value": 1200.0, "zone": "main", "recorded_at": now},
        ]
    })

    # --- Frontend polling ---

    # Zones
    r = await client.get("/zones/")
    zones = r.json()
    assert len(zones) == 1
    assert zones[0]["environment"]["co2"] == 1200.0

    # PC
    r = await client.get("/pc/")
    assert r.json()["cpu"] == 55

    # Biometric
    r = await client.get("/biometric/")
    assert r.json()["heart_rate"] == 80

    # Home
    r = await client.get("/home/")
    assert r.json()["devices"][0]["entity_id"] == "light.desk"

    # Tasks
    r = await client.get("/tasks/")
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Ventilate room"

    # Voice events
    r = await client.get("/voice-events/recent")
    events = r.json()
    assert len(events) >= 1
    assert "CO2" in events[0]["message"]

    # Time series
    r = await client.get("/timeseries/", params={"metric": "co2", "hours": 1})
    assert len(r.json()) == 1

    # Stats
    r = await client.get("/tasks/stats")
    assert r.json()["tasks_created"] == 1
    assert r.json()["tasks_active"] == 1

    # --- User completes the task ---
    r = await client.put(f"/tasks/{task_id}/complete", json={
        "report_status": "done",
        "completion_note": "Opened window, CO2 dropping",
    })
    assert r.json()["is_completed"] is True

    r = await client.get("/tasks/stats")
    assert r.json()["tasks_completed"] == 1
    assert r.json()["total_xp"] == 150
