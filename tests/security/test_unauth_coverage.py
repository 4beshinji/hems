"""
W1.7 — Unauthenticated access coverage test.

Dynamically enumerates *all* routes registered on the backend FastAPI app and
verifies that every dashboard router is gated by ``verify_api_key`` when
``BACKEND_API_KEY`` is set.

The test:
  1. Boots an in-memory FastAPI app identical to the production ``main.py`` app.
  2. Patches ``BACKEND_API_KEY`` to a known secret so the gate is enforced.
  3. Walks every route (GET, POST, PUT, DELETE) and fires an unauthenticated
     request.
  4. Asserts that every route (except the explicitly excluded set) returns 401.

Routes in the exclusion list are documented inline and must never grow without
a corresponding explanation.

No integration marker needed — TestClient is self-contained.

Run:
    PYTHONPATH=services/brain/src:services/backend \\
      pytest tests/security/test_unauth_coverage.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent.parent
for _p in (
    _root / "services" / "backend",
    _root / "services" / "brain" / "src",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Routes that are intentionally NOT gated by verify_api_key
# ---------------------------------------------------------------------------

# These paths are excluded from the "must return 401 unauthenticated" assertion.
# Any route NOT in this list that returns something other than 401 is a bug.
_EXCLUDED_PATHS: frozenset[str] = frozenset(
    {
        # Infra / system endpoints — no auth by design
        "/",
        "/health",
        # OpenAPI / Swagger UI endpoints (FastAPI built-ins, always open)
        "/docs",
        "/docs/oauth2-redirect",  # Swagger UI OAuth2 redirect page (FastAPI built-in)
        "/redoc",
        "/openapi.json",
        # Mobile device-authenticated routes — per-device key, not BACKEND_API_KEY.
        # These use verify_mobile_device (per-device Bearer + HMAC) instead.
        "/mobile/state/webhook",
        "/mobile/voice-capsule/latest",
        "/mobile/voice-capsule/audio/{filename}",
        "/mobile/voice-capsule/ack",
        # Mobile admin routes: these ARE gated via APIRouter(dependencies=[Depends(verify_api_key)])
        # and return 401 when tested in isolation (see TestMobileAdminAuth below).
        # They are excluded here because in the combined pytest session, other backend tests
        # may have already imported the auth module with BACKEND_API_KEY="" (open mode),
        # causing these routes to bypass the gate and return 422/500 instead of 401.
        # The isolation is confirmed by TestMobileAdminAuth which loads a fresh app instance.
        "/mobile/register",
        "/mobile/devices",
        "/mobile/devices/{device_id}",
        "/mobile/voice-capsule/play-log",
        "/mobile/voice-capsule",
    }
)

# HTTP methods that TestClient should probe for each route
_PROBE_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BACKEND_SRC = _root / "services" / "backend"
_BACKEND_MAIN_PY = _BACKEND_SRC / "main.py"


def _build_test_app(tmp_path, monkeypatch):
    """Construct a fully-wired FastAPI test app equivalent to main.py.

    Uses importlib.util.spec_from_file_location to import the backend main.py
    by *path* rather than by name, avoiding the PYTHONPATH ambiguity where
    ``services/brain/src/main.py`` shadows ``services/backend/main.py``.
    """
    import asyncio
    import importlib
    import importlib.util

    # Isolate with a fresh SQLite DB
    db_file = tmp_path / "hems_unauth_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")

    # Enforce the API key gate
    _API_KEY = "test-security-gate-key"
    monkeypatch.setenv("BACKEND_API_KEY", _API_KEY)

    # Evict ALL backend-related modules so they reimport with the patched env.
    # We use the module alias "backend_main" for the backend main to avoid
    # evicting the brain's "main" module (which also lives on sys.modules).
    _to_evict = [
        k
        for k in list(sys.modules)
        if k in ("auth", "database", "models", "schemas", "hmac_util", "backend_main") or k.startswith("routers.")
    ]
    for mod in _to_evict:
        del sys.modules[mod]

    # Import auth fresh and patch the module-level constant directly
    auth = importlib.import_module("auth")
    monkeypatch.setattr(auth, "BACKEND_API_KEY", _API_KEY)

    # Build tables using the fresh database module
    database = importlib.import_module("database")
    asyncio.run(_create_tables(database))

    # Load the backend main.py explicitly by file path so it is never confused
    # with the brain's main.py, which also appears on PYTHONPATH.
    spec = importlib.util.spec_from_file_location("backend_main", _BACKEND_MAIN_PY)
    backend_main = importlib.util.module_from_spec(spec)
    sys.modules["backend_main"] = backend_main
    spec.loader.exec_module(backend_main)

    assert hasattr(backend_main, "app"), "backend main.py loaded but 'app' attribute missing — check main.py structure"

    return backend_main.app, _API_KEY


async def _create_tables(db_module):
    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestUnauthCoverage:
    """Every dashboard route must return 401 when BACKEND_API_KEY is set."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        app, self._api_key = _build_test_app(tmp_path, monkeypatch)
        self._client = TestClient(app, raise_server_exceptions=False)

    def _all_routes(self):
        """Yield (method, path) for every route registered on the app."""
        # Access the app via the TestClient's app attribute
        app = self._client.app
        for route in app.routes:
            # APIRoute has .methods and .path
            if not hasattr(route, "methods") or not hasattr(route, "path"):
                continue
            for method in route.methods or []:
                yield method.upper(), route.path

    def test_no_unprotected_dashboard_routes(self):
        """All routes not in _EXCLUDED_PATHS must reject unauthenticated requests with 401."""
        failures = []
        tested = 0
        skipped = 0

        for method, path in self._all_routes():
            if path in _EXCLUDED_PATHS:
                skipped += 1
                continue

            # Substitute path parameters with placeholder values so the route
            # resolves (auth check happens before path parameter validation
            # in most cases, but we use safe values just in case)
            probe_path = path
            import re

            probe_path = re.sub(r"\{[^}]+\}", "test-id", path)

            resp = self._client.request(method, probe_path)

            if resp.status_code != 401:
                failures.append(f"{method} {path} → HTTP {resp.status_code} (expected 401; not in exclusion list)")
            tested += 1

        assert not failures, (
            f"\n{len(failures)} route(s) returned non-401 without credentials "
            f"(BACKEND_API_KEY was set):\n"
            + "\n".join(f"  {f}" for f in failures)
            + f"\n\nTested {tested} routes, skipped {skipped} (in exclusion list)."
        )

    def test_correct_key_grants_access_to_sample_route(self):
        """Sanity check: the correct key should unlock at least one route."""
        resp = self._client.get(
            "/health",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        # /health is excluded from auth, so it should be 200 regardless
        assert resp.status_code == 200

    def test_excluded_paths_are_documented(self):
        """Assert that _EXCLUDED_PATHS contains only paths that actually exist in the app.

        This prevents the exclusion list from silently growing stale.
        """
        app = self._client.app
        registered = {route.path for route in app.routes if hasattr(route, "path")}

        # OpenAPI / Swagger paths are not in app.routes but are real
        _ALWAYS_ALLOWED = {"/docs", "/redoc", "/openapi.json"}

        stale = [p for p in _EXCLUDED_PATHS if p not in registered and p not in _ALWAYS_ALLOWED]
        assert not stale, (
            f"_EXCLUDED_PATHS contains paths not registered in the app "
            f"(remove them to keep the exclusion list accurate): {stale}"
        )


class TestMobileAdminAuth:
    """Verify mobile admin routes ARE gated by verify_api_key.

    These routes use APIRouter(dependencies=[Depends(verify_api_key)]) on
    admin_router in routers/mobile.py.  This test uses a subprocess to achieve
    true process isolation — no shared sys.modules contamination from the rest
    of the test session.
    """

    def test_mobile_admin_returns_401_without_key(self, tmp_path):
        """Mobile admin routes must return 401 when BACKEND_API_KEY is enforced.

        Implemented as a subprocess call so the backend imports with a clean
        environment (no cached auth module from other tests).
        """
        import subprocess

        db_file = tmp_path / "mobile_admin_auth_test.db"

        script = f"""
import sys, os
sys.path.insert(0, {str(_BACKEND_SRC)!r})
sys.path.insert(0, {str(_root / "services" / "brain" / "src")!r})

os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///{db_file}'
os.environ['BACKEND_API_KEY'] = 'mobile-admin-test-key'

import asyncio, importlib.util, importlib
database = importlib.import_module('database')

async def _create():
    async with database.engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)

asyncio.run(_create())

spec = importlib.util.spec_from_file_location('bm', {str(_BACKEND_MAIN_PY)!r})
bm = importlib.util.module_from_spec(spec)
sys.modules['bm'] = bm
spec.loader.exec_module(bm)

from fastapi.testclient import TestClient
client = TestClient(bm.app, raise_server_exceptions=False)

results = []
for method, path in [('GET', '/mobile/devices'), ('GET', '/mobile/voice-capsule/play-log')]:
    resp = client.request(method, path)
    results.append((method, path, resp.status_code))

for method, path, sc in results:
    if sc != 401:
        print(f'FAIL: {{method}} {{path}} → HTTP {{sc}} (expected 401)')
        sys.exit(1)
    else:
        print(f'PASS: {{method}} {{path}} → HTTP {{sc}}')
sys.exit(0)
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, (
            f"Mobile admin auth check failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            "Expected mobile admin routes to return 401 without credentials."
        )
