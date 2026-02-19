"""
Tests for DashboardClient.push_pc_snapshot.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from world_model.data_classes import (
    PCState, CPUData, MemoryData, GPUData, DiskData, DiskPartition, ProcessInfo,
)


class TestPushPCSnapshot:

    def _make_client(self, mock_session):
        from dashboard_client import DashboardClient
        client = DashboardClient(session=mock_session)
        return client

    @pytest.mark.asyncio
    async def test_skips_when_no_pc_data(self, world_model, mock_session):
        client = self._make_client(mock_session)
        await client.push_pc_snapshot(world_model)
        # Session.post should NOT be called for PC when no data
        for call in mock_session.post.call_args_list:
            assert "/pc/snapshot" not in str(call)

    @pytest.mark.asyncio
    async def test_pushes_when_data_exists(self, world_model, mock_session):
        client = self._make_client(mock_session)
        world_model.pc_state.cpu = CPUData(usage_percent=50, core_count=8, temp_c=55, last_update=1.0)
        world_model.pc_state.memory = MemoryData(used_gb=12, total_gb=32, percent=37.5, last_update=1.0)

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_pc_snapshot(world_model)
        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert "/pc/snapshot" in call_url

    @pytest.mark.asyncio
    async def test_payload_contains_all_sections(self, world_model, mock_session):
        client = self._make_client(mock_session)
        world_model.pc_state.cpu = CPUData(usage_percent=50, core_count=8, last_update=1.0)
        world_model.pc_state.memory = MemoryData(used_gb=12, total_gb=32, percent=37.5, last_update=1.0)
        world_model.pc_state.gpu = GPUData(usage_percent=80, temp_c=70, last_update=1.0)
        world_model.pc_state.disk = DiskData(
            partitions=[DiskPartition(mount="/", used_gb=100, total_gb=500, percent=20)],
        )
        world_model.pc_state.top_processes = [
            ProcessInfo(pid=1, name="test", cpu_percent=5, mem_mb=100),
        ]

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_pc_snapshot(world_model)
        call_kwargs = mock_session.post.call_args[1]
        payload = call_kwargs["json"]

        assert "cpu" in payload
        assert payload["cpu"]["usage_percent"] == 50
        assert "memory" in payload
        assert "gpu" in payload
        assert "disk" in payload
        assert len(payload["disk"]) == 1
        assert "top_processes" in payload
        assert len(payload["top_processes"]) == 1
        assert "bridge_connected" in payload
