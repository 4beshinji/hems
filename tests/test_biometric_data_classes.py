"""
Tests for biometric data class *behavior*: classification thresholds, derived
properties, ring buffers, default-factory isolation, and aggregate
last_update.

Trivial @dataclass default/assignment tests dropped — Python guarantees that.
Boundary tests on classify_* methods are preserved because the thresholds are
real business logic.
"""

from world_model.data_classes import (
    ActivityData,
    BiometricState,
    Event,
    HeartRateData,
    StressData,
)


class TestHeartRateZoneClassification:
    """HeartRateData.classify_zone returns the zone name for a bpm value."""

    def test_rest(self):
        assert HeartRateData.classify_zone(50) == "rest"
        assert HeartRateData.classify_zone(59) == "rest"

    def test_rest_to_fat_burn_boundary(self):
        assert HeartRateData.classify_zone(59) == "rest"
        assert HeartRateData.classify_zone(60) == "fat_burn"

    def test_fat_burn(self):
        assert HeartRateData.classify_zone(90) == "fat_burn"
        assert HeartRateData.classify_zone(119) == "fat_burn"

    def test_fat_burn_to_cardio_boundary(self):
        assert HeartRateData.classify_zone(119) == "fat_burn"
        assert HeartRateData.classify_zone(120) == "cardio"

    def test_cardio(self):
        assert HeartRateData.classify_zone(135) == "cardio"
        assert HeartRateData.classify_zone(149) == "cardio"

    def test_cardio_to_peak_boundary(self):
        assert HeartRateData.classify_zone(149) == "cardio"
        assert HeartRateData.classify_zone(150) == "peak"

    def test_peak(self):
        assert HeartRateData.classify_zone(180) == "peak"
        assert HeartRateData.classify_zone(200) == "peak"


class TestActivityGoalProgress:
    """ActivityData.goal_progress is steps/steps_goal capped to [0, 1]."""

    def test_partial_progress(self):
        assert ActivityData(steps=5000, steps_goal=10000).goal_progress == 0.5

    def test_zero_steps(self):
        assert ActivityData(steps=0, steps_goal=10000).goal_progress == 0.0

    def test_at_goal(self):
        assert ActivityData(steps=10000, steps_goal=10000).goal_progress == 1.0

    def test_over_goal_capped(self):
        assert ActivityData(steps=15000, steps_goal=10000).goal_progress == 1.0

    def test_zero_goal_avoids_division_error(self):
        assert ActivityData(steps=5000, steps_goal=0).goal_progress == 0.0

    def test_negative_goal_treated_as_zero(self):
        assert ActivityData(steps=5000, steps_goal=-100).goal_progress == 0.0


class TestStressCategoryClassification:
    """StressData.classify_category maps level to category bucket."""

    def test_relaxed(self):
        assert StressData.classify_category(0) == "relaxed"
        assert StressData.classify_category(24) == "relaxed"

    def test_relaxed_to_normal_boundary(self):
        assert StressData.classify_category(24) == "relaxed"
        assert StressData.classify_category(25) == "normal"

    def test_normal(self):
        assert StressData.classify_category(35) == "normal"
        assert StressData.classify_category(49) == "normal"

    def test_normal_to_moderate_boundary(self):
        assert StressData.classify_category(49) == "normal"
        assert StressData.classify_category(50) == "moderate"

    def test_moderate(self):
        assert StressData.classify_category(60) == "moderate"
        assert StressData.classify_category(74) == "moderate"

    def test_moderate_to_high_boundary(self):
        assert StressData.classify_category(74) == "moderate"
        assert StressData.classify_category(75) == "high"

    def test_high(self):
        assert StressData.classify_category(90) == "high"
        assert StressData.classify_category(100) == "high"


class TestBiometricStateAggregates:
    """BiometricState aggregate properties and ring buffer behavior."""

    def test_last_update_zero_when_all_sources_unset(self):
        assert BiometricState().last_update == 0

    def test_last_update_returns_max_across_sources(self):
        bs = BiometricState()
        bs.heart_rate.last_update = 100.0
        bs.sleep.last_update = 200.0
        bs.activity.last_update = 50.0
        bs.stress.last_update = 150.0
        bs.fatigue.last_update = 300.0
        bs.spo2.last_update = 250.0
        assert bs.last_update == 300.0

    def test_last_update_with_only_one_source(self):
        bs = BiometricState()
        bs.spo2.last_update = 42.0
        assert bs.last_update == 42.0

    def test_event_ring_buffer_explicit_max(self):
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
        assert len(bs.events) == 30  # default max_events=30
        assert bs.events[0].event_type == "ev_5"
        assert bs.events[-1].event_type == "ev_34"

    def test_independent_instances(self):
        """Default factories produce independent state per instance."""
        bs1 = BiometricState()
        bs2 = BiometricState()
        bs1.add_event(Event(event_type="only_in_bs1"))
        bs1.heart_rate.bpm = 80
        assert len(bs1.events) == 1
        assert len(bs2.events) == 0
        assert bs2.heart_rate.bpm is None
