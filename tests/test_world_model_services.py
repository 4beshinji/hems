"""
Tests for WorldModel service state integration — MQTT routing, LLM context, events.
"""
import time
import pytest
from world_model.data_classes import Event


class TestWorldModelServiceRouting:
    """Test hems/services/{name}/* MQTT topic routing."""

    def test_service_status_update(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail",
            "available": True,
            "unread_count": 3,
            "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        ss = world_model.services_state
        assert "gmail" in ss.services
        assert ss.services["gmail"].unread_count == 3
        assert ss.services["gmail"].available is True

    def test_service_status_update_with_error(self, world_model):
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github",
            "available": False,
            "unread_count": 0,
            "summary": "GitHub接続エラー",
            "error": "API 401",
            "last_check": time.time(),
        })
        svc = world_model.services_state.services["github"]
        assert svc.available is False
        assert svc.error == "API 401"

    def test_multiple_services(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 2, "summary": "未読: 2通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github", "unread_count": 5, "summary": "通知: 5件",
            "last_check": time.time(),
        })
        ss = world_model.services_state
        assert len(ss.services) == 2
        assert ss.services["gmail"].unread_count == 2
        assert ss.services["github"].unread_count == 5

    def test_service_status_overwrite(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読: 3通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 1, "summary": "未読: 1通",
            "last_check": time.time(),
        })
        assert world_model.services_state.services["gmail"].unread_count == 1

    def test_service_event_topic(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/event", {
            "type": "unread_increased",
            "name": "gmail",
            "prev_count": 0,
            "new_count": 3,
            "summary": "未読メール: 3通",
        })
        events = world_model.services_state.events
        assert len(events) == 1
        assert events[0].event_type == "service_unread_increased"


class TestWorldModelServiceEvents:
    """Test event generation from service state changes."""

    def test_unread_increase_generates_event(self, world_model):
        # First update: 0 unread
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 0, "summary": "未読なし",
            "last_check": time.time(),
        })
        assert len(world_model.services_state.events) == 0

        # Second update: 3 unread (increase)
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        events = world_model.services_state.events
        assert len(events) == 1
        assert events[0].event_type == "service_unread_increase"
        assert "3通" in events[0].description

    def test_unread_decrease_no_event(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 5, "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 2, "last_check": time.time(),
        })
        # First creates an event (0→5), decrease should not
        assert len(world_model.services_state.events) == 1

    def test_same_unread_no_event(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "last_check": time.time(),
        })
        # Only one event from 0→3
        assert len(world_model.services_state.events) == 1

    def test_events_ring_buffer(self, world_model):
        for i in range(25):
            world_model.services_state.add_event(
                Event(event_type="test", description=f"event_{i}")
            )
        assert len(world_model.services_state.events) == 20  # max_events


class TestWorldModelServiceLLMContext:
    """Test services section in LLM context."""

    def test_no_services_section_when_empty(self, world_model):
        # No service data → "サービス" section absent from context
        ctx = world_model.get_llm_context()
        assert "サービス" not in ctx

    def test_services_section_when_data_exists(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github", "unread_count": 0, "summary": "通知なし",
            "last_check": time.time(),
        })
        ctx = world_model.get_llm_context()
        assert "### サービス" in ctx
        assert "gmail: 未読メール: 3通" in ctx
        assert "github: 通知なし" in ctx

    def test_services_error_indicator(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "available": False, "summary": "Gmail接続エラー",
            "error": "timeout", "last_check": time.time(),
        })
        ctx = world_model.get_llm_context()
        assert "⚠" in ctx
        assert "Gmail接続エラー" in ctx


class TestWorldModelPCRouting:
    """Test hems/pc/* MQTT topic routing."""

    def test_cpu_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 45.0,
            "core_count": 8,
            "freq_mhz": 3600.0,
            "temp_c": 65.0,
        })
        pc = world_model.pc_state
        assert pc.cpu.usage_percent == 45.0
        assert pc.cpu.core_count == 8
        assert pc.cpu.temp_c == 65.0
        assert pc.cpu.last_update > 0

    def test_memory_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 12.0,
            "total_gb": 32.0,
            "percent": 37.5,
        })
        pc = world_model.pc_state
        assert pc.memory.used_gb == 12.0
        assert pc.memory.total_gb == 32.0
        assert pc.memory.percent == 37.5
        assert pc.memory.last_update > 0

    def test_gpu_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/gpu", {
            "usage_percent": 80.0,
            "vram_used_gb": 6.0,
            "vram_total_gb": 8.0,
            "temp_c": 72.0,
        })
        pc = world_model.pc_state
        assert pc.gpu.usage_percent == 80.0
        assert pc.gpu.vram_used_gb == 6.0
        assert pc.gpu.temp_c == 72.0

    def test_disk_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/disk", {
            "partitions": [
                {"mount": "/", "used_gb": 100.0, "total_gb": 500.0, "percent": 20.0},
            ]
        })
        pc = world_model.pc_state
        assert len(pc.disk.partitions) == 1
        assert pc.disk.partitions[0].mount == "/"
        assert pc.disk.partitions[0].percent == 20.0

    def test_top_processes_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/processes/top", {
            "processes": [
                {"pid": 1234, "name": "python", "cpu_percent": 25.0, "mem_mb": 512.0},
                {"pid": 5678, "name": "chrome", "cpu_percent": 10.0, "mem_mb": 1024.0},
            ]
        })
        pc = world_model.pc_state
        assert len(pc.top_processes) == 2
        assert pc.top_processes[0].name == "python"
        assert pc.top_processes[1].name == "chrome"

    def test_pc_bridge_status_connected(self, world_model):
        assert world_model.pc_state.bridge_connected is False
        world_model.update_from_mqtt("hems/pc/bridge/status", {"connected": True})
        assert world_model.pc_state.bridge_connected is True

    def test_pc_bridge_status_disconnected(self, world_model):
        world_model.update_from_mqtt("hems/pc/bridge/status", {"connected": True})
        world_model.update_from_mqtt("hems/pc/bridge/status", {"connected": False})
        assert world_model.pc_state.bridge_connected is False

    def test_cpu_threshold_event(self, world_model):
        """CPU crossing 90% generates pc_cpu_high event."""
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 95.0, "core_count": 8, "freq_mhz": 3600.0, "temp_c": 70.0,
        })
        events = world_model.pc_state.events
        assert len(events) == 1
        assert events[0].event_type == "pc_cpu_high"

    def test_cpu_below_threshold_no_event(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 50.0, "core_count": 8, "freq_mhz": 3600.0, "temp_c": 55.0,
        })
        assert len(world_model.pc_state.events) == 0

    def test_memory_threshold_event(self, world_model):
        """Memory crossing 90% generates pc_memory_high event."""
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 30.0, "total_gb": 32.0, "percent": 94.0,
        })
        events = world_model.pc_state.events
        assert len(events) == 1
        assert events[0].event_type == "pc_memory_high"

    def test_disk_high_usage_event(self, world_model):
        """Disk partition over 90% generates pc_disk_high event."""
        world_model.update_from_mqtt("hems/pc/metrics/disk", {
            "partitions": [
                {"mount": "/data", "used_gb": 950.0, "total_gb": 1000.0, "percent": 95.0},
            ]
        })
        events = world_model.pc_state.events
        assert len(events) == 1
        assert events[0].event_type == "pc_disk_high"
        assert "/data" in events[0].description


class TestWorldModelLLMContextPC:
    """Test PC section in LLM context."""

    def test_pc_section_not_shown_when_no_data(self, world_model):
        ctx = world_model.get_llm_context()
        assert "### PC" not in ctx

    def test_pc_section_shown_when_cpu_data_exists(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 50.0, "core_count": 8, "freq_mhz": 3600.0, "temp_c": 60.0,
        })
        ctx = world_model.get_llm_context()
        assert "### PC" in ctx
        assert "CPU" in ctx
        assert "50" in ctx

    def test_pc_section_shows_memory(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 16.0, "total_gb": 32.0, "percent": 50.0,
        })
        ctx = world_model.get_llm_context()
        assert "### PC" in ctx
        assert "メモリ" in ctx
        assert "16.0" in ctx

    def test_pc_bridge_disconnected_warning(self, world_model):
        # Add CPU data so PC section appears; bridge_connected defaults to False
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 30.0, "core_count": 4, "freq_mhz": 3200.0, "temp_c": 55.0,
        })
        ctx = world_model.get_llm_context()
        assert "⚠" in ctx
        assert "OpenClaw" in ctx
