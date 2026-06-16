"""Regression tests for the biometric-bridge W3.9 HEMS_INTERNAL_TOKEN auth wiring.

Verifies that:
1. The bridge modules import without errors (hems_common wiring is correct).
2. config module-level MQTT constants are still exported (backward compat).
3. /health stays public for Docker healthchecks.
4. /api/biometric/webhook stays public (external companion apps push there).
5. /api/biometric/latest, /api/biometric/sleep, and /api/biometric/activity
   require the internal bearer token when HEMS_INTERNAL_TOKEN is configured.

Isolation note: biometric-bridge modules are loaded via importlib to avoid
sys.modules pollution from other bridge test files.
"""

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_BIOMETRIC_SRC = Path(__file__).resolve().parent.parent / "services" / "biometric-bridge" / "src"


def _load_biometric_module(name: str) -> ModuleType:
    """Load a module from biometric-bridge/src by file path, bypassing sys.modules cache.

    Registers the module under a namespaced key (``biometric_bridge.<name>``) so it
    does not collide with same-named flat modules from other bridges.
    """
    ns_key = f"biometric_bridge.{name}"

    saved_config = sys.modules.get("config")
    biometric_config_key = "biometric_bridge.config"

    if biometric_config_key not in sys.modules:
        cfg_file = _BIOMETRIC_SRC / "config.py"
        cfg_spec = importlib.util.spec_from_file_location(biometric_config_key, cfg_file)
        cfg_mod = importlib.util.module_from_spec(cfg_spec)
        sys.modules[biometric_config_key] = cfg_mod
        sys.modules["config"] = cfg_mod
        cfg_spec.loader.exec_module(cfg_mod)
    else:
        sys.modules["config"] = sys.modules[biometric_config_key]

    _src_str = str(_BIOMETRIC_SRC)
    added_path = _src_str not in sys.path
    if added_path:
        sys.path.insert(0, _src_str)

    try:
        if ns_key in sys.modules:
            return sys.modules[ns_key]

        file_path = _BIOMETRIC_SRC / f"{name}.py"
        spec = importlib.util.spec_from_file_location(ns_key, file_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[ns_key] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if added_path and _src_str in sys.path:
            sys.path.remove(_src_str)
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_import_config():
    cfg = _load_biometric_module("config")
    assert hasattr(cfg, "MQTT_BROKER")
    assert hasattr(cfg, "MQTT_PORT")
    assert hasattr(cfg, "MQTT_USER")
    assert hasattr(cfg, "MQTT_PASS")


def test_import_main():
    pytest.importorskip("aiohttp")
    pytest.importorskip("aiosqlite")
    m = _load_biometric_module("main")
    assert hasattr(m, "app")


# ---------------------------------------------------------------------------
# HEMS_INTERNAL_TOKEN auth (W3.9)
# ---------------------------------------------------------------------------


_PRIVATE_ENDPOINTS = [
    "/api/biometric/latest",
    "/api/biometric/sleep",
    "/api/biometric/activity",
]


def _biometric_test_client(tmp_path) -> tuple[ModuleType, TestClient]:
    """Load biometric-bridge main with a temp DB path and return (module, client)."""
    pytest.importorskip("aiohttp")
    pytest.importorskip("aiosqlite")
    # Force a fresh config load so environment overrides are honoured.
    sys.modules.pop("biometric_bridge.main", None)
    sys.modules.pop("biometric_bridge.config", None)
    sys.modules.pop("config", None)
    os.environ.pop("BIOMETRIC_WEBHOOK_SECRET", None)
    os.environ["BIOMETRIC_DB_PATH"] = str(tmp_path / "send_queue.db")
    os.environ["HUAMI_ENABLED"] = "false"
    os.environ["ZEPP_ENABLED"] = "false"
    m = _load_biometric_module("main")
    # Provide a mock publisher so /health never tries to talk to a real broker.
    m.mqtt_pub = MagicMock()
    return m, TestClient(m.app)


def test_health_requires_no_auth(monkeypatch, tmp_path):
    """/health must stay public for Docker healthchecks."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    _m, client = _biometric_test_client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_stays_public(monkeypatch, tmp_path):
    """/api/biometric/webhook must not be protected by HEMS_INTERNAL_TOKEN."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _biometric_test_client(tmp_path)
    response = client.post("/api/biometric/webhook", content=b"")
    # With no BIOMETRIC_WEBHOOK_SECRET and an empty body the webhook returns 400,
    # but it must NOT be blocked by the internal-token dependency (401).
    assert response.status_code != 401


def test_api_skips_auth_when_token_unset(monkeypatch, tmp_path):
    """Dev mode: no HEMS_INTERNAL_TOKEN means the dependency is a no-op."""
    monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
    _m, client = _biometric_test_client(tmp_path)
    response = client.get("/api/biometric/latest")
    assert response.status_code == 200
    assert response.json()["status"] == "no_data"


@pytest.mark.parametrize("path", _PRIVATE_ENDPOINTS)
def test_api_requires_auth_when_token_configured(monkeypatch, tmp_path, path):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _biometric_test_client(tmp_path)
    response = client.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PRIVATE_ENDPOINTS)
def test_api_rejects_wrong_token(monkeypatch, tmp_path, path):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _biometric_test_client(tmp_path)
    response = client.get(path, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", _PRIVATE_ENDPOINTS)
def test_api_accepts_valid_token(monkeypatch, tmp_path, path):
    monkeypatch.setenv("HEMS_INTERNAL_TOKEN", "secret")
    _m, client = _biometric_test_client(tmp_path)
    response = client.get(path, headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
