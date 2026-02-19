"""PostgreSQL implementation of SensorDataRepository.

Queries the events.* schema owned by the Brain service (read-only access).
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .sensor_repository import (
    AggregatedReading,
    EventItem,
    LLMActivitySummary,
    SensorDataRepository,
    SensorReading,
    TimeSeriesQuery,
    ZoneSnapshot,
)

logger = logging.getLogger(__name__)


class PgSensorRepository(SensorDataRepository):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_latest_readings(
        self, zone: str | None = None
    ) -> list[SensorReading]:
        result = await self._session.execute(
            text("""
                SELECT DISTINCT ON (zone, data->>'channel')
                    timestamp, zone, data->>'channel' AS channel,
                    (data->>'value')::float AS value, source_device
                FROM events.raw_events
                WHERE event_type = 'sensor_reading'
                  AND timestamp > now() - interval '10 minutes'
                  AND data->>'value' IS NOT NULL
                  AND (CAST(:zone AS TEXT) IS NULL OR zone = :zone)
                ORDER BY zone, data->>'channel', timestamp DESC
            """),
            {"zone": zone},
        )
        return [
            SensorReading(
                timestamp=row[0],
                zone=row[1],
                channel=row[2],
                value=row[3],
                device_id=row[4],
            )
            for row in result.fetchall()
        ]

    async def get_time_series(
        self, query: TimeSeriesQuery
    ) -> list[AggregatedReading]:
        if query.window == "raw":
            return await self._time_series_raw(query)
        elif query.window == "1d":
            return await self._time_series_daily(query)
        else:
            return await self._time_series_hourly(query)

    async def _time_series_raw(
        self, query: TimeSeriesQuery
    ) -> list[AggregatedReading]:
        """Raw readings — capped at 1 hour range for performance."""
        end = query.end or datetime.now(timezone.utc)
        start = query.start or (end - timedelta(hours=1))
        # Enforce max 1h window
        if (end - start) > timedelta(hours=1):
            start = end - timedelta(hours=1)

        result = await self._session.execute(
            text("""
                SELECT timestamp, zone, data->>'channel' AS channel,
                       (data->>'value')::float AS value
                FROM events.raw_events
                WHERE event_type = 'sensor_reading'
                  AND data->>'value' IS NOT NULL
                  AND timestamp BETWEEN :start AND :end
                  AND (CAST(:zone AS TEXT) IS NULL OR zone = :zone)
                  AND (CAST(:channel AS TEXT) IS NULL OR data->>'channel' = :channel)
                  AND (CAST(:device_id AS TEXT) IS NULL OR source_device = :device_id)
                ORDER BY timestamp ASC
                LIMIT :limit
            """),
            {
                "start": start,
                "end": end,
                "zone": query.zone,
                "channel": query.channel,
                "device_id": query.device_id,
                "limit": query.limit,
            },
        )
        return [
            AggregatedReading(
                period_start=row[0],
                zone=row[1],
                channel=row[2],
                avg=row[3],
                max=row[3],
                min=row[3],
                count=1,
            )
            for row in result.fetchall()
        ]

    async def _time_series_hourly(
        self, query: TimeSeriesQuery
    ) -> list[AggregatedReading]:
        """Hourly aggregated data from events.hourly_aggregates JSONB."""
        end = query.end or datetime.now(timezone.utc)
        start = query.start or (end - timedelta(days=7))

        result = await self._session.execute(
            text("""
                SELECT ha.period_start, zone_key, zone_data
                FROM events.hourly_aggregates ha,
                     jsonb_each(ha.zones) AS z(zone_key, zone_data)
                WHERE ha.period_start BETWEEN :start AND :end
                  AND (CAST(:zone AS TEXT) IS NULL OR zone_key = :zone)
                ORDER BY ha.period_start ASC
                LIMIT :limit
            """),
            {
                "start": start,
                "end": end,
                "zone": query.zone,
                "limit": query.limit,
            },
        )

        readings = []
        channel_filter = query.channel
        for row in result.fetchall():
            period_start = row[0]
            zone_key = row[1]
            zone_data = row[2] if isinstance(row[2], dict) else json.loads(row[2])

            # Extract channels from keys like "avg_temperature", "max_temperature", etc.
            channels = set()
            for key in zone_data:
                m = re.match(r"^avg_(.+)$", key)
                if m:
                    channels.add(m.group(1))

            for ch in channels:
                if channel_filter and ch != channel_filter:
                    continue
                avg_val = zone_data.get(f"avg_{ch}")
                max_val = zone_data.get(f"max_{ch}")
                min_val = zone_data.get(f"min_{ch}")
                count_val = zone_data.get(f"count_{ch}", 0)
                if avg_val is not None:
                    readings.append(
                        AggregatedReading(
                            period_start=period_start,
                            zone=zone_key,
                            channel=ch,
                            avg=avg_val,
                            max=max_val if max_val is not None else avg_val,
                            min=min_val if min_val is not None else avg_val,
                            count=count_val,
                        )
                    )
        return readings

    async def _time_series_daily(
        self, query: TimeSeriesQuery
    ) -> list[AggregatedReading]:
        """Daily aggregation from hourly_aggregates via GROUP BY date."""
        end = query.end or datetime.now(timezone.utc)
        start = query.start or (end - timedelta(days=30))

        result = await self._session.execute(
            text("""
                SELECT ha.period_start, zone_key, zone_data
                FROM events.hourly_aggregates ha,
                     jsonb_each(ha.zones) AS z(zone_key, zone_data)
                WHERE ha.period_start BETWEEN :start AND :end
                  AND (CAST(:zone AS TEXT) IS NULL OR zone_key = :zone)
                ORDER BY ha.period_start ASC
            """),
            {"start": start, "end": end, "zone": query.zone},
        )

        # Collect hourly rows, then aggregate by date + zone + channel
        daily: dict[tuple[str, str, str], list[dict]] = {}
        channel_filter = query.channel
        for row in result.fetchall():
            period_start: datetime = row[0]
            day_key = period_start.strftime("%Y-%m-%d")
            zone_key = row[1]
            zone_data = row[2] if isinstance(row[2], dict) else json.loads(row[2])

            channels = set()
            for key in zone_data:
                m = re.match(r"^avg_(.+)$", key)
                if m:
                    channels.add(m.group(1))

            for ch in channels:
                if channel_filter and ch != channel_filter:
                    continue
                avg_val = zone_data.get(f"avg_{ch}")
                max_val = zone_data.get(f"max_{ch}")
                min_val = zone_data.get(f"min_{ch}")
                count_val = zone_data.get(f"count_{ch}", 0)
                if avg_val is not None:
                    bucket_key = (day_key, zone_key, ch)
                    daily.setdefault(bucket_key, []).append(
                        {
                            "avg": avg_val,
                            "max": max_val if max_val is not None else avg_val,
                            "min": min_val if min_val is not None else avg_val,
                            "count": count_val,
                        }
                    )

        readings = []
        for (day_key, zone_key, ch), entries in sorted(daily.items()):
            total_count = sum(e["count"] for e in entries)
            weighted_avg = (
                sum(e["avg"] * e["count"] for e in entries) / total_count
                if total_count > 0
                else 0
            )
            readings.append(
                AggregatedReading(
                    period_start=datetime.strptime(day_key, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    ),
                    zone=zone_key,
                    channel=ch,
                    avg=round(weighted_avg, 2),
                    max=max(e["max"] for e in entries),
                    min=min(e["min"] for e in entries),
                    count=total_count,
                )
            )
        return readings[: query.limit]

    async def get_zone_overview(self) -> list[ZoneSnapshot]:
        readings = await self.get_latest_readings()

        zones: dict[str, ZoneSnapshot] = {}
        for r in readings:
            if r.zone not in zones:
                zones[r.zone] = ZoneSnapshot(zone=r.zone, channels={})
            zones[r.zone].channels[r.channel] = r.value
            if zones[r.zone].last_update is None or r.timestamp > zones[r.zone].last_update:
                zones[r.zone].last_update = r.timestamp

        # Add event counts per zone (last 1 hour)
        result = await self._session.execute(
            text("""
                SELECT zone, COUNT(*)
                FROM events.raw_events
                WHERE event_type LIKE 'world_model_%%'
                  AND timestamp > now() - interval '1 hour'
                GROUP BY zone
            """)
        )
        for row in result.fetchall():
            zone_id = row[0]
            if zone_id in zones:
                zones[zone_id].event_count = row[1]

        return list(zones.values())

    async def get_event_feed(
        self, zone: str | None = None, limit: int = 50
    ) -> list[EventItem]:
        result = await self._session.execute(
            text("""
                SELECT timestamp, zone, event_type, source_device, data
                FROM events.raw_events
                WHERE event_type LIKE 'world_model_%%'
                  AND (CAST(:zone AS TEXT) IS NULL OR zone = :zone)
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
            {"zone": zone, "limit": limit},
        )
        return [
            EventItem(
                timestamp=row[0],
                zone=row[1],
                event_type=row[2],
                source_device=row[3],
                data=row[4] if isinstance(row[4], dict) else json.loads(row[4]),
            )
            for row in result.fetchall()
        ]

    async def get_llm_activity(self, hours: int = 24) -> LLMActivitySummary:
        result = await self._session.execute(
            text("""
                SELECT COUNT(*) AS cycles,
                       COALESCE(SUM(total_tool_calls), 0) AS tools,
                       COALESCE(AVG(cycle_duration_sec), 0) AS avg_duration
                FROM events.llm_decisions
                WHERE timestamp > now() - make_interval(hours => :hours)
            """),
            {"hours": hours},
        )
        row = result.fetchone()
        if row:
            return LLMActivitySummary(
                cycles=row[0],
                total_tool_calls=row[1],
                avg_duration_sec=round(row[2], 2),
                hours=hours,
            )
        return LLMActivitySummary(hours=hours)
