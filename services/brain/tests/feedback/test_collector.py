"""Tests for FeedbackCollector."""

from feedback.collector import FeedbackCollector


class FakeEventWriter:
    def __init__(self):
        self.feedback = []

    def record_feedback(self, **kwargs):
        self.feedback.append(kwargs)


def test_collect_explicit_buffers_feedback():
    writer = FakeEventWriter()
    collector = FeedbackCollector(event_writer=writer)
    result = collector.collect_explicit(
        target_type="task",
        target_id="1",
        feedback_type="explicit_up",
        channel="frontend",
        user_id="user-1",
    )
    assert result["feedback_type"] == "explicit_up"
    assert len(writer.feedback) == 1
    assert writer.feedback[0]["target_id"] == "1"


def test_collect_implicit_uses_implicit_channel():
    writer = FakeEventWriter()
    collector = FeedbackCollector(event_writer=writer)
    collector.collect_implicit(
        target_type="device_action",
        target_id="10",
        feedback_type="implicit_override",
        context={"device_id": "light"},
    )
    assert writer.feedback[0]["channel"] == "implicit"
    assert writer.feedback[0]["context"]["device_id"] == "light"


def test_collect_without_event_writer_does_not_raise():
    collector = FeedbackCollector(event_writer=None)
    result = collector.collect_explicit("voice", "2", "explicit_down")
    assert result["target_type"] == "voice"
