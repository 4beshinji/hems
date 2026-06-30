"""Tests for intervention efficacy (Group D, ported from SOMS).

Pure-logic tests (metric derivation + verdict) plus a dual-backend writer
round-trip (created -> completed -> post-value -> verdict) on SQLite.
"""

import pytest

from efficacy import compute_verdict, derive_trigger_metric


class TestDeriveTriggerMetric:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("換気してください", "co2"),
            ("CO2が高いので窓を開ける", "co2"),
            ("エアコンの温度を下げる", "temperature"),
            ("室温が高い", "temperature"),
            ("暑いので冷房を入れる", "temperature"),
            ("除湿器をつける", "humidity"),
            ("加湿してください", "humidity"),
        ],
    )
    def test_known_metrics(self, text, expected):
        assert derive_trigger_metric(text) == expected

    @pytest.mark.parametrize("text", ["ホワイトボードを消す", "コーヒー豆を補充する", "", None])
    def test_non_environment_returns_none(self, text):
        assert derive_trigger_metric(text) is None

    def test_co2_beats_generic_temperature_keyword(self):
        assert derive_trigger_metric("空調で換気する") == "co2"


class TestComputeVerdict:
    def test_high_temp_cooled_into_band_is_effective(self):
        assert compute_verdict("temperature", baseline=30.0, post=24.0) == "effective"

    def test_low_temp_warmed_into_band_is_effective(self):
        assert compute_verdict("temperature", baseline=14.0, post=20.0) == "effective"

    def test_high_temp_got_hotter_is_counterproductive(self):
        assert compute_verdict("temperature", baseline=28.0, post=31.0) == "counterproductive"

    def test_high_co2_ventilated_is_effective(self):
        assert compute_verdict("co2", baseline=1600, post=800) == "effective"

    def test_co2_rose_further_is_counterproductive(self):
        assert compute_verdict("co2", baseline=1200, post=1500) == "counterproductive"

    def test_tiny_change_is_inconclusive(self):
        assert compute_verdict("temperature", baseline=30.0, post=29.8) == "inconclusive"

    def test_movement_within_band_is_inconclusive(self):
        assert compute_verdict("temperature", baseline=22.0, post=23.0) == "inconclusive"

    def test_missing_values_are_inconclusive(self):
        assert compute_verdict("temperature", baseline=None, post=24.0) == "inconclusive"
        assert compute_verdict("temperature", baseline=30.0, post=None) == "inconclusive"

    def test_unknown_metric_is_inconclusive(self):
        assert compute_verdict("noise", baseline=10.0, post=5.0) == "inconclusive"

    def test_partial_improvement_still_out_of_band_is_effective(self):
        assert compute_verdict("temperature", baseline=35.0, post=30.0) == "effective"


class TestEfficacyWriterRoundTrip:
    @pytest.mark.asyncio
    async def test_created_completed_postvalue_verdict(self, tmp_path, monkeypatch):
        from datetime import UTC, datetime, timedelta

        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'eff.db'}")
        from event_store import EventWriter, init_db

        engine = await init_db()
        w = EventWriter(engine)

        # Created at t0 with baseline 30C; completed shortly after.
        w.record_intervention_created(
            task_id="t1", zone="居間", trigger_metric="temperature", baseline_value=30.0, window_sec=1800
        )
        await w._flush()
        w.mark_intervention_completed("t1")
        await w._flush()

        # Seed post-completion sensor readings inside the window (avg 24.0).
        import json

        from sqlalchemy import text

        async with engine.begin() as conn:
            row = (await conn.execute(text("SELECT completed_at, window_sec FROM intervention_efficacy"))).fetchone()
            completed_at = datetime.fromisoformat(row[0]) if isinstance(row[0], str) else row[0]
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=UTC)
            for off, val in ((60, 23.5), (120, 24.5)):
                ts = (completed_at + timedelta(seconds=off)).isoformat()
                await conn.execute(
                    text(
                        "INSERT INTO raw_events (timestamp, zone, event_type, source_device, data) "
                        "VALUES (:ts, :zone, 'sensor_reading', 'env_01', :data)"
                    ),
                    {"ts": ts, "zone": "居間", "data": json.dumps({"channel": "temperature", "value": val})},
                )

        post = await w.compute_post_value(zone="居間", channel="temperature", start=completed_at, window_sec=1800)
        assert post == pytest.approx(24.0, abs=0.01)
        verdict = compute_verdict("temperature", 30.0, post)
        assert verdict == "effective"

        # fetch_pending: the window hasn't elapsed yet (completed just now), so none.
        assert await w.fetch_pending_interventions() == []

        await w.record_intervention_verdict(1, post, verdict)
        async with engine.begin() as conn:
            v = (
                await conn.execute(text("SELECT verdict, post_value FROM intervention_efficacy WHERE id=1"))
            ).fetchone()
        assert v[0] == "effective"
        assert v[1] == pytest.approx(24.0, abs=0.01)
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_created_with_approval_id_and_decision_rollback(self, tmp_path, monkeypatch):
        from sqlalchemy import text

        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'eff2.db'}")
        from event_store import EventWriter, init_db

        engine = await init_db()
        w = EventWriter(engine)

        w.record_intervention_created(
            task_id="t2",
            zone="寝室",
            trigger_metric="co2",
            baseline_value=1200.0,
            approval_id="app-123",
        )
        await w._flush()

        w.record_intervention_decision("app-123", "approve")
        await w._flush()

        w.record_intervention_rollback("app-123", True, True)
        await w._flush()

        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text("SELECT approval_id, human_decision, rolled_back, rollback_success FROM intervention_efficacy")
                )
            ).fetchone()
        assert row[0] == "app-123"
        assert row[1] == "approve"
        assert row[2] == 1
        assert row[3] == 1
        await engine.dispose()
