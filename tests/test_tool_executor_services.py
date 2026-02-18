"""
Tests for ToolExecutor get_service_status handler, get_pc_status handler,
and Sanitizer pc_command validation.
"""
import json
import time

import pytest
from world_model.data_classes import ServiceStatusData, ProcessInfo


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


class TestGetPCStatus:
    """Test _handle_get_pc_status — reads from world_model.pc_state."""

    @pytest.mark.asyncio
    async def test_get_pc_status_default(self, tool_executor, world_model):
        world_model.pc_state.cpu.usage_percent = 55.0
        world_model.pc_state.cpu.core_count = 8
        world_model.pc_state.memory.percent = 40.0
        world_model.pc_state.memory.used_gb = 12.0
        world_model.pc_state.memory.total_gb = 32.0
        world_model.pc_state.bridge_connected = True

        result = await tool_executor.execute("get_pc_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["cpu_percent"] == 55.0
        assert data["memory_percent"] == 40.0
        assert data["bridge_connected"] is True
        assert "processes" not in data

    @pytest.mark.asyncio
    async def test_get_pc_status_with_processes(self, tool_executor, world_model):
        world_model.pc_state.top_processes = [
            ProcessInfo(pid=1234, name="python", cpu_percent=20.0, mem_mb=256.0),
            ProcessInfo(pid=5678, name="chrome", cpu_percent=5.0, mem_mb=512.0),
        ]

        result = await tool_executor.execute("get_pc_status", {"include_processes": True})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "processes" in data
        assert data["processes"][0]["name"] == "python"
        assert data["processes"][0]["pid"] == 1234

    @pytest.mark.asyncio
    async def test_get_pc_status_without_processes_flag(self, tool_executor, world_model):
        world_model.pc_state.top_processes = [
            ProcessInfo(pid=1, name="python", cpu_percent=10.0, mem_mb=100.0),
        ]

        result = await tool_executor.execute("get_pc_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "processes" not in data

    @pytest.mark.asyncio
    async def test_get_pc_status_with_disk(self, tool_executor, world_model):
        from world_model.data_classes import DiskData, DiskPartition
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=100.0, total_gb=500.0, percent=20.0)],
            last_update=time.time(),
        )

        result = await tool_executor.execute("get_pc_status", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "disk" in data
        assert data["disk"][0]["mount"] == "/"
        assert data["disk"][0]["percent"] == 20.0

    @pytest.mark.asyncio
    async def test_sanitizer_allows_get_pc_status(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call("get_pc_status", {})
        assert validation["allowed"] is True


class TestSanitizerPCCommand:
    """Test sanitizer validation for run_pc_command."""

    def test_dangerous_rm_rf_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "rm -rf /home/user"}
        )
        assert validation["allowed"] is False
        assert "Dangerous" in validation["reason"]

    def test_dangerous_rm_rf_space_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "rm -rf /"}
        )
        assert validation["allowed"] is False

    def test_shutdown_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "shutdown -h now"}
        )
        assert validation["allowed"] is False

    def test_reboot_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "sudo reboot"}
        )
        assert validation["allowed"] is False

    def test_mkfs_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "mkfs.ext4 /dev/sdb1"}
        )
        assert validation["allowed"] is False

    def test_fork_bomb_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": ":() { :|:& };:"}
        )
        assert validation["allowed"] is False

    def test_safe_ls_command_allowed(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "ls -la /home"}
        )
        assert validation["allowed"] is True

    def test_safe_echo_command_allowed(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": "echo hello world"}
        )
        assert validation["allowed"] is True

    def test_empty_command_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call(
            "run_pc_command", {"command": ""}
        )
        assert validation["allowed"] is False

    @pytest.mark.asyncio
    async def test_run_pc_command_no_openclaw_url(self, tool_executor):
        """When OPENCLAW_BRIDGE_URL is not set, run_pc_command returns error."""
        tool_executor.openclaw_url = ""
        result = await tool_executor.execute("run_pc_command", {"command": "echo hello"})
        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_control_browser_unknown_action(self, tool_executor):
        """Unknown browser action returns error."""
        tool_executor.openclaw_url = "http://localhost:9000"
        result = await tool_executor.execute("control_browser", {"action": "click"})
        assert result["success"] is False
        assert "Unknown browser action" in result["error"]

    @pytest.mark.asyncio
    async def test_send_pc_notification_no_openclaw_url(self, tool_executor):
        """When OPENCLAW_BRIDGE_URL is not set, send_pc_notification returns error."""
        tool_executor.openclaw_url = ""
        result = await tool_executor.execute(
            "send_pc_notification", {"title": "Test", "body": "Message"}
        )
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_unknown_tool_blocked(self, tool_executor):
        validation = tool_executor.sanitizer.validate_tool_call("nonexistent_tool", {})
        assert validation["allowed"] is False
        assert "Unknown tool" in validation["reason"]
