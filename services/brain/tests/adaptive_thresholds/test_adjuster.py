"""Tests for ThresholdAdjuster."""

from adaptive_thresholds.adjuster import AdjusterConfig, ThresholdAdjuster


def test_explicit_down_relaxes_threshold():
    adjuster = ThresholdAdjuster()
    new = adjuster.compute_offset(0.0, feedback_type="explicit_down")
    assert new > 0.0


def test_explicit_up_tightens_threshold():
    adjuster = ThresholdAdjuster()
    new = adjuster.compute_offset(0.0, feedback_type="explicit_up")
    assert new < 0.0


def test_counterproductive_efficacy_relaxes():
    adjuster = ThresholdAdjuster()
    new = adjuster.compute_offset(0.0, efficacy_verdict="counterproductive")
    assert new > 0.0


def test_offset_clamped():
    adjuster = ThresholdAdjuster(AdjusterConfig(min_offset=-2.0, max_offset=2.0, step=1.0))
    new = adjuster.compute_offset(1.5, feedback_type="explicit_down")
    assert new == 2.0
