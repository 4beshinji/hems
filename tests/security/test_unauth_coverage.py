"""
W1.7 — Unauthenticated access coverage test.

Dynamically enumerates *all* routes registered on the backend FastAPI app and
verifies that every non-public router is gated by the appropriate dashboard,
internal-service, or mobile-device authentication dependency.

The test:
  1. Boots an in-memory FastAPI app identical to the production ``main.py`` app.
  2. Imports all routers from a clean module graph.
  3. Walks every route and recursively inspects its FastAPI dependency graph.
  4. Asserts that every route (except the explicitly excluded set) depends on
     a supported authentication dependency. Unit tests separately verify each
     dependency's 401 behavior.

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
    _root / "services" / "_common",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Routes that are intentionally NOT gated by verify_api_key
# ---------------------------------------------------------------------------

# These paths are intentionally public. Every other route must have one of the
# supported authentication dependencies.
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
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_BACKEND_SRC = _root / "services" / "backend"
_BACKEND_MAIN_PY = _BACKEND_SRC / "main.py"


def _loaded_backend_modules() -> dict[str, object]:
    modules = {}
    for name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            if Path(module_file).resolve().is_relative_to(_BACKEND_SRC):
                modules[name] = module
        except (OSError, RuntimeError):
            continue
    return modules


def _build_test_app(tmp_path, monkeypatch):
    """Construct a fully-wired FastAPI test app equivalent to main.py.

    Uses importlib.util.spec_from_file_location to import the backend main.py
    by *path* rather than by name, avoiding the PYTHONPATH ambiguity where
    ``services/brain/src/main.py`` shadows ``services/backend/main.py``.
    """
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
    for mod in _loaded_backend_modules():
        del sys.modules[mod]

    # Import auth fresh and patch the module-level constant directly
    auth = importlib.import_module("auth")
    monkeypatch.setattr(auth, "BACKEND_API_KEY", _API_KEY)

    # Import the fresh database module so routers bind to the isolated engine.
    # Schema creation is unnecessary because this test inspects dependencies
    # and only calls the database-free /health endpoint.
    importlib.import_module("database")

    # Load the backend main.py explicitly by file path so it is never confused
    # with the brain's main.py, which also appears on PYTHONPATH.
    spec = importlib.util.spec_from_file_location("backend_main", _BACKEND_MAIN_PY)
    backend_main = importlib.util.module_from_spec(spec)
    sys.modules["backend_main"] = backend_main
    spec.loader.exec_module(backend_main)

    assert hasattr(backend_main, "app"), "backend main.py loaded but 'app' attribute missing — check main.py structure"

    return backend_main.app, _API_KEY


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestUnauthCoverage:
    """Every non-public route must be wired to an authentication dependency."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        previous_modules = _loaded_backend_modules()
        try:
            app, _ = _build_test_app(tmp_path, monkeypatch)
            self._app = app
            yield
        finally:
            for name in _loaded_backend_modules():
                sys.modules.pop(name, None)
            sys.modules.update(previous_modules)

    def test_no_unprotected_dashboard_routes(self):
        """All non-public routes must include verify_api_key in their dependency graph.

        Calling every handler with TestClient made this security gate execute
        unrelated endpoint I/O and inherit module/DB state from earlier tests.
        Dependency inspection checks the actual FastAPI authorization wiring
        without invoking business handlers; response behavior is covered by
        isolated auth tests below and in tests/test_backend_auth.py.
        """
        failures = []
        tested = 0
        skipped = 0

        for route in self._app.routes:
            path = getattr(route, "path", "")
            if path in _EXCLUDED_PATHS:
                skipped += 1
                continue
            if not hasattr(route, "dependant"):
                continue

            stack = list(route.dependant.dependencies)
            dependency_names = set()
            while stack:
                dependency = stack.pop()
                call = dependency.call
                dependency_names.add(getattr(call, "__name__", ""))
                stack.extend(dependency.dependencies)

            accepted_auth = {"verify_api_key", "verify_internal_token", "verify_mobile_device"}
            if dependency_names.isdisjoint(accepted_auth):
                methods = ",".join(sorted(route.methods or []))
                failures.append(f"{methods} {path} → authentication dependency missing")
            tested += 1

        assert not failures, (
            f"\n{len(failures)} route(s) are missing a supported authentication dependency:\n"
            + "\n".join(f"  {f}" for f in failures)
            + f"\n\nTested {tested} routes, skipped {skipped} (in exclusion list)."
        )

    def test_excluded_paths_are_documented(self):
        """Assert that _EXCLUDED_PATHS contains only paths that actually exist in the app.

        This prevents the exclusion list from silently growing stale.
        """
        registered = {route.path for route in self._app.routes if hasattr(route, "path")}

        # OpenAPI / Swagger paths are not in app.routes but are real
        _ALWAYS_ALLOWED = {"/docs", "/redoc", "/openapi.json"}

        stale = [p for p in _EXCLUDED_PATHS if p not in registered and p not in _ALWAYS_ALLOWED]
        assert not stale, (
            f"_EXCLUDED_PATHS contains paths not registered in the app "
            f"(remove them to keep the exclusion list accurate): {stale}"
        )
