"""Tests for AdaptiveRuleThresholds wrapper."""

from rules.config import AdaptiveRuleThresholds, load_rule_thresholds


def test_offset_applied_to_numeric_thresholds():
    base = load_rule_thresholds()
    adaptive = AdaptiveRuleThresholds(base, offsets={"co2_high": 50.0})
    assert adaptive.co2_high == base.co2_high + 50
    assert adaptive.temp_high == base.temp_high


def test_non_numeric_fields_unchanged():
    base = load_rule_thresholds()
    adaptive = AdaptiveRuleThresholds(base)
    assert adaptive.biometric_stale_minutes == base.biometric_stale_minutes


def test_set_offset_and_get_effective():
    base = load_rule_thresholds()
    adaptive = AdaptiveRuleThresholds(base)
    adaptive.set_offset("temp_high", -2.0)
    assert adaptive.get_effective("temp_high") == base.temp_high - 2.0
    assert adaptive.get_offset("temp_high") == -2.0
