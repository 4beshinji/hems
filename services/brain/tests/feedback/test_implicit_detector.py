"""Tests for ImplicitFeedbackDetector."""

from datetime import UTC, datetime

from feedback.collector import FeedbackCollector
from feedback.implicit_detector import ImplicitFeedbackDetector


class FakeEventWriter:
    def __init__(self):
        self.feedback = []

    def record_feedback(self, **kwargs):
        self.feedback.append(kwargs)


def now():
    return datetime.now(UTC)


def test_detects_inverse_action_override():
    writer = FakeEventWriter()
    detector = ImplicitFeedbackDetector(collector=FeedbackCollector(writer), window_seconds=30, clock=now)
    detector.record_action("device_action", "42", "light.living", "on")
    emitted = detector.observe_state("light.living", {"action": "off"})
    assert len(emitted) == 1
    assert emitted[0]["feedback_type"] == "implicit_override"


def test_detects_state_on_false_after_on():
    writer = FakeEventWriter()
    detector = ImplicitFeedbackDetector(collector=FeedbackCollector(writer), window_seconds=30, clock=now)
    detector.record_action("device_action", "42", "light.living", "on")
    emitted = detector.observe_state("light.living", {"on": False})
    assert len(emitted) == 1


def test_ignores_non_overriding_state():
    writer = FakeEventWriter()
    detector = ImplicitFeedbackDetector(collector=FeedbackCollector(writer), window_seconds=30, clock=now)
    detector.record_action("device_action", "42", "light.living", "on")
    emitted = detector.observe_state("light.living", {"on": True})
    assert len(emitted) == 0


def test_old_actions_are_pruned():
    writer = FakeEventWriter()
    base = datetime.now(UTC)

    def frozen():
        return base

    detector = ImplicitFeedbackDetector(collector=FeedbackCollector(writer), window_seconds=5, clock=frozen)
    detector.record_action("device_action", "42", "light.living", "on")

    def later():
        return base.replace(second=base.second + 10)

    detector._clock = later
    emitted = detector.observe_state("light.living", {"action": "off"})
    assert len(emitted) == 0
