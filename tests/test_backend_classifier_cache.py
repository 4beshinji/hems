"""Tests for /classifier-cache/ CRUD endpoints (P3 Step A)."""
import pytest


try:
    import sqlalchemy  # noqa: F401
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAS_SQLALCHEMY, reason="sqlalchemy not installed")

ADMIN_KEY = "test_admin_key_ccache"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with classifier_cache router mounted on a tmp SQLite file."""
    import asyncio
    import sys
    from pathlib import Path

    backend_path = Path(__file__).resolve().parent.parent / "services" / "backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path/'hems.db'}")
    monkeypatch.setenv("HEMS_API_KEY", ADMIN_KEY)

    # Match the mobile-router fixture pattern — popping `routers` package is
    # required so re-imported routers pick up the fresh Base / models classes.
    for name in ("database", "models", "auth",
                 "routers", "routers.classifier_cache"):
        sys.modules.pop(name, None)

    import database
    from fastapi import FastAPI, Depends
    from routers import classifier_cache
    from auth import verify_api_key

    app = FastAPI()
    app.include_router(classifier_cache.router, dependencies=[Depends(verify_api_key)])

    async def _create():
        async with database.engine.begin() as conn:
            await conn.run_sync(database.Base.metadata.create_all)

    asyncio.new_event_loop().run_until_complete(_create())

    from fastapi.testclient import TestClient
    return TestClient(app)


def _headers() -> dict:
    return {"Authorization": f"Bearer {ADMIN_KEY}"}


def _upsert(client, *, kind="shopping", key_hash="abc123", value="drugstore", source="llm"):
    return client.post(
        "/classifier-cache",
        json={
            "kind": kind, "key_hash": key_hash,
            "value_json": value if value.startswith("{") else f'"{value}"',
            "source": source,
        },
        headers=_headers(),
    )


class TestClassifierCacheAuth:
    def test_requires_admin_key(self, client):
        resp = client.post(
            "/classifier-cache",
            json={"kind": "shopping", "key_hash": "x", "value_json": '"y"', "source": "llm"},
        )
        assert resp.status_code == 401

    def test_rejects_wrong_key(self, client):
        resp = client.post(
            "/classifier-cache",
            json={"kind": "shopping", "key_hash": "x", "value_json": '"y"', "source": "llm"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401


class TestClassifierCacheCrud:
    def test_upsert_creates(self, client):
        resp = _upsert(client, kind="shopping", key_hash="hash_a", value="drugstore")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["kind"] == "shopping"
        assert body["key_hash"] == "hash_a"
        assert body["value_json"] == '"drugstore"'
        assert body["source"] == "llm"
        assert body["hit_count"] == 1

    def test_upsert_overwrites_preserves_hit_count(self, client):
        _upsert(client, kind="shopping", key_hash="hash_b", value="drugstore")
        # Read once to bump hit_count to 2
        client.get("/classifier-cache/shopping/hash_b", headers=_headers())
        # Upsert overwrites value/source but hit_count is preserved
        resp = _upsert(client, kind="shopping", key_hash="hash_b", value="supermarket", source="promoted")
        assert resp.status_code == 201
        body = resp.json()
        assert body["value_json"] == '"supermarket"'
        assert body["source"] == "promoted"
        assert body["hit_count"] >= 2

    def test_get_increments_hit_count(self, client):
        _upsert(client, kind="shopping", key_hash="hash_c", value="drugstore")
        r1 = client.get("/classifier-cache/shopping/hash_c", headers=_headers())
        assert r1.status_code == 200 and r1.json()["hit_count"] == 2
        r2 = client.get("/classifier-cache/shopping/hash_c", headers=_headers())
        assert r2.status_code == 200 and r2.json()["hit_count"] == 3

    def test_get_missing_returns_404(self, client):
        resp = client.get("/classifier-cache/shopping/missing", headers=_headers())
        assert resp.status_code == 404

    def test_list_with_filters(self, client):
        _upsert(client, kind="shopping", key_hash="s1", value="drugstore", source="seed")
        _upsert(client, kind="shopping", key_hash="s2", value="supermarket", source="llm")
        _upsert(client, kind="event_lead", key_hash="e1", value="30", source="llm")

        # Bump s2 hit_count to 3 so min_hit_count=3 filter matters.
        for _ in range(2):
            client.get("/classifier-cache/shopping/s2", headers=_headers())

        shopping_llm = client.get(
            "/classifier-cache?kind=shopping&source=llm", headers=_headers(),
        ).json()
        assert [e["key_hash"] for e in shopping_llm] == ["s2"]

        min3 = client.get(
            "/classifier-cache?kind=shopping&min_hit_count=3", headers=_headers(),
        ).json()
        assert all(e["hit_count"] >= 3 for e in min3)

    def test_delete(self, client):
        _upsert(client, kind="shopping", key_hash="to_del", value="drugstore")
        resp = client.delete("/classifier-cache/shopping/to_del", headers=_headers())
        assert resp.status_code == 200 and resp.json()["deleted"] is True
        # GET now 404
        get = client.get("/classifier-cache/shopping/to_del", headers=_headers())
        assert get.status_code == 404

    def test_upsert_rejects_extra_field(self, client):
        resp = client.post(
            "/classifier-cache",
            json={
                "kind": "shopping", "key_hash": "extra", "value_json": '"x"',
                "source": "llm", "not_a_field": True,
            },
            headers=_headers(),
        )
        assert resp.status_code == 422
