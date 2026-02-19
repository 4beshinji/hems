"""
Tests for ToolExecutor PC tool handlers.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from world_model.data_classes import CPUData, MemoryData, GPUData, DiskData, DiskPartition, ProcessInfo


class TestGetPCStatus:
    """Test _handle_get_pc_status — reads from world_model.pc_state."""

    @pytest.mark.asyncio
    async def test_returns_cpu_metrics(self, tool_executor, world_model):
        world_model.pc_state.cpu = CPUData(
            usage_percent=42, core_count=8, temp_c=55, last_update=1.0,
        )
        result = await tool_executor.execute("get_pc_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["cpu_percent"] == 42
        assert data["cpu_cores"] == 8

    @pytest.mark.asyncio
    async def test_returns_memory_metrics(self, tool_executor, world_model):
        world_model.pc_state.memory = MemoryData(
            used_gb=12.5, total_gb=32.0, percent=39.1, last_update=1.0,
        )
        result = await tool_executor.execute("get_pc_status", {})
        data = json.loads(result["result"])
        assert data["memory_percent"] == 39.1
        assert data["memory_used_gb"] == 12.5

    @pytest.mark.asyncio
    async def test_includes_processes_when_requested(self, tool_executor, world_model):
        world_model.pc_state.top_processes = [
            ProcessInfo(pid=100, name="python", cpu_percent=10.0, mem_mb=256),
        ]
        result = await tool_executor.execute("get_pc_status", {"include_processes": True})
        data = json.loads(result["result"])
        assert "processes" in data
        assert data["processes"][0]["name"] == "python"

    @pytest.mark.asyncio
    async def test_no_processes_by_default(self, tool_executor, world_model):
        world_model.pc_state.top_processes = [
            ProcessInfo(pid=100, name="python", cpu_percent=10.0, mem_mb=256),
        ]
        result = await tool_executor.execute("get_pc_status", {})
        data = json.loads(result["result"])
        assert "processes" not in data

    @pytest.mark.asyncio
    async def test_includes_disk_partitions(self, tool_executor, world_model):
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=100, total_gb=500, percent=20)],
            last_update=1.0,
        )
        result = await tool_executor.execute("get_pc_status", {})
        data = json.loads(result["result"])
        assert "disk" in data
        assert data["disk"][0]["mount"] == "/"


class TestRunPCCommand:
    """Test _handle_run_pc_command — proxies to bridge REST."""

    @pytest.mark.asyncio
    async def test_not_configured_returns_error(self, tool_executor):
        tool_executor.openclaw_url = ""
        result = await tool_executor.execute("run_pc_command", {"command": "ls"})
        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_calls_bridge_api(self, tool_executor, mock_session):
        tool_executor.openclaw_url = "http://openclaw-bridge:8000"
        resp = mock_session._make_response(200, {"result": {"stdout": "hello", "stderr": ""}})
        mock_session.post = MagicMock(return_value=resp)

        result = await tool_executor.execute("run_pc_command", {"command": "echo hello"})
        assert result["success"] is True
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "/api/pc/command" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_dangerous_command_blocked_by_sanitizer(self, tool_executor):
        tool_executor.openclaw_url = "http://openclaw-bridge:8000"
        result = await tool_executor.execute("run_pc_command", {"command": "rm -rf /"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_bridge_error_propagated(self, tool_executor, mock_session):
        tool_executor.openclaw_url = "http://openclaw-bridge:8000"
        resp = mock_session._make_response(503, {"detail": "Gateway not connected"})
        mock_session.post = MagicMock(return_value=resp)

        result = await tool_executor.execute("run_pc_command", {"command": "ls"})
        assert result["success"] is False
        assert "Gateway not connected" in result["error"]


class TestControlBrowser:
    """Test _handle_control_browser — proxies to bridge REST."""

    @pytest.mark.asyncio
    async def test_not_configured_returns_error(self, tool_executor):
        tool_executor.openclaw_url = ""
        result = await tool_executor.execute("control_browser", {"action": "get_url"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_navigate_calls_correct_endpoint(self, tool_executor, mock_session):
        tool_executor.openclaw_url = "http://bridge:8000"
        resp = mock_session._make_response(200, {"result": {}})
        mock_session.post = MagicMock(return_value=resp)

        result = await tool_executor.execute("control_browser", {
            "action": "navigate", "url": "https://example.com",
        })
        assert result["success"] is True
        call_url = mock_session.post.call_args[0][0]
        assert "/api/pc/browser/navigate" in call_url

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self, tool_executor):
        tool_executor.openclaw_url = "http://bridge:8000"
        result = await tool_executor.execute("control_browser", {"action": "delete_everything"})
        assert result["success"] is False
        assert "Unknown browser action" in result["error"]


class TestSendPCNotification:
    """Test _handle_send_pc_notification — proxies to bridge REST."""

    @pytest.mark.asyncio
    async def test_not_configured_returns_error(self, tool_executor):
        tool_executor.openclaw_url = ""
        result = await tool_executor.execute("send_pc_notification", {
            "title": "Test", "body": "Hello",
        })
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_calls_bridge_notify(self, tool_executor, mock_session):
        tool_executor.openclaw_url = "http://bridge:8000"
        resp = mock_session._make_response(200, {"result": {}})
        mock_session.post = MagicMock(return_value=resp)

        result = await tool_executor.execute("send_pc_notification", {
            "title": "HEMS Alert", "body": "GPU is hot!",
        })
        assert result["success"] is True
        call_url = mock_session.post.call_args[0][0]
        assert "/api/pc/notify" in call_url
