"""Tests for occupancy activity/posture data in WorldModel LLM context."""
import pytest
from world_model.data_classes import OccupancyData


class TestWorldModelOccupancyContext:
    """Test that occupancy activity/posture data appears in LLM context."""

    def test_activity_in_llm_context(self, world_model):
        """Activity class and level appear in LLM context when set."""
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            activity_class="moderate",
            activity_level=0.6,
        )
        ctx = world_model.get_llm_context()
        assert "活動: moderate (レベル0.6)" in ctx

    def test_posture_in_llm_context(self, world_model):
        """Posture status and duration appear in LLM context when set."""
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            posture_status="static",
            posture_duration_sec=2400,  # 40 minutes
        )
        ctx = world_model.get_llm_context()
        assert "姿勢: static (40分)" in ctx

    def test_no_activity_when_unknown(self, world_model):
        """Default 'unknown' values do not produce activity/posture lines."""
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            activity_class="unknown",
            posture_status="unknown",
        )
        ctx = world_model.get_llm_context()
        assert "在室: 1人" in ctx
        assert "活動:" not in ctx
        assert "姿勢:" not in ctx
