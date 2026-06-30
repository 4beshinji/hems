"""Tests for OutcomeRewardCalculator."""

from feedback.outcome_reward import OutcomeRewardCalculator


def test_effective_and_approved_is_positive():
    calc = OutcomeRewardCalculator()
    reward = calc.calculate({"verdict": "effective", "human_decision": "approve", "rolled_back": False})
    assert reward > 0


def test_counterproductive_and_rejected_is_negative():
    calc = OutcomeRewardCalculator()
    reward = calc.calculate({"verdict": "counterproductive", "human_decision": "reject", "rolled_back": True})
    assert reward < 0


def test_explicit_feedback_mapping():
    calc = OutcomeRewardCalculator()
    assert calc.calculate_from_explicit_feedback("explicit_up") == 1.0
    assert calc.calculate_from_explicit_feedback("explicit_down") == -1.0
    assert calc.calculate_from_explicit_feedback("cancel") == -0.5


def test_reward_is_clamped():
    calc = OutcomeRewardCalculator()
    row = {
        "verdict": "effective",
        "human_decision": "approve",
        "rolled_back": False,
    }
    assert -1.0 <= calc.calculate(row) <= 1.0
