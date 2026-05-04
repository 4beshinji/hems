"""Tests for brain voice_capsule package (P2 — time-trigger only)."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


class _StubWeather:
    def __init__(self, condition="晴れ", temperature=22):
        self.condition = condition
        self.temperature = temperature


class _StubPhysical:
    def __init__(self, weather=None):
        self.weather = weather or _StubWeather()


@dataclass
class _StubEvent:
    id: str
    title: str
    start_ts: float


class _StubGas:
    def __init__(self, events=None):
        self.calendar_events = events or []


class _StubDigital:
    def __init__(self, events=None):
        self.gas_state = _StubGas(events)


class _StubWorld:
    def __init__(self, *, weather=None, events=None):
        self.physical = _StubPhysical(weather)
        self.digital = _StubDigital(events)


class TestGenericBank:
    def test_default_bank_has_expected_tags(self):
        from voice_capsule.generic_bank import default_bank

        bank = default_bank()
        assert {b.tag for b in bank} >= {"ack_yes", "ack_no", "thinking", "hello", "goodbye"}
        assert all(b.id and b.text for b in bank)


class TestClipPlanner:
    def test_produces_morning_pair_when_weather_known(self):
        from voice_capsule.clip_planner import plan_day

        tomorrow = datetime.now() + timedelta(days=1)
        date = tomorrow.strftime("%Y-%m-%d")
        wake_ts = tomorrow.replace(hour=6, minute=30, second=0, microsecond=0).timestamp()
        clips = asyncio.run(plan_day(date=date, wake_ts=wake_ts, world_model=_StubWorld()))
        ids = [c.id for c in clips]
        assert "morning_greet" in ids
        assert "weather_morning" in ids

    def test_weather_clip_omitted_when_condition_unknown(self):
        from voice_capsule.clip_planner import plan_day

        tomorrow = datetime.now() + timedelta(days=1)
        world = _StubWorld(weather=_StubWeather(condition="unknown"))
        clips = asyncio.run(
            plan_day(
                date=tomorrow.strftime("%Y-%m-%d"),
                wake_ts=tomorrow.replace(hour=7).timestamp(),
                world_model=world,
            )
        )
        assert "weather_morning" not in [c.id for c in clips]

    def test_future_event_yields_pre_event_reminder(self):
        from voice_capsule.clip_planner import plan_day

        tomorrow = datetime.now() + timedelta(days=1)
        date = tomorrow.strftime("%Y-%m-%d")
        event_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        world = _StubWorld(
            events=[
                _StubEvent(id="ev1", title="歯医者", start_ts=event_time.timestamp()),
            ]
        )
        clips = asyncio.run(plan_day(date=date, wake_ts=None, world_model=world))
        reminders = [c for c in clips if c.id.startswith("event_")]
        assert len(reminders) == 1
        # trigger_kind should be pre_event when event has an id
        assert reminders[0].trigger_kind == "pre_event"
        assert reminders[0].event_ref == "ev1"
        assert reminders[0].event_offset_min == 15  # DEFAULT_EVENT_LEAD_MIN (no classifier)
        assert "歯医者" in reminders[0].transcript_seed

    def test_past_event_skipped(self):
        from voice_capsule.clip_planner import plan_day

        past_ts = datetime.now().timestamp() - 300
        today = datetime.now().strftime("%Y-%m-%d")
        world = _StubWorld(
            events=[
                _StubEvent(id="past", title="already_happened", start_ts=past_ts),
            ]
        )
        clips = asyncio.run(plan_day(date=today, wake_ts=None, world_model=world))
        assert not any(c.id.startswith("event_") for c in clips)

    def test_event_classifier_overrides_lead_time(self):
        from voice_capsule.clip_planner import plan_day

        tomorrow = datetime.now() + timedelta(days=1)
        event_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        world = _StubWorld(
            events=[
                _StubEvent(id="ev1", title="診察", start_ts=event_time.timestamp()),
            ]
        )

        class _StubClassifier:
            async def plan_event(self, ev):
                from annotator import EventPlan

                return EventPlan(lead_time_min=60, needs_pre_event=True, priority=1, context_hint="doctor_visit")

        clips = asyncio.run(
            plan_day(
                date=tomorrow.strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=world,
                event_classifier=_StubClassifier(),
            )
        )
        reminder = next(c for c in clips if c.id.startswith("event_"))
        assert reminder.event_offset_min == 60
        assert reminder.priority == 1
        assert "doctor_visit" in reminder.tags

    def test_event_classifier_can_suppress(self):
        from voice_capsule.clip_planner import plan_day

        tomorrow = datetime.now() + timedelta(days=1)
        event_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
        world = _StubWorld(
            events=[
                _StubEvent(id="ev1", title="どうでもいい", start_ts=event_time.timestamp()),
            ]
        )

        class _SuppressClassifier:
            async def plan_event(self, ev):
                from annotator import EventPlan

                return EventPlan(needs_pre_event=False)

        clips = asyncio.run(
            plan_day(
                date=tomorrow.strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=world,
                event_classifier=_SuppressClassifier(),
            )
        )
        assert not any(c.id.startswith("event_") for c in clips)


class TestGeofenceClips:
    def test_geofence_emitted_for_matching_category(self):
        from voice_capsule.clip_planner import plan_day

        places = [
            {
                "id": 7,
                "label": "近所のスギ薬局",
                "category": "drugstore",
                "lat": 35.65,
                "lon": 139.72,
                "radius_m": 200,
                "cooldown_min": 60,
                "enabled": True,
            }
        ]
        shopping = [
            {"name": "シャンプー", "store_category": "drugstore"},
            {"name": "歯ブラシ", "store_category": "drugstore"},
            {"name": "牛乳", "store_category": "supermarket"},
        ]
        clips = asyncio.run(
            plan_day(
                date=datetime.now().strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=_StubWorld(),
                frequent_places=places,
                pending_shopping=shopping,
            )
        )
        geofence = [c for c in clips if c.trigger_kind == "geofence"]
        assert len(geofence) == 1
        g = geofence[0]
        assert g.place_id == 7
        assert g.place_category == "drugstore"
        assert g.place_lat == 35.65
        assert g.cooldown_min == 60
        assert "シャンプー" in g.transcript_seed or "歯ブラシ" in g.transcript_seed

    def test_no_geofence_when_no_matches(self):
        from voice_capsule.clip_planner import plan_day

        places = [
            {
                "id": 7,
                "label": "薬局",
                "category": "drugstore",
                "lat": 1.0,
                "lon": 2.0,
                "radius_m": 200,
                "cooldown_min": 60,
                "enabled": True,
            }
        ]
        shopping = [{"name": "牛乳", "store_category": "supermarket"}]
        clips = asyncio.run(
            plan_day(
                date=datetime.now().strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=_StubWorld(),
                frequent_places=places,
                pending_shopping=shopping,
            )
        )
        assert not any(c.trigger_kind == "geofence" for c in clips)

    def test_biometric_clips_always_emitted(self):
        from voice_capsule.clip_planner import plan_day

        clips = asyncio.run(
            plan_day(
                date=datetime.now().strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=_StubWorld(),
            )
        )
        bio = [c for c in clips if c.trigger_kind == "biometric_threshold"]
        assert len(bio) >= 3
        ids = {c.id for c in bio}
        assert "bio_high_stress" in ids
        assert "bio_high_fatigue" in ids
        assert "bio_high_hr_at_rest" in ids
        stress = next(c for c in bio if c.id == "bio_high_stress")
        assert stress.biometric_metric == "stress"
        assert stress.biometric_op == "gt"
        assert stress.biometric_value == 80.0

    def test_geofence_truncates_transcript_at_three_items(self):
        from voice_capsule.clip_planner import plan_day

        places = [
            {
                "id": 1,
                "label": "スーパー",
                "category": "supermarket",
                "lat": 1.0,
                "lon": 2.0,
                "radius_m": 200,
                "cooldown_min": 60,
                "enabled": True,
            }
        ]
        shopping = [{"name": f"品{i}", "store_category": "supermarket"} for i in range(5)]
        clips = asyncio.run(
            plan_day(
                date=datetime.now().strftime("%Y-%m-%d"),
                wake_ts=None,
                world_model=_StubWorld(),
                frequent_places=places,
                pending_shopping=shopping,
            )
        )
        g = next(c for c in clips if c.trigger_kind == "geofence")
        assert "ほか2件" in g.transcript_seed


class TestCapsuleBuilder:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()

        def _make_resp(status=200, payload=None):
            resp = AsyncMock()
            resp.status = status
            resp.json = AsyncMock(return_value=payload or {})
            resp.text = AsyncMock(return_value="")
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            return resp

        # batch-synthesize returns per-clip audio urls; persist returns 201
        session._make_resp = _make_resp
        session.post = MagicMock(
            side_effect=lambda url, **kw: (
                _make_resp(
                    200,
                    {
                        "results": [
                            {"clip_id": item["clip_id"], "audio_url": f"/audio/{item['clip_id']}.mp3"}
                            for item in kw.get("json", {}).get("items", [])
                        ]
                    },
                )
                if url.endswith("/batch-synthesize")
                else _make_resp(201)
            ),
        )
        # CapsuleBuilder now GETs frequent-places + shopping — make them 200 empty list
        session.get = MagicMock(return_value=_make_resp(200, []))
        return session

    def test_build_daily_capsule_returns_valid_manifest(self, mock_session):
        from voice_capsule import CapsuleBuilder

        builder = CapsuleBuilder(
            session=mock_session,
            voice_service_url="http://voice:8000",
            backend_url="http://backend:8000",
        )
        tomorrow = datetime.now() + timedelta(days=1)
        wake_ts = tomorrow.replace(hour=7).timestamp()
        date = tomorrow.strftime("%Y-%m-%d")
        manifest = asyncio.run(
            builder.build_daily_capsule(
                date,
                world_model=_StubWorld(),
                wake_ts=wake_ts,
            )
        )
        assert manifest is not None
        assert manifest["capsule_id"] == date
        assert len(manifest["generic_bank"]) == 5
        assert any(c["id"] == "morning_greet" for c in manifest["clips"])
        # Audio URLs should have been populated by the mocked batch-synth.
        assert all(c["audio_url"] for c in manifest["clips"])

    def test_build_drops_clips_with_failed_synth(self, mock_session):
        from voice_capsule import CapsuleBuilder

        # Override post to return audio_url ONLY for morning_greet; other clips fail.
        def _partial(url, **kw):
            if url.endswith("/batch-synthesize"):
                items = kw.get("json", {}).get("items", [])
                results = [
                    {
                        "clip_id": it["clip_id"],
                        "audio_url": f"/audio/{it['clip_id']}.mp3" if it["clip_id"] == "morning_greet" else None,
                    }
                    for it in items
                ]
                return mock_session._make_resp(200, {"results": results})
            return mock_session._make_resp(201)

        mock_session.post = MagicMock(side_effect=_partial)

        builder = CapsuleBuilder(
            session=mock_session,
            voice_service_url="http://v:8000",
            backend_url="http://b:8000",
        )
        tomorrow = datetime.now() + timedelta(days=1)
        manifest = asyncio.run(
            builder.build_daily_capsule(
                tomorrow.strftime("%Y-%m-%d"),
                world_model=_StubWorld(),
                wake_ts=tomorrow.replace(hour=7).timestamp(),
            )
        )
        clip_ids = [c["id"] for c in manifest["clips"]]
        assert "morning_greet" in clip_ids
        assert "weather_morning" not in clip_ids  # dropped (no audio_url)
