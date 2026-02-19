"""
Tests for PCState and related dataclasses.
"""
import time
from world_model.data_classes import (
    CPUData, MemoryData, GPUData, DiskPartition, DiskData,
    ProcessInfo, PCState, Event,
)


class TestCPUData:
    def test_defaults(self):
        cpu = CPUData()
        assert cpu.usage_percent == 0
        assert cpu.core_count == 0
        assert cpu.freq_mhz == 0
        assert cpu.temp_c == 0
        assert cpu.last_update == 0

    def test_custom_values(self):
        cpu = CPUData(usage_percent=45.3, core_count=16, temp_c=62.0, last_update=1.0)
        assert cpu.usage_percent == 45.3
        assert cpu.core_count == 16
        assert cpu.temp_c == 62.0


class TestMemoryData:
    def test_defaults(self):
        mem = MemoryData()
        assert mem.used_gb == 0
        assert mem.total_gb == 0
        assert mem.percent == 0

    def test_custom_values(self):
        mem = MemoryData(used_gb=12.5, total_gb=32.0, percent=39.1)
        assert mem.used_gb == 12.5
        assert mem.total_gb == 32.0
        assert mem.percent == 39.1


class TestGPUData:
    def test_defaults(self):
        gpu = GPUData()
        assert gpu.usage_percent == 0
        assert gpu.vram_used_gb == 0
        assert gpu.vram_total_gb == 0
        assert gpu.temp_c == 0

    def test_custom_values(self):
        gpu = GPUData(usage_percent=80.0, vram_used_gb=6.0, vram_total_gb=16.0, temp_c=75.0)
        assert gpu.usage_percent == 80.0
        assert gpu.vram_total_gb == 16.0


class TestDiskData:
    def test_empty_partitions(self):
        disk = DiskData()
        assert disk.partitions == []
        assert disk.last_update == 0

    def test_with_partitions(self):
        p = DiskPartition(mount="/", used_gb=100.0, total_gb=500.0, percent=20.0)
        disk = DiskData(partitions=[p], last_update=1.0)
        assert len(disk.partitions) == 1
        assert disk.partitions[0].mount == "/"
        assert disk.partitions[0].percent == 20.0


class TestProcessInfo:
    def test_defaults(self):
        p = ProcessInfo()
        assert p.pid == 0
        assert p.name == ""
        assert p.cpu_percent == 0
        assert p.mem_mb == 0

    def test_custom(self):
        p = ProcessInfo(pid=1234, name="python3", cpu_percent=15.5, mem_mb=256.0)
        assert p.pid == 1234
        assert p.name == "python3"


class TestPCState:
    def test_defaults(self):
        pc = PCState()
        assert pc.cpu.usage_percent == 0
        assert pc.memory.total_gb == 0
        assert pc.gpu.temp_c == 0
        assert pc.disk.partitions == []
        assert pc.top_processes == []
        assert pc.bridge_connected is False
        assert pc.events == []

    def test_add_event(self):
        pc = PCState()
        ev = Event(event_type="test", description="Test event", severity=1)
        pc.add_event(ev)
        assert len(pc.events) == 1
        assert pc.events[0].event_type == "test"

    def test_event_ring_buffer(self):
        pc = PCState(max_events=5)
        for i in range(10):
            pc.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(pc.events) == 5
        assert pc.events[0].event_type == "ev_5"
        assert pc.events[-1].event_type == "ev_9"

    def test_independent_instances(self):
        """Ensure dataclass fields don't share mutable defaults."""
        pc1 = PCState()
        pc2 = PCState()
        pc1.add_event(Event(event_type="only_in_pc1"))
        assert len(pc1.events) == 1
        assert len(pc2.events) == 0
