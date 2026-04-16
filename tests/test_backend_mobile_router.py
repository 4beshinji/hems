"""
Tests for backend mobile router + FrequentPlace CRUD + Shopping PATCH.

Covers:
- /mobile/register admin-key gating and payload shape
- /mobile/state/webhook HMAC verification (reject without / wrong sig)
- /mobile/devices disable flow
- /frequent-places CRUD round-trip
- /shopping/{id} PATCH writing store_category
"""
import hashlib
import hmac
import json

import pytest


try:
    import sqlalchemy  # noqa: F401
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")


ADMIN_KEY = "test_admin_key_12345"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient against a file-backed SQLite DB so cross-loop inserts work.

    Using `sqlite+aiosqlite:///:memory:` breaks when a helper spawns its own
    event loop (see TestVoiceCapsule) because in-memory DBs are connection-
    scoped and aiosqlite connections are loop-bound. A tempfile side-steps
    both problems with negligible perf cost.
    """
    import asyncio
    import os
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    db_file = tmp_path / "hems_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("HEMS_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("CHARACTER_VERSION", "test-char@v1")

    # Drop cached modules so env vars take effect on import.
    for name in ("database", "models", "auth", "hmac_util",
                 "routers", "routers.mobile", "routers.frequent_places", "routers.shopping"):
        sys.modules.pop(name, None)

    import database
    from fastapi import FastAPI, Depends
    from routers import mobile, frequent_places, shopping
    from auth import verify_api_key

    app = FastAPI()
    app.include_router(mobile.admin_router)
    app.include_router(mobile.device_router)
    app.include_router(frequent_places.router, dependencies=[Depends(verify_api_key)])
    app.include_router(shopping.router, dependencies=[Depends(verify_api_key)])

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    asyncio.new_event_loop().run_until_complete(_create())

    from fastapi.testclient import TestClient
    return TestClient(app)


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def _register_device(client, label="test-phone") -> dict:
    resp = client.post(
        "/mobile/register",
        json={"device_label": label, "platform": "android"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMobileRegister:
    def test_register_requires_admin_key(self, client):
        resp = client.post("/mobile/register", json={"device_label": "x"})
        assert resp.status_code == 401

    def test_register_rejects_wrong_admin_key(self, client):
        resp = client.post(
            "/mobile/register",
            json={"device_label": "x"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    def test_register_issues_credentials(self, client):
        payload = _register_device(client, "pixel9")
        assert payload["device_id"] >= 1
        assert len(payload["device_key"]) == 64   # 32 bytes hex
        assert len(payload["hmac_secret"]) == 64
        assert payload["character_version"] == "test-char@v1"

    def test_register_returns_unique_keys(self, client):
        a = _register_device(client, "phone-a")
        b = _register_device(client, "phone-b")
        assert a["device_key"] != b["device_key"]
        assert a["hmac_secret"] != b["hmac_secret"]


class TestMobileDeviceAdmin:
    def test_list_and_disable(self, client):
        reg = _register_device(client, "disable-me")
        did = reg["device_id"]

        lst = client.get("/mobile/devices", headers=_admin_headers()).json()
        assert any(d["id"] == did for d in lst)

        resp = client.delete(f"/mobile/devices/{did}", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["disabled"] is True

        # Disabled device rejected on device-authenticated endpoints.
        body = json.dumps({"ts": "2026-04-16T10:00:00+00:00"}).encode()
        sig = hmac.new(reg["hmac_secret"].encode(), body, hashlib.sha256).hexdigest()
        resp2 = client.post(
            "/mobile/state/webhook",
            content=body,
            headers={
                "Authorization": f"Bearer {reg['device_key']}",
                "X-HEMS-Signature": f"sha256={sig}",
                "Content-Type": "application/json",
            },
        )
        assert resp2.status_code == 401


class TestMobileStateWebhook:
    def test_rejects_without_signature(self, client):
        reg = _register_device(client, "sig-test")
        body = json.dumps({"ts": "2026-04-16T10:00:00+00:00"}).encode()
        resp = client.post(
            "/mobile/state/webhook",
            content=body,
            headers={
                "Authorization": f"Bearer {reg['device_key']}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_rejects_wrong_signature(self, client):
        reg = _register_device(client, "sig-test")
        body = json.dumps({"ts": "2026-04-16T10:00:00+00:00"}).encode()
        resp = client.post(
            "/mobile/state/webhook",
            content=body,
            headers={
                "Authorization": f"Bearer {reg['device_key']}",
                "X-HEMS-Signature": "sha256=deadbeef",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_accepts_valid_signature(self, client):
        reg = _register_device(client, "sig-test")
        body = json.dumps({
            "ts": "2026-04-16T10:00:00+00:00",
            "location": {"lat": 35.6, "lon": 139.7, "accuracy_m": 20.0},
            "activity": {"kind": "walking", "confidence": 85},
            "battery_pct": 73,
        }).encode()
        sig = hmac.new(reg["hmac_secret"].encode(), body, hashlib.sha256).hexdigest()
        resp = client.post(
            "/mobile/state/webhook",
            content=body,
            headers={
                "Authorization": f"Bearer {reg['device_key']}",
                "X-HEMS-Signature": f"sha256={sig}",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["received"] is True
        # published_topics is empty when no broker is reachable (tests run without mosquitto)
        assert isinstance(data["published_topics"], list)

    def test_rejects_unknown_device_key(self, client):
        _register_device(client, "sig-test")
        body = json.dumps({"ts": "2026-04-16T10:00:00+00:00"}).encode()
        resp = client.post(
            "/mobile/state/webhook",
            content=body,
            headers={
                "Authorization": "Bearer not_a_real_device_key",
                "X-HEMS-Signature": "sha256=00",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401


class TestFrequentPlaces:
    def test_crud_round_trip(self, client):
        create = client.post(
            "/frequent-places/",
            json={
                "label": "近所のスギ薬局",
                "category": "drugstore",
                "lat": 35.65,
                "lon": 139.72,
                "radius_m": 150,
            },
            headers=_admin_headers(),
        )
        assert create.status_code == 200, create.text
        pid = create.json()["id"]

        lst = client.get("/frequent-places/", headers=_admin_headers()).json()
        assert any(p["id"] == pid for p in lst)

        upd = client.put(
            f"/frequent-places/{pid}",
            json={"radius_m": 250, "enabled": False},
            headers=_admin_headers(),
        )
        assert upd.status_code == 200
        assert upd.json()["radius_m"] == 250
        assert upd.json()["enabled"] is False

        enabled_only = client.get(
            "/frequent-places/?enabled_only=true", headers=_admin_headers(),
        ).json()
        assert all(p["id"] != pid for p in enabled_only)

        deleted = client.delete(f"/frequent-places/{pid}", headers=_admin_headers())
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True


class TestVoiceCapsule:
    """Capsule endpoints (P2 Step A)."""

    def _device_headers(self, reg: dict) -> dict:
        return {"Authorization": f"Bearer {reg['device_key']}"}

    def _insert_capsule(
        self, *, capsule_date: str, clips: list | None = None, invalidated: bool = False,
    ) -> int:
        """Insert a capsule row via raw sqlite3 — bypasses the async stack entirely.

        The async SQLAlchemy engine is tied to a specific event loop; sharing
        it between TestClient's internal loop and a helper-spawned loop leads
        to "no such table" errors even when the file truly has the table.
        Going through sqlite3 directly avoids the loop-binding problem.
        """
        import os as _os
        import sqlite3 as _sqlite3
        import database

        # Strip the driver/scheme: "sqlite+aiosqlite:///" → "/" path.
        db_path = database.DATABASE_URL.split("///", 1)[1]
        manifest = {
            "capsule_id": capsule_date,
            "character_version": "test-char@v1",
            "clips": clips or [],
            "generic_bank": [],
        }
        with _sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "INSERT INTO voice_capsules "
                "(capsule_date, character_version, manifest_json, invalidated) "
                "VALUES (?, ?, ?, ?)",
                (capsule_date, "test-char@v1", json.dumps(manifest), 1 if invalidated else 0),
            )
            conn.commit()
            return cur.lastrowid or 0

    def test_latest_returns_404_when_empty(self, client):
        reg = _register_device(client, "cap-empty")
        resp = client.get("/mobile/voice-capsule/latest", headers=self._device_headers(reg))
        assert resp.status_code == 404

    def test_latest_returns_newest_non_invalidated(self, client):
        reg = _register_device(client, "cap-latest")
        old_id = self._insert_capsule(capsule_date="2026-04-15")
        new_id = self._insert_capsule(capsule_date="2026-04-16")
        # Also insert a later-but-invalidated one to verify filtering
        self._insert_capsule(capsule_date="2026-04-17", invalidated=True)

        resp = client.get("/mobile/voice-capsule/latest", headers=self._device_headers(reg))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["capsule_id"] == "2026-04-16"
        assert new_id > old_id

    def test_get_by_id(self, client):
        reg = _register_device(client, "cap-by-id")
        self._insert_capsule(capsule_date="2026-04-16")

        resp = client.get("/mobile/voice-capsule/2026-04-16", headers=self._device_headers(reg))
        assert resp.status_code == 200
        assert resp.json()["capsule_id"] == "2026-04-16"

        missing = client.get("/mobile/voice-capsule/2099-01-01", headers=self._device_headers(reg))
        assert missing.status_code == 404

    def test_capsule_requires_device_auth(self, client):
        self._insert_capsule(capsule_date="2026-04-16")
        resp = client.get("/mobile/voice-capsule/latest")
        assert resp.status_code == 401

    def test_ack_records_play_log(self, client):
        import asyncio as _asyncio
        import database
        import models as _models

        reg = _register_device(client, "cap-ack")
        self._insert_capsule(capsule_date="2026-04-16")

        ack = client.post(
            "/mobile/voice-capsule/ack",
            json={
                "capsule_id": "2026-04-16",
                "clip_id": "morning_greet",
                "played_at": "2026-04-16T07:31:02+09:00",
                "trigger_drift_sec": 2,
            },
            headers=self._device_headers(reg),
        )
        assert ack.status_code == 204, ack.text

        import sqlite3 as _sqlite3
        db_path = database.DATABASE_URL.split("///", 1)[1]
        with _sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM voice_capsule_play_log"
            ).fetchone()[0]
        assert count == 1

    def test_ack_rejects_unknown_capsule(self, client):
        reg = _register_device(client, "cap-ack-missing")
        resp = client.post(
            "/mobile/voice-capsule/ack",
            json={
                "capsule_id": "2099-01-01",
                "clip_id": "x",
                "played_at": "2026-04-16T07:31:02+09:00",
            },
            headers=self._device_headers(reg),
        )
        assert resp.status_code == 404

    def test_audio_rejects_invalid_filename(self, client):
        reg = _register_device(client, "audio-bad")
        resp = client.get(
            "/mobile/voice-capsule/audio/..%2Fetc%2Fpasswd",
            headers=self._device_headers(reg),
        )
        assert resp.status_code in (400, 404)  # FastAPI may 404 before hitting handler

        resp2 = client.get(
            "/mobile/voice-capsule/audio/weird.txt",
            headers=self._device_headers(reg),
        )
        assert resp2.status_code == 400

    def test_audio_requires_device_auth(self, client):
        resp = client.get("/mobile/voice-capsule/audio/capsule_2026-04-16_greet.mp3")
        assert resp.status_code == 401

    def test_admin_upsert_creates_and_overwrites(self, client):
        reg = _register_device(client, "upsert-test")

        manifest_a = {
            "capsule_id": "2026-04-18",
            "character_version": "v1",
            "clips": [{
                "id": "greet",
                "trigger": {"kind": "time", "at": "07:00"},
                "audio_url": "/mobile/voice-capsule/audio/capsule_2026-04-18_greet.mp3",
                "transcript": "おはよう。",
                "tone": "caring",
            }],
        }
        resp_a = client.post("/mobile/voice-capsule", json=manifest_a, headers=_admin_headers())
        assert resp_a.status_code == 201, resp_a.text
        assert resp_a.json()["capsule_id"] == "2026-04-18"

        # Phone retrieves it
        resp_latest = client.get(
            "/mobile/voice-capsule/latest", headers=self._device_headers(reg),
        )
        assert resp_latest.status_code == 200
        assert resp_latest.json()["character_version"] == "v1"

        # Upsert with same capsule_id → overwrites (still only one row)
        manifest_b = {**manifest_a, "character_version": "v2", "clips": []}
        resp_b = client.post("/mobile/voice-capsule", json=manifest_b, headers=_admin_headers())
        assert resp_b.status_code == 201

        resp_after = client.get(
            "/mobile/voice-capsule/2026-04-18", headers=self._device_headers(reg),
        )
        assert resp_after.status_code == 200
        assert resp_after.json()["character_version"] == "v2"
        assert resp_after.json()["clips"] == []

    def test_admin_upsert_requires_admin_key(self, client):
        manifest = {"capsule_id": "2026-04-18", "clips": [], "generic_bank": []}
        resp = client.post("/mobile/voice-capsule", json=manifest)
        assert resp.status_code == 401

    def test_admin_play_log_list(self, client):
        reg = _register_device(client, "play-log-test")
        self._insert_capsule(capsule_date="2026-04-20")

        client.post(
            "/mobile/voice-capsule/ack",
            json={
                "capsule_id": "2026-04-20", "clip_id": "morning_greet",
                "played_at": "2026-04-20T07:31:00+00:00", "trigger_drift_sec": 5,
            },
            headers=self._device_headers(reg),
        )
        client.post(
            "/mobile/voice-capsule/ack",
            json={
                "capsule_id": "2026-04-20", "clip_id": "weather_morning",
                "played_at": "2026-04-20T07:33:00+00:00",
            },
            headers=self._device_headers(reg),
        )

        # Admin lists all play logs from the last 30 days.
        all_logs = client.get("/mobile/voice-capsule/play-log", headers=_admin_headers())
        assert all_logs.status_code == 200, all_logs.text
        assert len(all_logs.json()) == 2

        # Filter by clip_id.
        one = client.get(
            "/mobile/voice-capsule/play-log?clip_id=morning_greet",
            headers=_admin_headers(),
        ).json()
        assert len(one) == 1
        assert one[0]["clip_id"] == "morning_greet"
        assert one[0]["trigger_drift_sec"] == 5

    def test_admin_play_log_requires_admin_key(self, client):
        resp = client.get("/mobile/voice-capsule/play-log")
        assert resp.status_code == 401


class TestShoppingPatch:
    def test_patch_store_category(self, client):
        add = client.post(
            "/shopping/",
            json={"name": "シャンプー"},
            headers=_admin_headers(),
        )
        assert add.status_code == 200
        iid = add.json()["id"]
        assert add.json().get("store_category") is None

        patch = client.patch(
            f"/shopping/{iid}",
            json={"store_category": "drugstore"},
            headers=_admin_headers(),
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["store_category"] == "drugstore"

    def test_patch_rejects_unknown_field(self, client):
        add = client.post("/shopping/", json={"name": "x"}, headers=_admin_headers())
        iid = add.json()["id"]
        resp = client.patch(
            f"/shopping/{iid}",
            json={"completely_unknown": True},
            headers=_admin_headers(),
        )
        assert resp.status_code == 422
