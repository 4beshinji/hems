"""
Data classes for HEMS WorldModel — zone state, environment, events.
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
