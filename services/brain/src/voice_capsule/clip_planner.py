"""Plan the clip list for a given day.

Time-triggered morning pair (greet + weather) is always emitted. Each of
today's calendar events goes through an optional :class:`EventClassifier`
to decide the reminder lead time; without a classifier, a fixed 15-minute
lead is used.

For events the trigger kind is ``pre_event`` (carries ``event_id`` and
``offset_min``) but ``absolute_ts`` is pre-filled so the Android scheduler
doesn't need calendar context.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .builder import ClipSpec

if TYPE_CHECKING:
    from annotator import EventClassifier


# Fallback lead time when no EventClassifier is wired.
DEFAULT_EVENT_LEAD_MIN = 15

_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9]+")


def _safe_id(raw: str, max_len: int = 24) -> str:
    s = _SAFE_ID_RE.sub("_", raw.strip().lower()).strip("_") or "event"
    return s[:max_len]


async def plan_day(
    *,
    date: str,
    wake_ts: float | None,
    world_model,
    event_classifier: "EventClassifier | None" = None,
    frequent_places: list[dict] | None = None,
    pending_shopping: list[dict] | None = None,
) -> list[ClipSpec]:
    """Plan clips for ``date`` (YYYY-MM-DD). Now async — event_classifier may call LLM.

    ``frequent_places`` / ``pending_shopping`` are backend DTOs (dicts). When
    both are supplied, one geofence clip is emitted for each place whose
    ``category`` matches at least one pending item's ``store_category``.
    """
    clips: list[ClipSpec] = []
    local_tz = datetime.now().astimezone().tzinfo
    wake_dt = (
        datetime.fromtimestamp(wake_ts).astimezone(local_tz)
        if wake_ts
        else datetime.fromisoformat(f"{date}T07:00:00").replace(tzinfo=local_tz)
    )

    # Core morning pair — tone "caring" keeps wake-up gentle.
    weather_ctx = _weather_context(world_model)
    greet_weather_suffix = f" 今日の天気は{weather_ctx}です。" if weather_ctx else ""
    clips.append(ClipSpec(
        id="morning_greet",
        trigger_kind="time",
        trigger_at_ts=int(wake_dt.timestamp()),
        tone="caring",
        transcript_seed=f"おはようございます。{greet_weather_suffix}",
        tags=["morning", "greet"],
        priority=1,
    ))

    weather_body = _weather_body(world_model)
    if weather_body:
        clips.append(ClipSpec(
            id="weather_morning",
            trigger_kind="time",
            trigger_at_ts=int((wake_dt + timedelta(minutes=2)).timestamp()),
            tone="caring",
            transcript_seed=weather_body,
            tags=["morning", "weather"],
            priority=2,
        ))

    # Per-event reminders.
    seen_ids: set[str] = set()
    for ev in _today_events(world_model, date):
        title = (ev.title or "").strip()
        if not title:
            continue

        if event_classifier is not None:
            plan = await event_classifier.plan_event(ev)
            if not plan.needs_pre_event:
                continue
            lead_min = plan.lead_time_min
            priority = plan.priority
            context_hint = plan.context_hint
        else:
            lead_min = DEFAULT_EVENT_LEAD_MIN
            priority = 3
            context_hint = None

        event_time = datetime.fromtimestamp(ev.start_ts).astimezone(local_tz)
        trigger = event_time - timedelta(minutes=lead_min)
        if trigger <= datetime.now(tz=local_tz):
            continue
        raw_id = f"event_{_safe_id(title)}_{event_time.strftime('%H%M')}"
        if raw_id in seen_ids:
            continue
        seen_ids.add(raw_id)
        event_ref = getattr(ev, "id", None)
        clips.append(ClipSpec(
            id=raw_id,
            trigger_kind="pre_event" if event_ref else "time",
            trigger_at_ts=int(trigger.timestamp()),
            tone="neutral",
            transcript_seed=(
                f"{lead_min}分後、{event_time.strftime('%H:%M')}から"
                f"「{title}」です。"
            ),
            tags=["schedule", "reminder"] + ([context_hint] if context_hint else []),
            priority=priority,
            event_ref=event_ref,
            event_offset_min=lead_min,
        ))

    # Geofence clips for pending shopping items matched to FrequentPlaces.
    clips.extend(_geofence_clips(frequent_places or [], pending_shopping or []))

    # Biometric-threshold clips — declarative rules the phone evaluates as
    # biometrics stream in. Decoupled from today's schedule so they ride in
    # every capsule regardless of events.
    clips.extend(_biometric_clips())

    return clips


_BIOMETRIC_RULES = [
    # (clip_id, metric, op, threshold, tone, transcript_seed, priority)
    ("bio_high_stress", "stress", "gt", 80.0, "caring",
     "少し深呼吸しましょう。肩の力を抜いて、3回ゆっくり息を吐いてみてください。", 2),
    ("bio_high_fatigue", "fatigue", "gt", 80.0, "caring",
     "だいぶ疲れが溜まっているみたい。短くでも目を閉じて休んでみませんか。", 2),
    ("bio_high_hr_at_rest", "heart_rate", "gt", 120.0, "neutral",
     "心拍が高めです。座って水を少し飲みましょう。", 1),
]


def _biometric_clips() -> list[ClipSpec]:
    """Return declarative biometric_threshold clips.

    The phone's BiometricEvaluator watches its own biometric stream and
    fires whichever of these matches. Thresholds are conservative defaults
    — P6 will let the user tune them via config.
    """
    out: list[ClipSpec] = []
    for (clip_id, metric, op, threshold, tone, seed, prio) in _BIOMETRIC_RULES:
        out.append(ClipSpec(
            id=clip_id,
            trigger_kind="biometric_threshold",
            trigger_at_ts=None,
            tone=tone,
            transcript_seed=seed,
            tags=["biometric", metric],
            priority=prio,
            biometric_metric=metric,
            biometric_op=op,
            biometric_value=threshold,
        ))
    return out


def _geofence_clips(places: list[dict], shopping: list[dict]) -> list[ClipSpec]:
    """Emit one geofence clip per place whose category matches pending items.

    The transcript enumerates up to 3 item names so the phone's reminder is
    concrete. Cooldown is carried in the manifest so the phone can de-dup
    rapid re-entries into the same geofence.
    """
    out: list[ClipSpec] = []
    by_category: dict[str, list[str]] = {}
    for item in shopping:
        cat = (item.get("store_category") or "").strip()
        name = (item.get("name") or "").strip()
        if not cat or not name:
            continue
        by_category.setdefault(cat, []).append(name)

    if not by_category:
        return out

    for place in places:
        place_id = place.get("id")
        category = (place.get("category") or "").strip()
        label = (place.get("label") or "").strip() or "お店"
        if place_id is None or category not in by_category:
            continue
        matched = by_category[category]
        preview = "、".join(matched[:3])
        if len(matched) > 3:
            preview += f" ほか{len(matched) - 3}件"
        clip_id = f"geofence_place_{place_id}"
        out.append(ClipSpec(
            id=clip_id,
            trigger_kind="geofence",
            trigger_at_ts=None,
            tone="caring",
            transcript_seed=f"{label}の近くです。買いたいものは{preview}。",
            tags=["shopping", "geofence", category],
            priority=3,
            place_id=place_id,
            place_category=category,
            place_lat=place.get("lat"),
            place_lon=place.get("lon"),
            place_radius_m=place.get("radius_m"),
            cooldown_min=place.get("cooldown_min"),
        ))
    return out


# --- internals ------------------------------------------------------------ #

def _weather_context(world_model) -> str:
    try:
        w = world_model.physical.weather
        if w.condition and w.condition != "unknown":
            return w.condition
    except Exception:
        pass
    return ""


def _weather_body(world_model) -> str:
    try:
        w = world_model.physical.weather
        if not w.condition or w.condition == "unknown":
            return ""
        parts = [f"今日の天気は{w.condition}です。"]
        if getattr(w, "temperature", None) is not None:
            parts.append(f"気温は{w.temperature}度の見込み。")
        return "".join(parts)
    except Exception:
        return ""


def _today_events(world_model, date: str) -> list:
    try:
        events = world_model.digital.gas_state.calendar_events
    except Exception:
        return []
    if not events:
        return []
    local_tz = datetime.now().astimezone().tzinfo
    day_start = datetime.fromisoformat(f"{date}T00:00:00").replace(tzinfo=local_tz).timestamp()
    day_end = day_start + 86400
    return [ev for ev in events if day_start <= ev.start_ts < day_end]
