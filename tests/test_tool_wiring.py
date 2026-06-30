"""
Regression tests for split tool wiring.
"""

import importlib
import os
from contextlib import contextmanager
from unittest.mock import AsyncMock


@contextmanager
def _openclaw_env(openclaw_url: str | None, localcraw_url: str | None):
    keys = ("OPENCLAW_BRIDGE_URL", "LOCALCRAW_BRIDGE_URL")
    old_values = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        if openclaw_url is not None:
            os.environ["OPENCLAW_BRIDGE_URL"] = openclaw_url
        if localcraw_url is not None:
            os.environ["LOCALCRAW_BRIDGE_URL"] = localcraw_url
        yield
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_tool_dispatch_handlers_exist_on_executor(tool_executor):
    from tool_dispatch import TOOL_HANDLERS

    missing = [handler_name for handler_name in TOOL_HANDLERS.values() if not hasattr(tool_executor, handler_name)]
    assert missing == []


async def _noop(*args, **kwargs):
    return None


def test_openclaw_url_prefers_canonical_env():
    with _openclaw_env("http://openclaw:8000", "http://localcraw:8000"):
        import brain_constants
        import tool_executor

        importlib.reload(brain_constants)
        importlib.reload(tool_executor)
        assert brain_constants.OPENCLAW_BRIDGE_URL == "http://openclaw:8000"
        assert brain_constants.LOCALCRAW_BRIDGE_URL == "http://openclaw:8000"
        assert tool_executor.OPENCLAW_BRIDGE_URL == "http://openclaw:8000"

    importlib.reload(brain_constants)
    importlib.reload(tool_executor)


def test_openclaw_url_falls_back_to_legacy_alias(sanitizer, mock_session, world_model):
    with _openclaw_env(None, "http://localcraw:8000"):
        import brain_constants
        import tool_executor

        importlib.reload(brain_constants)
        tool_executor = importlib.reload(tool_executor)
        executor = tool_executor.ToolExecutor(
            sanitizer=sanitizer,
            dashboard_client=AsyncMock(),
            world_model=world_model,
            task_queue=AsyncMock(),
            session=mock_session,
        )
        assert brain_constants.OPENCLAW_BRIDGE_URL == "http://localcraw:8000"
        assert brain_constants.LOCALCRAW_BRIDGE_URL == "http://localcraw:8000"
        assert tool_executor.OPENCLAW_BRIDGE_URL == "http://localcraw:8000"
        assert executor.openclaw_url == "http://localcraw:8000"

    importlib.reload(brain_constants)
    importlib.reload(tool_executor)
