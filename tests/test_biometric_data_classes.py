"""
Tests for biometric data classes (HeartRateData, SleepData, ActivityData,
StressData, FatigueData, SpO2Data, BiometricState).
"""
import time
from world_model.data_classes import (
    HeartRateData, SleepData, ActivityData, StressData,
    FatigueData, SpO2Data, BiometricState, Event,
)


class TestHeartRateData:
    def test_defaults(self):
        hr = HeartRateData()
        assert hr.bpm is None
        assert hr.resting_bpm is None
        assert hr.zone == "unknown"
        assert hr.last_update == 0

    def test_custom_values(self):
        hr = HeartRateData(bpm=72, resting_bpm=58, zone="fat_burn", last_update=1.0)
        assert hr.bpm == 72
        assert hr.resting_bpm == 58
        assert hr.zone == "fat_burn"
        assert hr.last_update == 1.0

    def test_classify_zone_rest(self):
        assert HeartRateData.classify_zone(50) == "rest"
        assert HeartRateData.classify_zone(59) == "rest"

    def test_classify_zone_rest_boundary(self):
        """bpm < 60 is rest, bpm == 60 is fat_burn."""
        assert HeartRateData.classify_zone(59) == "rest"
        assert HeartRateData.classify_zone(60) == "fat_burn"

    def test_classify_zone_fat_burn(self):
        assert HeartRateData.classify_zone(60) == "fat_burn"
        assert HeartRateData.classify_zone(90) == "fat_burn"
        assert HeartRateData.classify_zone(119) == "fat_burn"

    def test_classify_zone_fat_burn_boundary(self):
        """bpm < 120 is fat_burn, bpm == 120 is cardio."""
        assert HeartRateData.classify_zone(119) == "fat_burn"
        assert HeartRateData.classify_zone(120) == "cardio"

    def test_classify_zone_cardio(self):
        assert HeartRateData.classify_zone(120) == "cardio"
        assert HeartRateData.classify_zone(135) == "cardio"
        assert HeartRateData.classify_zone(149) == "cardio"

    def test_classify_zone_cardio_boundary(self):
        """bpm < 150 is cardio, bpm == 150 is peak."""
        assert HeartRateData.classify_zone(149) == "cardio"
        assert HeartRateData.classify_zone(150) == "peak"

    def test_classify_zone_peak(self):
        assert HeartRateData.classify_zone(150) == "peak"
        assert HeartRateData.classify_zone(180) == "peak"
        assert HeartRateData.classify_zone(200) == "peak"


class TestSleepData:
    def test_defaults(self):
        s = SleepData()
        assert s.stage == "unknown"
        assert s.duration_minutes == 0
        assert s.deep_minutes == 0
        assert s.rem_minutes == 0
        assert s.light_minutes == 0
        assert s.quality_score == 0
        assert s.sleep_start_ts == 0
        assert s.sleep_end_ts == 0
        assert s.last_update == 0

    def test_custom_values(self):
        s = SleepData(
            stage="deep", duration_minutes=480, deep_minutes=90,
            rem_minutes=120, light_minutes=270, quality_score=85,
            sleep_start_ts=1000.0, sleep_end_ts=29800.0, last_update=2.0,
        )
        assert s.stage == "deep"
        assert s.duration_minutes == 480
        assert s.deep_minutes == 90
        assert s.rem_minutes == 120
        assert s.light_minutes == 270
        assert s.quality_score == 85
        assert s.sleep_start_ts == 1000.0
        assert s.sleep_end_ts == 29800.0
        assert s.last_update == 2.0


class TestActivityData:
    def test_defaults(self):
        a = ActivityData()
        assert a.steps == 0
        assert a.steps_goal == 10000
        assert a.calories == 0
        assert a.active_minutes == 0
        assert a.level == "rest"
        assert a.last_update == 0

    def test_custom_values(self):
        a = ActivityData(steps=7500, steps_goal=10000, calories=350,
                         active_minutes=45, level="moderate", last_update=3.0)
        assert a.steps == 7500
        assert a.calories == 350
        assert a.active_minutes == 45
        assert a.level == "moderate"

    def test_goal_progress_normal(self):
        a = ActivityData(steps=5000, steps_goal=10000)
        assert a.goal_progress == 0.5

    def test_goal_progress_zero_steps(self):
        a = ActivityData(steps=0, steps_goal=10000)
        assert a.goal_progress == 0.0

    def test_goal_progress_goal_reached(self):
        a = ActivityData(steps=10000, steps_goal=10000)
        assert a.goal_progress == 1.0

    def test_goal_progress_over_goal_capped_at_one(self):
        a = ActivityData(steps=15000, steps_goal=10000)
        assert a.goal_progress == 1.0

    def test_goal_progress_zero_goal(self):
        """When steps_goal is 0, should return 0.0 (avoid division by zero)."""
        a = ActivityData(steps=5000, steps_goal=0)
        assert a.goal_progress == 0.0

    def test_goal_progress_negative_goal(self):
        """When steps_goal is negative, should return 0.0."""
        a = ActivityData(steps=5000, steps_goal=-100)
        assert a.goal_progress == 0.0


class TestStressData:
    def test_defaults(self):
        s = StressData()
        assert s.level == 0
        assert s.category == "unknown"
        assert s.last_update == 0

    def test_custom_values(self):
        s = StressData(level=65, category="moderate", last_update=4.0)
        assert s.level == 65
        assert s.category == "moderate"

    def test_classify_category_relaxed(self):
        assert StressData.classify_category(0) == "relaxed"
        assert StressData.classify_category(10) == "relaxed"
        assert StressData.classify_category(24) == "relaxed"

    def test_classify_category_relaxed_boundary(self):
        """level < 25 is relaxed, level == 25 is normal."""
        assert StressData.classify_category(24) == "relaxed"
        assert StressData.classify_category(25) == "normal"

    def test_classify_category_normal(self):
        assert StressData.classify_category(25) == "normal"
        assert StressData.classify_category(35) == "normal"
        assert StressData.classify_category(49) == "normal"

    def test_classify_category_normal_boundary(self):
        """level < 50 is normal, level == 50 is moderate."""
        assert StressData.classify_category(49) == "normal"
        assert StressData.classify_category(50) == "moderate"

    def test_classify_category_moderate(self):
        assert StressData.classify_category(50) == "moderate"
        assert StressData.classify_category(60) == "moderate"
        assert StressData.classify_category(74) == "moderate"

    def test_classify_category_moderate_boundary(self):
        """level < 75 is moderate, level == 75 is high."""
        assert StressData.classify_category(74) == "moderate"
        assert StressData.classify_category(75) == "high"

    def test_classify_category_high(self):
        assert StressData.classify_category(75) == "high"
        assert StressData.classify_category(90) == "high"
        assert StressData.classify_category(100) == "high"


class TestFatigueData:
    def test_defaults(self):
        f = FatigueData()
        assert f.score == 0
        assert f.factors == []
        assert f.last_update == 0

    def test_custom_values(self):
        f = FatigueData(score=70, factors=["poor_sleep", "high_activity"], last_update=5.0)
        assert f.score == 70
        assert f.factors == ["poor_sleep", "high_activity"]
        assert f.last_update == 5.0

    def test_independent_factors_lists(self):
        """Ensure default factory creates independent lists."""
        f1 = FatigueData()
        f2 = FatigueData()
        f1.factors.append("dehydration")
        assert len(f1.factors) == 1
        assert len(f2.factors) == 0


class TestSpO2Data:
    def test_defaults(self):
        s = SpO2Data()
        assert s.percent is None
        assert s.last_update == 0

    def test_custom_values(self):
        s = SpO2Data(percent=98, last_update=6.0)
        assert s.percent == 98
        assert s.last_update == 6.0


class TestBiometricState:
    def test_defaults(self):
        bs = BiometricState()
        assert isinstance(bs.heart_rate, HeartRateData)
        assert isinstance(bs.sleep, SleepData)
        assert isinstance(bs.activity, ActivityData)
        assert isinstance(bs.stress, StressData)
        assert isinstance(bs.fatigue, FatigueData)
        assert isinstance(bs.spo2, SpO2Data)
        assert bs.provider == ""
        assert bs.bridge_connected is False
        assert bs.events == []
        assert bs.max_events == 30

    def test_last_update_all_zero(self):
        bs = BiometricState()
        assert bs.last_update == 0

    def test_last_update_returns_max(self):
        bs = BiometricState()
        bs.heart_rate.last_update = 100.0
        bs.sleep.last_update = 200.0
        bs.activity.last_update = 50.0
        bs.stress.last_update = 150.0
        bs.fatigue.last_update = 300.0
        bs.spo2.last_update = 250.0
        assert bs.last_update == 300.0

    def test_last_update_single_source(self):
        """Only one sub-data has a non-zero timestamp."""
        bs = BiometricState()
        bs.spo2.last_update = 42.0
        assert bs.last_update == 42.0

    def test_add_event(self):
        bs = BiometricState()
        ev = Event(event_type="hr_spike", description="Heart rate spike detected", severity=1)
        bs.add_event(ev)
        assert len(bs.events) == 1
        assert bs.events[0].event_type == "hr_spike"

    def test_event_ring_buffer(self):
        bs = BiometricState(max_events=5)
        for i in range(10):
            bs.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(bs.events) == 5
        assert bs.events[0].event_type == "ev_5"
        assert bs.events[-1].event_type == "ev_9"

    def test_event_ring_buffer_default_max(self):
        bs = BiometricState()
        for i in range(35):
            bs.add_event(Event(event_type=f"ev_{i}", description=f"Event {i}"))
        assert len(bs.events) == 30
        assert bs.events[0].event_type == "ev_5"
        assert bs.events[-1].event_type == "ev_34"

    def test_independent_instances(self):
        """Ensure dataclass fields don't share mutable defaults."""
        bs1 = BiometricState()
        bs2 = BiometricState()
        bs1.add_event(Event(event_type="only_in_bs1"))
        bs1.heart_rate.bpm = 80
        assert len(bs1.events) == 1
        assert len(bs2.events) == 0
        assert bs2.heart_rate.bpm is None

    def test_provider_and_bridge(self):
        bs = BiometricState(provider="fitbit", bridge_connected=True)
        assert bs.provider == "fitbit"
        assert bs.bridge_connected is True
