import json
import os
from typing import Any

from loguru import logger


class WorldToolHandlers:
    async def _handle_device_command(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send command to edge device via MCPBridge with adaptive timeout."""
        agent_id = args.get("agent_id", "")
        tool_name = args.get("tool_name", "")

        inner_args = args.get("arguments", {})
        if isinstance(inner_args, str):
            try:
                inner_args = json.loads(inner_args)
            except (json.JSONDecodeError, TypeError):
                inner_args = {}

        timeout = None
        if self.device_registry:
            timeout = self.device_registry.get_timeout_for_device(agent_id)

        result = await self.mcp.call_tool(agent_id, tool_name, inner_args, timeout=timeout)
        if isinstance(result, dict) and result.get("status") == "queued":
            target = result.get("target", agent_id)
            return {
                "success": True,
                "result": f"コマンドをキューに追加: {target}/{tool_name} (デバイスの次回ウェイク時に配送)",
            }

        if result is not None:
            return {
                "success": True,
                "result": f"デバイスコマンド実行完了: {agent_id}/{tool_name} -> {json.dumps(result, ensure_ascii=False)}",
            }
        return {"success": False, "error": f"MCP call to {agent_id}/{tool_name} failed or timed out"}

    async def _handle_get_zone_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get detailed zone status from WorldModel."""
        zone_id = args.get("zone_id", "")
        zone = self.world_model.zones.get(zone_id)
        if not zone:
            return {"success": False, "error": f"Zone '{zone_id}' not found"}

        env = zone.environment
        status = {
            "zone_id": zone_id,
            "temperature": env.temperature,
            "humidity": env.humidity,
            "co2": env.co2,
            "occupancy_count": zone.occupancy.count if zone.occupancy else 0,
            "recent_events": [
                {"type": e.event_type, "description": e.description, "severity": e.severity} for e in zone.events[-5:]
            ],
        }
        return {"success": True, "result": json.dumps(status, ensure_ascii=False)}

    async def _handle_get_sensor_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return a sensor history window from the event store."""
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import text as _sql

        from event_store.database import get_engine

        zone = str(args.get("zone", "")).strip()
        channel = str(args.get("channel", "")).strip()
        hours = int(args.get("hours", 6) or 6)
        max_points = int(args.get("max_points", 200) or 200)
        force_aggregate = bool(args.get("aggregate", False))
        hours = max(1, min(hours, 720))
        max_points = max(1, min(max_points, 1000))

        if not zone or not channel:
            return {"success": False, "error": "zone and channel are required"}

        engine = get_engine()
        if engine is None:
            return {
                "success": True,
                "result": json.dumps(
                    {"zone": zone, "channel": channel, "points": [], "note": "event store disabled"},
                    ensure_ascii=False,
                ),
            }

        is_postgres = "postgresql" in os.getenv("DATABASE_URL", "")
        schema = "events." if is_postgres else ""
        since = datetime.now(UTC) - timedelta(hours=hours)
        use_aggregate = force_aggregate or hours > 24

        try:
            async with engine.begin() as conn:
                if use_aggregate:
                    rows = (
                        await conn.execute(
                            _sql(
                                f"""
                                SELECT period_start, zones FROM {schema}hourly_aggregates
                                WHERE period_start >= :since
                                ORDER BY period_start ASC
                                LIMIT :lim
                                """
                            ),
                            {"since": since, "lim": max_points},
                        )
                    ).fetchall()

                    points: list[dict] = []
                    for ts, raw in rows:
                        try:
                            zones_data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                        except Exception:
                            continue
                        zone_data = zones_data.get(zone, {})
                        ch_data = zone_data.get(channel) if isinstance(zone_data, dict) else None
                        if ch_data is None:
                            continue
                        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                        if isinstance(ch_data, dict):
                            points.append(
                                {
                                    "t": ts_str,
                                    "min": ch_data.get("min"),
                                    "max": ch_data.get("max"),
                                    "avg": ch_data.get("avg"),
                                    "v": ch_data.get("avg"),
                                }
                            )
                        else:
                            points.append({"t": ts_str, "v": ch_data})

                    values = [p["v"] for p in points if isinstance(p.get("v"), (int, float))]
                    summary = None
                    if values:
                        summary = {
                            "count": len(values),
                            "min": min(values),
                            "max": max(values),
                            "avg": sum(values) / len(values),
                            "last": values[-1],
                        }
                    return {
                        "success": True,
                        "result": json.dumps(
                            {
                                "zone": zone,
                                "channel": channel,
                                "hours": hours,
                                "resolution": "hourly_aggregate",
                                "points": points,
                                "summary": summary,
                            },
                            ensure_ascii=False,
                        ),
                    }

                rows = (
                    await conn.execute(
                        _sql(
                            f"""
                            SELECT timestamp, data FROM {schema}raw_events
                            WHERE zone = :zone
                              AND event_type = 'sensor_reading'
                              AND timestamp >= :since
                            ORDER BY timestamp DESC
                            LIMIT :lim
                            """
                        ),
                        {"zone": zone, "since": since, "lim": max_points * 4},
                    )
                ).fetchall()
        except Exception as e:
            logger.warning(f"get_sensor_history query failed: {e}")
            return {"success": False, "error": f"query failed: {e}"}

        points: list[dict] = []
        for ts, raw in rows:
            try:
                data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            except Exception:
                continue
            if data.get("channel") != channel:
                continue
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            points.append({"t": ts_str, "v": data.get("value")})
            if len(points) >= max_points:
                break

        points.reverse()
        values = [p["v"] for p in points if isinstance(p["v"], (int, float))]
        summary = None
        if values:
            summary = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "last": values[-1],
            }

        result = {
            "zone": zone,
            "channel": channel,
            "hours": hours,
            "resolution": "raw",
            "points": points,
            "summary": summary,
        }
        return {"success": True, "result": json.dumps(result, ensure_ascii=False)}

    async def _handle_get_device_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get device network status from DeviceRegistry."""
        if not self.device_registry:
            return {"success": False, "error": "DeviceRegistry が初期化されていません"}

        zone_id = args.get("zone_id")
        tree = self.device_registry.get_device_tree(zone_id=zone_id)
        return {"success": True, "result": tree}

    def _handle_set_guest_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        enabled = args.get("enabled", False)
        duration = args.get("duration_hours", 4)
        self.world_model.set_guest_mode(enabled, duration)
        return {"success": True, "result": f"ゲストモード{'ON' if enabled else 'OFF'} ({duration}時間)"}

    def _handle_get_weather(self, args: dict[str, Any]) -> dict[str, Any]:
        w = self.world_model.weather
        if w.last_update == 0:
            return {"success": True, "result": "天気データなし"}
        forecast = [
            {
                "datetime": f.datetime,
                "condition": f.condition,
                "temperature": f.temperature,
                "precipitation": f.precipitation_probability,
            }
            for f in w.forecast[:6]
        ]
        result = {
            "condition": w.condition,
            "temperature": w.temperature,
            "humidity": w.humidity,
            "wind_speed": w.wind_speed,
            "forecast": forecast,
        }
        return {"success": True, "result": json.dumps(result, ensure_ascii=False)}
