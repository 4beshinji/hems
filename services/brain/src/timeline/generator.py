"""TimelineGenerator: orchestrates routine + calendar + travel + tasks → ScheduledBlock list."""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from loguru import logger

from .models import TimelineSlot, CandidateTask, FreeWindow
from .free_window import compute_free_windows
from .edf_scheduler import schedule_edf
from .travel_config import load_travel_matrix, lookup_travel_minutes

TZ_NAME = os.getenv("TZ", "Asia/Tokyo")
try:
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("Asia/Tokyo")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
HEMS_HOME_LOCATION_KEYWORDS = ("home", "自宅", "家", "")

# Default routine anchors when schedule_learner has no data
DEFAULT_WAKE_HOUR = 7.0
DEFAULT_DEPARTURE_HOUR = 8.5
DEFAULT_ARRIVAL_HOUR = 18.5
DEFAULT_SLEEP_HOUR = 24.0
ROUTINE_SLEEP_DURATION_HOURS = 7.0


def _hour_float_to_dt(day: datetime, hour_float: float) -> datetime:
    h = int(hour_float)
    m = int(round((hour_float - h) * 60))
    if h >= 24:
        day = day + timedelta(days=h // 24)
        h = h % 24
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def _is_home_location(location: str | None) -> bool:
    if not location:
        return True
    loc = location.lower().strip()
    if not loc:
        return True
    return any(kw and kw in loc for kw in ("home", "自宅", "家"))


class TimelineGenerator:
    """Build a day's timeline slots from routines + calendar + tasks. Stateless per-call."""

    def __init__(self, world_model, schedule_learner, session, auth_headers: dict):
        self.world_model = world_model
        self.schedule_learner = schedule_learner
        self.session = session
        self.auth_headers = auth_headers or {}
        self.travel_matrix = load_travel_matrix()

    def _day_bounds(self) -> tuple[datetime, datetime, str]:
        now = datetime.now(LOCAL_TZ)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(hours=30)  # extend to tomorrow 06:00
        date_str = day_start.strftime("%Y-%m-%d")
        return day_start, day_end, date_str

    def _routine_slots(self, day_start: datetime) -> list[TimelineSlot]:
        """Build wake / commute_out / commute_in / sleep slots from schedule_learner."""
        slots: list[TimelineSlot] = []
        sl = self.schedule_learner

        weekday = day_start.weekday()

        def _median(hist_dict: dict, default: float) -> float:
            if not sl:
                return default
            entries = hist_dict.get(weekday, [])
            if len(entries) >= 2:
                import statistics as _st
                return _st.median(entries)
            return default

        wake_hour = _median(getattr(sl, "_wake_history", {}) if sl else {}, DEFAULT_WAKE_HOUR)
        dep_hour = _median(
            getattr(sl, "_departure_history", {}) if sl else {}, DEFAULT_DEPARTURE_HOUR
        )
        arr_hour = _median(
            getattr(sl, "_arrival_history", {}) if sl else {}, DEFAULT_ARRIVAL_HOUR
        )

        wake_dt = _hour_float_to_dt(day_start, wake_hour)
        slots.append(
            TimelineSlot(
                start=wake_dt,
                end=wake_dt + timedelta(minutes=30),
                kind="routine_wake",
                title="起床",
                is_locked=True,
            )
        )

        if dep_hour > wake_hour + 0.5 and dep_hour < arr_hour:
            dep_dt = _hour_float_to_dt(day_start, dep_hour)
            travel_out = lookup_travel_minutes(self.travel_matrix, "home", "office")
            slots.append(
                TimelineSlot(
                    start=dep_dt,
                    end=dep_dt + timedelta(minutes=travel_out),
                    kind="commute_out",
                    title=f"出発→外出 ({travel_out}分)",
                    is_locked=True,
                    travel_buffer_minutes=travel_out,
                )
            )

            arr_dt = _hour_float_to_dt(day_start, arr_hour)
            travel_in = lookup_travel_minutes(self.travel_matrix, "office", "home")
            slots.append(
                TimelineSlot(
                    start=arr_dt - timedelta(minutes=travel_in),
                    end=arr_dt,
                    kind="commute_in",
                    title=f"帰宅移動 ({travel_in}分)",
                    is_locked=True,
                    travel_buffer_minutes=travel_in,
                )
            )

        sleep_start_hour = arr_hour + 5.5 if arr_hour < 22 else DEFAULT_SLEEP_HOUR
        sleep_start_hour = min(sleep_start_hour, DEFAULT_SLEEP_HOUR + 1.5)
        sleep_start = _hour_float_to_dt(day_start, sleep_start_hour)
        tomorrow = day_start + timedelta(days=1)
        next_wake_hour = wake_hour
        sleep_end = _hour_float_to_dt(tomorrow, next_wake_hour)
        if sleep_end <= sleep_start:
            sleep_end = sleep_start + timedelta(hours=ROUTINE_SLEEP_DURATION_HOURS)
        slots.append(
            TimelineSlot(
                start=sleep_start,
                end=sleep_end,
                kind="sleep",
                title="睡眠",
                is_locked=True,
            )
        )

        return slots

    def _calendar_slots(self, day_start: datetime, day_end: datetime) -> list[TimelineSlot]:
        """Convert world_model calendar events into slots, inject travel buffers."""
        slots: list[TimelineSlot] = []
        gas_state = getattr(self.world_model, "gas_state", None)
        if not gas_state:
            return slots
        events = getattr(gas_state, "calendar_events", []) or []

        start_ts_bound = day_start.timestamp()
        end_ts_bound = day_end.timestamp()

        for ev in events:
            start_ts = float(getattr(ev, "start_ts", 0) or 0)
            end_ts = float(getattr(ev, "end_ts", 0) or 0)
            if start_ts <= 0 or end_ts <= 0:
                continue
            if end_ts <= start_ts_bound or start_ts >= end_ts_bound:
                continue
            if getattr(ev, "is_all_day", False):
                continue

            ev_start = datetime.fromtimestamp(start_ts, tz=LOCAL_TZ)
            ev_end = datetime.fromtimestamp(end_ts, tz=LOCAL_TZ)
            location = getattr(ev, "location", "") or ""
            slots.append(
                TimelineSlot(
                    start=ev_start,
                    end=ev_end,
                    kind="calendar",
                    title=getattr(ev, "title", "予定") or "予定",
                    ref_calendar_event_id=getattr(ev, "id", "") or None,
                    location=location or None,
                    is_locked=True,
                )
            )

            if not _is_home_location(location):
                out_min = lookup_travel_minutes(self.travel_matrix, "home", location or "office")
                in_min = lookup_travel_minutes(self.travel_matrix, location or "office", "home")
                slots.append(
                    TimelineSlot(
                        start=ev_start - timedelta(minutes=out_min),
                        end=ev_start,
                        kind="commute_out",
                        title=f"移動 → {location or '目的地'} ({out_min}分)",
                        ref_calendar_event_id=getattr(ev, "id", "") or None,
                        is_locked=True,
                        travel_buffer_minutes=out_min,
                    )
                )
                slots.append(
                    TimelineSlot(
                        start=ev_end,
                        end=ev_end + timedelta(minutes=in_min),
                        kind="commute_in",
                        title=f"移動 ← {location or '目的地'} ({in_min}分)",
                        ref_calendar_event_id=getattr(ev, "id", "") or None,
                        is_locked=True,
                        travel_buffer_minutes=in_min,
                    )
                )

        return slots

    async def _fetch_active_tasks(self) -> list[CandidateTask]:
        if not self.session:
            return []
        try:
            async with self.session.get(
                f"{BACKEND_URL}/tasks/?include_proposed=false",
                timeout=5,
                headers=self.auth_headers,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"fetch_active_tasks status={resp.status}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.warning(f"fetch_active_tasks error: {e}")
            return []

        out: list[CandidateTask] = []
        for t in data:
            if t.get("is_completed"):
                continue
            dl = t.get("deadline")
            locked = t.get("locked_start")
            try:
                deadline_dt = datetime.fromisoformat(dl.replace("Z", "+00:00")) if dl else None
            except (ValueError, AttributeError):
                deadline_dt = None
            try:
                locked_dt = (
                    datetime.fromisoformat(locked.replace("Z", "+00:00")) if locked else None
                )
            except (ValueError, AttributeError):
                locked_dt = None
            if deadline_dt and deadline_dt.tzinfo is None:
                deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            if locked_dt and locked_dt.tzinfo is None:
                locked_dt = locked_dt.replace(tzinfo=timezone.utc)
            out.append(
                CandidateTask(
                    task_id=t["id"],
                    title=t.get("title", ""),
                    duration_min=max(5, int(t.get("estimated_duration") or 10)),
                    deadline=deadline_dt,
                    cognitive_load=t.get("cognitive_load"),
                    preferred_slot=(t.get("preferred_time_slot") or "anytime"),
                    urgency=int(t.get("urgency") or 2),
                    locked_start=locked_dt,
                    source=t.get("source"),
                    zone=t.get("zone"),
                    location=t.get("location"),
                )
            )
        return out

    def _slot_to_api(self, slot: TimelineSlot) -> dict:
        return {
            "start_ts": slot.start.astimezone(timezone.utc).isoformat(),
            "end_ts": slot.end.astimezone(timezone.utc).isoformat(),
            "kind": slot.kind,
            "ref_task_id": slot.ref_task_id,
            "ref_calendar_event_id": slot.ref_calendar_event_id,
            "title": slot.title,
            "location": slot.location,
            "is_locked": slot.is_locked,
            "travel_buffer_minutes": slot.travel_buffer_minutes,
        }

    async def generate_for_today(self) -> list[TimelineSlot]:
        """Full pipeline: build locked slots, compute free windows, EDF-schedule tasks, POST to backend."""
        day_start, day_end, date_str = self._day_bounds()
        now = datetime.now(LOCAL_TZ)

        routine_slots = self._routine_slots(day_start)
        calendar_slots = self._calendar_slots(day_start, day_end)
        locked_slots = routine_slots + calendar_slots

        free_windows = compute_free_windows(day_start, day_end, locked_slots, min_minutes=15)

        tasks = await self._fetch_active_tasks()
        task_slots, overflow = schedule_edf(tasks, free_windows, now)
        if overflow:
            logger.info(
                f"Timeline overflow: {len(overflow)} task(s) could not fit today"
            )

        all_slots = sorted(routine_slots + calendar_slots + task_slots, key=lambda s: s.start)

        payload = {
            "date": date_str,
            "blocks": [self._slot_to_api(s) for s in all_slots],
        }
        try:
            async with self.session.post(
                f"{BACKEND_URL}/timeline/regenerate",
                json=payload,
                timeout=10,
                headers=self.auth_headers,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"timeline/regenerate failed: {resp.status} {text[:200]}")
        except Exception as e:
            logger.warning(f"timeline/regenerate error: {e}")

        return all_slots
