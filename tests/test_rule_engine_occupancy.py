"""Tests for rule engine occupancy/activity rules."""
import time
from unittest.mock import patch

import pytest
from world_model.data_classes import OccupancyData


class TestRuleEngineOccupancyRules:
    """Test occupancy-related rules (posture and late-night idle)."""

    def _make_engine(self):
        from rule_engine import RuleEngine
        engine = RuleEngine()
        engine._cooldowns = {}
        return engine

    # --- Long static posture ---

    def test_long_static_posture_generates_speak(self, world_model):
        """posture_status='static' with duration above threshold triggers speak."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            posture_status="static",
            posture_duration_sec=3700,  # > 60*60 = 3600
            activity_class="idle",
            activity_level=0.1,
        )

        actions = engine.evaluate(world_model)
        posture_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "ストレッチ" in a["args"]["message"]
        ]
        assert len(posture_speaks) == 1
        assert posture_speaks[0]["args"]["tone"] == "caring"

    def test_short_posture_no_action(self, world_model):
        """posture_status='static' but duration below threshold does not trigger."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            posture_status="static",
            posture_duration_sec=1800,  # 30 min, below default 60 min
            activity_class="idle",
            activity_level=0.1,
        )

        actions = engine.evaluate(world_model)
        posture_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "ストレッチ" in a["args"]["message"]
        ]
        assert len(posture_speaks) == 0

    def test_non_static_posture_no_action(self, world_model):
        """posture_status='changing' does not trigger even with long duration."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            posture_status="changing",
            posture_duration_sec=7200,
            activity_class="moderate",
            activity_level=0.5,
        )

        actions = engine.evaluate(world_model)
        posture_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "ストレッチ" in a["args"]["message"]
        ]
        assert len(posture_speaks) == 0

    # --- Late night idle ---

    def test_late_idle_generates_speak(self, world_model):
        """hour >= 23 with idle activity and count > 0 triggers sleep suggestion."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            activity_class="idle",
            activity_level=0.05,
        )

        # Mock datetime.now() to return 23:30
        import rule_engine as re_module
        from datetime import datetime as real_datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 2, 20, 23, 30, 0)

        with patch.object(re_module, "datetime", FakeDatetime):
            actions = engine.evaluate(world_model)

        late_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "休みましょう" in a["args"]["message"]
        ]
        assert len(late_speaks) == 1
        assert late_speaks[0]["args"]["tone"] == "caring"

    def test_daytime_idle_no_action(self, world_model):
        """hour = 14 with idle activity does not trigger sleep suggestion."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            activity_class="idle",
            activity_level=0.05,
        )

        import rule_engine as re_module
        from datetime import datetime as real_datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 2, 20, 14, 0, 0)

        with patch.object(re_module, "datetime", FakeDatetime):
            actions = engine.evaluate(world_model)

        late_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "休みましょう" in a["args"]["message"]
        ]
        assert len(late_speaks) == 0

    def test_late_but_active_no_action(self, world_model):
        """hour >= 23 but activity_class='moderate' does not trigger sleep suggestion."""
        engine = self._make_engine()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            count=1,
            activity_class="moderate",
            activity_level=0.6,
        )

        import rule_engine as re_module
        from datetime import datetime as real_datetime

        class FakeDatetime(real_datetime):
            @classmethod
            def now(cls, tz=None):
                return real_datetime(2026, 2, 20, 23, 45, 0)

        with patch.object(re_module, "datetime", FakeDatetime):
            actions = engine.evaluate(world_model)

        late_speaks = [
            a for a in actions
            if a["tool"] == "speak" and "休みましょう" in a["args"]["message"]
        ]
        assert len(late_speaks) == 0
