"""
Data classes for HEMS WorldModel — zone state, environment, events, PC state.
"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class EnvironmentData:
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    co2: Optional[float] = None
    pressure: Optional[float] = None
    light: Optional[float] = None
    voc: Optional[float] = None
    last_update: float = 0


@dataclass
class OccupancyData:
    count: int = 0
    last_update: float = 0


@dataclass
class DeviceState:
    device_id: str = ""
    state: dict = field(default_factory=dict)
    last_update: float = 0


@dataclass
class Event:
    event_type: str = ""
    description: str = ""
    severity: int = 0  # 0=info, 1=warning, 2=critical
    timestamp: float = field(default_factory=time.time)
    zone: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class ZoneState:
    zone_id: str = ""
    environment: EnvironmentData = field(default_factory=EnvironmentData)
    occupancy: OccupancyData = field(default_factory=OccupancyData)
    devices: dict[str, DeviceState] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    max_events: int = 50

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- Service Status (Service Monitor) ---

@dataclass
class ServiceStatusData:
    name: str = ""
    available: bool = True
    unread_count: int = 0
    summary: str = ""
    details: dict = field(default_factory=dict)
    last_check: float = 0
    error: str | None = None


@dataclass
class ServicesState:
    services: dict[str, ServiceStatusData] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    max_events: int = 20

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]


# --- PC State (OpenClaw integration) ---

@dataclass
class CPUData:
    usage_percent: float = 0
    core_count: int = 0
    freq_mhz: float = 0
    temp_c: float = 0
    last_update: float = 0


@dataclass
class MemoryData:
    used_gb: float = 0
    total_gb: float = 0
    percent: float = 0
    last_update: float = 0


@dataclass
class GPUData:
    usage_percent: float = 0
    vram_used_gb: float = 0
    vram_total_gb: float = 0
    temp_c: float = 0
    last_update: float = 0


@dataclass
class DiskPartition:
    mount: str = ""
    used_gb: float = 0
    total_gb: float = 0
    percent: float = 0


@dataclass
class DiskData:
    partitions: list[DiskPartition] = field(default_factory=list)
    last_update: float = 0


@dataclass
class ProcessInfo:
    pid: int = 0
    name: str = ""
    cpu_percent: float = 0
    mem_mb: float = 0


@dataclass
class PCState:
    cpu: CPUData = field(default_factory=CPUData)
    memory: MemoryData = field(default_factory=MemoryData)
    gpu: GPUData = field(default_factory=GPUData)
    disk: DiskData = field(default_factory=DiskData)
    top_processes: list[ProcessInfo] = field(default_factory=list)
    bridge_connected: bool = False
    events: list[Event] = field(default_factory=list)
    max_events: int = 50

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
