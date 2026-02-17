"""
Tests for ToolExecutor get_service_status handler.
"""
import json
import time

import pytest
from world_model.data_classes import ServiceStatusData


class TestGetServiceStatus:
    """Test _handle_get_service_status — reads from world_model.services_state."""

    @pytest.mark.asyncio
    async def test_get_all_services(self, tool_executor, world_model):
        world_model.services_state.services["gmail"] = ServiceStatusData(
            name="gmail", available=True, unread_count=3,
            summary="未読メール: 3通", last_check=time.time(),
        )
        world_model.services_state.services["github"] = ServiceStatusData(
            name="github", available=True, unread_count=5,
            summary="GitHub通知: 5件", last_check=time.time(),
        )

        result = await tool_executor.execute("get_service_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "gmail" in data
        assert "github" in data
        assert data["gmail"]["unread_count"] == 3
        assert data["github"]["unread_count"] == 5

    @pytest.mark.asyncio
    async def test_get_specific_service(self, tool_executor, world_model):
        world_model.services_state.services["gmail"] = ServiceStatusData(
            name="gmail", available=True, unread_count=2,
            summary="未読メール: 2通", last_check=time.time(),
        )

        result = await tool_executor.execute("get_service_status", {"service_name": "gmail"})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["name"] == "gmail"
        assert data["unread_count"] == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent_service(self, tool_executor, world_model):
        result = await tool_executor.execute("get_service_status", {"service_name": "slack"})
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_empty_services(self, tool_executor, world_model):
        result = await tool_executor.execute("get_service_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data == {}

    @pytest.mark.asyncio
    async def test_service_with_error(self, tool_executor, world_model):
        world_model.services_state.services["gmail"] = ServiceStatusData(
            name="gmail", available=False, unread_count=0,
            summary="Gmail接続エラー", error="IMAP timeout",
            last_check=time.time(),
        )

        result = await tool_executor.execute("get_service_status", {"service_name": "gmail"})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["available"] is False
        assert data["error"] == "IMAP timeout"

    @pytest.mark.asyncio
    async def test_sanitizer_allows_get_service_status(self, tool_executor):
        """Verify that sanitizer passes get_service_status through."""
        validation = tool_executor.sanitizer.validate_tool_call("get_service_status", {})
        assert validation["allowed"] is True
