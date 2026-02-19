"""
Tests for WorldModel PC state integration (MQTT routing + thresholds).
"""
import time
import pytest


class TestWorldModelPCRouting:
    """Test hems/pc/* MQTT topic routing into PCState."""

    def test_cpu_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 42.5,
            "core_count": 8,
            "load_1m": 3.4,
        })
        assert world_model.pc_state.cpu.usage_percent == 42.5
        assert world_model.pc_state.cpu.core_count == 8
        assert world_model.pc_state.cpu.last_update > 0

    def test_memory_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 12.5,
            "total_gb": 32.0,
            "percent": 39.1,
        })
        assert world_model.pc_state.memory.used_gb == 12.5
        assert world_model.pc_state.memory.total_gb == 32.0
        assert world_model.pc_state.memory.percent == 39.1

    def test_gpu_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/gpu", {
            "usage_percent": 80.0,
            "vram_used_gb": 6.0,
            "vram_total_gb": 16.0,
            "temp_c": 72.0,
        })
        gpu = world_model.pc_state.gpu
        assert gpu.usage_percent == 80.0
        assert gpu.vram_used_gb == 6.0
        assert gpu.temp_c == 72.0

    def test_disk_metrics_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/disk", {
            "partitions": [
                {"mount": "/", "used_gb": 100, "total_gb": 500, "percent": 20.0},
                {"mount": "/home", "used_gb": 400, "total_gb": 1000, "percent": 40.0},
            ]
        })
        disk = world_model.pc_state.disk
        assert len(disk.partitions) == 2
        assert disk.partitions[0].mount == "/"
        assert disk.partitions[1].percent == 40.0

    def test_temperature_update(self, world_model):
        # Set initial CPU data so temp has somewhere to go
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 10, "core_count": 4,
        })
        world_model.update_from_mqtt("hems/pc/metrics/temperature", {
            "cpu_temp_c": 55.0,
            "gpu_temp_c": 68.0,
        })
        assert world_model.pc_state.cpu.temp_c == 55.0
        assert world_model.pc_state.gpu.temp_c == 68.0

    def test_process_list_update(self, world_model):
        world_model.update_from_mqtt("hems/pc/processes/top", {
            "processes": [
                {"pid": 1, "name": "systemd", "cpu_percent": 0.1, "mem_mb": 10},
                {"pid": 100, "name": "python3", "cpu_percent": 25.0, "mem_mb": 512},
            ]
        })
        procs = world_model.pc_state.top_processes
        assert len(procs) == 2
        assert procs[1].name == "python3"
        assert procs[1].cpu_percent == 25.0

    def test_bridge_status_connected(self, world_model):
        world_model.update_from_mqtt("hems/pc/bridge/status", {
            "connected": True, "uptime_s": 120,
        })
        assert world_model.pc_state.bridge_connected is True

    def test_bridge_status_disconnected(self, world_model):
        world_model.update_from_mqtt("hems/pc/bridge/status", {
            "connected": False,
        })
        assert world_model.pc_state.bridge_connected is False

    def test_events_from_bridge(self, world_model):
        world_model.update_from_mqtt("hems/pc/events/cpu_high", {
            "usage_percent": 95,
        })
        events = world_model.pc_state.events
        assert len(events) == 1
        assert events[0].event_type == "pc_cpu_high"

    def test_unknown_pc_topic_ignored(self, world_model):
        """Non-matching subtopics shouldn't crash."""
        world_model.update_from_mqtt("hems/pc/unknown/foo", {"bar": 1})
        # Just verify no exception was raised

    def test_empty_path_parts_ignored(self, world_model):
        world_model.update_from_mqtt("hems/pc", {})
        # Should not crash


class TestWorldModelPCThresholds:
    """Test threshold event generation from PC metrics."""

    def test_cpu_high_event(self, world_model):
        # First update: normal
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 50, "core_count": 8,
        })
        assert len(world_model.pc_state.events) == 0

        # Second update: cross threshold
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 95, "core_count": 8,
        })
        events = [e for e in world_model.pc_state.events if e.event_type == "pc_cpu_high"]
        assert len(events) == 1
        assert "95" in events[0].description

    def test_cpu_high_no_duplicate_while_sustained(self, world_model):
        """Threshold event only fires on crossing, not repeatedly."""
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 50, "core_count": 8,
        })
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 95, "core_count": 8,
        })
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 96, "core_count": 8,
        })
        events = [e for e in world_model.pc_state.events if e.event_type == "pc_cpu_high"]
        assert len(events) == 1  # Only one crossing event

    def test_memory_high_event(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 10, "total_gb": 32, "percent": 31,
        })
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 30, "total_gb": 32, "percent": 93.75,
        })
        events = [e for e in world_model.pc_state.events if e.event_type == "pc_memory_high"]
        assert len(events) == 1

    def test_gpu_hot_event(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/gpu", {
            "usage_percent": 80, "vram_used_gb": 6, "vram_total_gb": 16, "temp_c": 70,
        })
        world_model.update_from_mqtt("hems/pc/metrics/gpu", {
            "usage_percent": 90, "vram_used_gb": 8, "vram_total_gb": 16, "temp_c": 90,
        })
        events = [e for e in world_model.pc_state.events if e.event_type == "pc_gpu_hot"]
        assert len(events) == 1
        assert events[0].severity == 2  # critical

    def test_disk_high_event_from_partition(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/disk", {
            "partitions": [
                {"mount": "/", "used_gb": 480, "total_gb": 500, "percent": 96.0},
            ]
        })
        events = [e for e in world_model.pc_state.events if e.event_type == "pc_disk_high"]
        assert len(events) == 1
        assert "/" in events[0].description

    def test_no_event_below_threshold(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 50, "core_count": 8,
        })
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 10, "total_gb": 32, "percent": 31,
        })
        world_model.update_from_mqtt("hems/pc/metrics/gpu", {
            "usage_percent": 50, "vram_used_gb": 4, "vram_total_gb": 16, "temp_c": 60,
        })
        assert len(world_model.pc_state.events) == 0


class TestWorldModelLLMContext:
    """Test that PC data appears in LLM context."""

    def test_no_pc_in_context_when_no_data(self, world_model):
        """PC section should not appear when no PC data exists."""
        ctx = world_model.get_llm_context()
        assert "PC" not in ctx

    def test_pc_in_context_when_data_exists(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 42, "core_count": 8,
        })
        world_model.update_from_mqtt("hems/pc/metrics/memory", {
            "used_gb": 12, "total_gb": 32, "percent": 37.5,
        })
        ctx = world_model.get_llm_context()
        assert "### PC" in ctx
        assert "CPU: 42%" in ctx
        assert "メモリ: 12.0/32.0GB" in ctx

    def test_pc_bridge_disconnected_warning(self, world_model):
        world_model.update_from_mqtt("hems/pc/metrics/cpu", {
            "usage_percent": 10, "core_count": 4,
        })
        world_model.update_from_mqtt("hems/pc/bridge/status", {
            "connected": False,
        })
        ctx = world_model.get_llm_context()
        assert "切断中" in ctx

    def test_empty_context_when_no_zones_no_pc(self, world_model):
        assert world_model.get_llm_context() == ""
