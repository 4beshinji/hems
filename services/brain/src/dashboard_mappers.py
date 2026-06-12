"""
Domain mappers for DashboardClient.

Pure functions that translate world_model state objects into the backend
payload dicts that the various ``/*/snapshot`` endpoints expect.  No HTTP
calls, no side-effects — the sole job is serialisation.

The companion transport layer (dashboard_transport.py) handles all HTTP
concerns; the public facade (dashboard_client.py) wires them together.
"""


def map_pc_payload(world_model) -> dict | None:
    """Return PC snapshot payload, or None when there is no data yet."""
    pc = world_model.pc_state
    if pc.cpu.last_update == 0 and pc.memory.last_update == 0:
        return None
    return {
        "cpu": {
            "usage_percent": pc.cpu.usage_percent,
            "core_count": pc.cpu.core_count,
            "temp_c": pc.cpu.temp_c,
        },
        "memory": {
            "used_gb": pc.memory.used_gb,
            "total_gb": pc.memory.total_gb,
            "percent": pc.memory.percent,
        },
        "gpu": {
            "usage_percent": pc.gpu.usage_percent,
            "vram_used_gb": pc.gpu.vram_used_gb,
            "vram_total_gb": pc.gpu.vram_total_gb,
            "temp_c": pc.gpu.temp_c,
        },
        "disk": [
            {"mount": p.mount, "used_gb": p.used_gb, "total_gb": p.total_gb, "percent": p.percent}
            for p in pc.disk.partitions
        ],
        "top_processes": [
            {"pid": p.pid, "name": p.name, "cpu_percent": p.cpu_percent, "mem_mb": p.mem_mb}
            for p in pc.top_processes[:10]
        ],
        "bridge_connected": pc.bridge_connected,
    }


def map_services_payload(world_model) -> dict | None:
    """Return services snapshot payload, or None when state is empty."""
    ss = world_model.services_state
    if not ss.services:
        return None
    return {
        name: {
            "name": svc.name,
            "available": svc.available,
            "unread_count": svc.unread_count,
            "summary": svc.summary,
            "last_check": svc.last_check,
            "error": svc.error,
        }
        for name, svc in ss.services.items()
    }


def map_knowledge_payload(world_model) -> dict | None:
    """Return knowledge snapshot payload, or None when bridge is disconnected."""
    ks = world_model.knowledge_state
    if not ks.bridge_connected:
        return None
    return {
        "total_notes": ks.total_notes,
        "indexed": ks.indexed,
        "bridge_connected": ks.bridge_connected,
        "recent_changes": ks.recent_changes[-5:],
    }


def map_gas_payload(world_model) -> dict | None:
    """Return GAS snapshot payload, or None when bridge is disconnected."""
    gs = world_model.gas_state
    if not gs.bridge_connected:
        return None

    calendar_events = [
        {
            "id": ev.id,
            "title": ev.title,
            "start": ev.start,
            "end": ev.end,
            "location": ev.location,
            "is_all_day": ev.is_all_day,
            "calendar_name": ev.calendar_name,
        }
        for ev in gs.calendar_events[:10]
    ]

    tasks_due = [
        {
            "title": t.title,
            "due": t.due,
            "status": t.status,
            "list_name": t.list_name,
            "is_overdue": t.is_overdue,
        }
        for t in gs.tasks
        if t.status != "completed"
    ]

    inbox = gs.gmail_labels.get("INBOX")

    return {
        "bridge_connected": True,
        "calendar_events": calendar_events,
        "calendar_event_count": len(gs.calendar_events),
        "tasks_due": tasks_due[:10],
        "overdue_count": sum(1 for t in gs.tasks if t.is_overdue),
        "gmail_inbox_unread": inbox.unread if inbox else 0,
        "free_slots": [
            {"start": s.start, "end": s.end, "duration_minutes": s.duration_minutes} for s in gs.free_slots[:5]
        ],
        "last_calendar_update": gs.last_calendar_update,
        "last_tasks_update": gs.last_tasks_update,
        "last_gmail_update": gs.last_gmail_update,
    }


def map_biometric_payload(world_model) -> dict | None:
    """Return biometric snapshot payload, or None when there is no data."""
    bio = world_model.biometric_state
    if not bio.bridge_connected and bio.last_update == 0:
        return None

    payload: dict = {
        "bridge_connected": bio.bridge_connected,
        "provider": bio.provider,
    }
    if bio.heart_rate.bpm is not None:
        payload["heart_rate"] = {
            "bpm": bio.heart_rate.bpm,
            "zone": bio.heart_rate.zone,
            "resting_bpm": bio.heart_rate.resting_bpm,
        }
    if bio.spo2.percent is not None:
        payload["spo2"] = {"percent": bio.spo2.percent}
    if bio.sleep.last_update > 0:
        payload["sleep"] = {
            "stage": bio.sleep.stage,
            "duration_minutes": bio.sleep.duration_minutes,
            "deep_minutes": bio.sleep.deep_minutes,
            "rem_minutes": bio.sleep.rem_minutes,
            "light_minutes": bio.sleep.light_minutes,
            "quality_score": bio.sleep.quality_score,
        }
    if bio.activity.last_update > 0:
        payload["activity"] = {
            "steps": bio.activity.steps,
            "steps_goal": bio.activity.steps_goal,
            "calories": bio.activity.calories,
            "active_minutes": bio.activity.active_minutes,
            "level": bio.activity.level,
        }
    if bio.stress.last_update > 0:
        payload["stress"] = {
            "level": bio.stress.level,
            "category": bio.stress.category,
        }
    if bio.fatigue.last_update > 0:
        payload["fatigue"] = {
            "score": bio.fatigue.score,
            "factors": bio.fatigue.factors,
        }
    return payload


def map_perception_zones(world_model) -> dict | None:
    """Return perception zones dict, or None when no zone has signal."""
    zones_data = {}
    for zone_id, zone in world_model.zones.items():
        occ = zone.occupancy
        has_signal = (
            occ.last_update > 0 or occ.inferred_occupied or occ.presence_state is not None or occ.last_motion_ts > 0
        )
        if has_signal:
            zones_data[zone_id] = {
                "person_count": occ.count,
                "activity_level": occ.activity_level,
                "activity_class": occ.activity_class,
                "posture": occ.posture,
                "posture_status": occ.posture_status,
                "posture_duration_sec": occ.posture_duration_sec,
                "last_update": occ.last_update,
                # Multi-source presence inference (reconcile_presence)
                "inferred_occupied": occ.inferred_occupied,
                "inference_source": occ.inference_source,
                "inference_sources": list(occ.inference_sources),
                "presence_state": occ.presence_state,
                "last_motion_ts": occ.last_motion_ts,
                "motion_event_count_5min": occ.motion_event_count_5min,
                # VLM scene data
                "scene_description": occ.scene_description,
                "scene_objects": list(occ.scene_objects),
                "scene_type": occ.scene_type,
                "scene_anomalies": list(occ.scene_anomalies),
                "vlm_last_update": occ.vlm_last_update,
                "vlm_history": [
                    {
                        "timestamp": s.timestamp,
                        "description": s.description[:200],
                        "objects": s.objects[:8],
                        "scene_type": s.scene_type,
                        "anomalies": s.anomalies[:3],
                        "tier": s.tier,
                    }
                    for s in list(occ.vlm_history)[-5:]
                ],
            }
    return zones_data if zones_data else None


def map_home_payload(world_model) -> dict | None:
    """Return home snapshot payload, or None when bridge is disconnected."""
    hd = world_model.home_devices
    if not hd.bridge_connected:
        return None

    energy_sensors = {}
    for eid, s in hd.sensors.items():
        if s.device_class in ("power", "energy"):
            energy_sensors[eid] = {
                "value": s.value,
                "unit": s.unit or ("W" if s.device_class == "power" else "kWh"),
                "device_class": s.device_class,
            }

    return {
        "bridge_connected": True,
        "lights": {eid: {"on": lt.on, "brightness": lt.brightness} for eid, lt in hd.lights.items()},
        "climates": {
            eid: {"mode": c.mode, "target_temp": c.target_temp, "current_temp": c.current_temp}
            for eid, c in hd.climates.items()
        },
        "covers": {eid: {"position": c.position, "is_open": c.is_open} for eid, c in hd.covers.items()},
        "switches": hd.switches,
        "energy_sensors": energy_sensors,
    }


def map_home_timeseries_points(world_model) -> list[dict]:
    """Return timeseries points for power readings (home/energy sensors)."""
    hd = world_model.home_devices
    points = []
    for eid, s in hd.sensors.items():
        if s.device_class == "power" and s.value > 0:
            name = eid.split(".")[-1] if "." in eid else eid
            points.append({"metric": f"power.{name}", "value": s.value})
    return points


def map_news_payload(world_model) -> dict | None:
    """Return news snapshot payload, or None when state has no data."""
    ns = world_model.news_state
    if ns.daily_timestamp == 0 and not ns.urgent_articles and not ns.bridge_connected:
        return None
    return {
        "daily_summary": ns.daily_summary,
        "daily_chunks": ns.daily_chunks,
        "daily_timestamp": ns.daily_timestamp,
        "urgent_articles": ns.urgent_articles[-10:],
        "bridge_connected": ns.bridge_connected,
    }


def map_weather_payload(world_model) -> dict | None:
    """Return weather snapshot payload, or None when there is no data."""
    w = world_model.weather
    if w.last_update == 0 and w.last_alerts_update == 0:
        return None
    return {
        "current": {
            "condition": w.condition,
            "temperature": w.temperature,
            "humidity": w.humidity,
            "wind_speed": w.wind_speed,
            "last_update": w.last_update,
        },
        "forecast": [
            {
                "datetime": f.datetime,
                "condition": f.condition,
                "temperature": f.temperature,
                "precipitation_probability": f.precipitation_probability,
                "wind_speed": f.wind_speed,
            }
            for f in w.forecast[:24]
        ],
        "alerts": [
            {
                "title": a.title,
                "severity": a.severity,
                "description": a.description,
                "area": a.area,
                "issued_at": a.issued_at,
                "expires_at": a.expires_at,
            }
            for a in w.alerts
        ],
        "last_alerts_update": w.last_alerts_update,
    }


def map_zone_rows(world_model) -> list[dict]:
    """Return list of zone dicts for the zone snapshot endpoint.

    Returns empty list when no zones are present.
    """
    zones = []
    for zone_id, zone in world_model.zones.items():
        env = zone.environment
        zones.append(
            {
                "zone_id": zone_id,
                "environment": {
                    "temperature": env.temperature,
                    "humidity": env.humidity,
                    "co2": env.co2,
                    "pressure": env.pressure,
                    "light": env.light,
                    "voc": env.voc,
                    "pm25": env.pm25,
                    "soil_moisture": env.soil_moisture,
                    "last_update": env.last_update,
                },
                "occupancy": {
                    "count": zone.occupancy.count if zone.occupancy else 0,
                    "last_update": zone.occupancy.last_update if zone.occupancy else None,
                },
                "events": [
                    {
                        "type": e.event_type,
                        "description": e.description,
                        "severity": e.severity,
                        "timestamp": e.timestamp,
                    }
                    for e in zone.events[-5:]
                ],
            }
        )
    return zones


def map_zone_timeseries_points(zones: list[dict]) -> list[dict]:
    """Return timeseries ingest points for zone environment metrics."""
    points = []
    for z in zones:
        zid = z["zone_id"]
        env = z["environment"]
        for metric in ("temperature", "humidity", "co2"):
            val = env.get(metric)
            if val is not None:
                points.append({"metric": metric, "zone": zid, "value": val})
    return points


def map_device_heartbeat_payload(observation) -> dict:
    """Serialise a DeviceObservation into the /devices/heartbeat payload."""
    return {
        "device_id": observation.device_id,
        "vendor": observation.vendor,
        "vendor_ref": observation.vendor_ref,
        "kind": observation.kind,
        "device_class": observation.device_class,
        "capabilities": observation.capabilities or [],
        "channels": observation.channels or [],
        "units": observation.units or {},
        "zone": observation.zone,
        "display_name": observation.display_name,
        "description": observation.description,
        "model_id": observation.model_id,
        "manufacturer": observation.manufacturer,
        "last_state": observation.last_state or {},
        "last_value": observation.last_value or {},
        "battery_pct": observation.battery_pct,
        "link_quality": observation.link_quality,
        "last_seen_reported": observation.last_seen_ts,
    }
