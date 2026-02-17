"""
Shared fixtures for HEMS OpenClaw integration tests.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add service source directories to path so tests can import them
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "services" / "brain" / "src"))
sys.path.insert(0, str(_root / "services" / "openclaw-bridge" / "src"))
sys.path.insert(0, str(_root / "services" / "backend"))


@pytest.fixture
def world_model():
    """Fresh WorldModel instance."""
    from world_model import WorldModel
    return WorldModel()


@pytest.fixture
def pc_state():
    """Fresh PCState instance."""
    from world_model.data_classes import PCState
    return PCState()


@pytest.fixture
def sanitizer():
    """Fresh Sanitizer instance."""
    from sanitizer import Sanitizer
    return Sanitizer()


@pytest.fixture
def mock_session():
    """Mock aiohttp.ClientSession with context-manager-aware post/get."""
    session = AsyncMock()

    def _make_response(status=200, json_data=None):
        resp = AsyncMock()
        resp.status = status
        resp.json = AsyncMock(return_value=json_data or {})
        resp.text = AsyncMock(return_value="")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session._make_response = _make_response
    session.post = MagicMock(return_value=_make_response())
    session.get = MagicMock(return_value=_make_response())
    return session


@pytest.fixture
def tool_executor(sanitizer, mock_session, world_model):
    """ToolExecutor with mocked dependencies."""
    from tool_executor import ToolExecutor
    mcp = AsyncMock()
    dashboard = AsyncMock()
    task_queue = AsyncMock()
    device_registry = MagicMock()

    executor = ToolExecutor(
        sanitizer=sanitizer, mcp_bridge=mcp,
        dashboard_client=dashboard, world_model=world_model,
        task_queue=task_queue, session=mock_session,
        device_registry=device_registry,
    )
    return executor
