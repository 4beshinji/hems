"""
Tests for ToolExecutor biometric tool handlers.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from world_model.data_classes import (
    HeartRateData, SleepData, ActivityData, StressData, FatigueData, SpO2Data,
)


class TestGetBiometrics:
    """Test _handle_get_biometrics — reads from world_model.biometric_state."""

    @pytest.mark.asyncio
    async def test_returns_heart_rate_when_set(self, tool_executor, world_model):
        world_model.biometric_state.heart_rate = HeartRateData(
            bpm=72, resting_bpm=60, zone="fat_burn", last_update=1.0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["heart_rate"]["bpm"] == 72
        assert data["heart_rate"]["zone"] == "fat_burn"
        assert data["heart_rate"]["resting_bpm"] == 60

    @pytest.mark.asyncio
    async def test_returns_spo2_when_set(self, tool_executor, world_model):
        world_model.biometric_state.spo2 = SpO2Data(percent=98, last_update=1.0)
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert data["spo2"]["percent"] == 98

    @pytest.mark.asyncio
    async def test_returns_stress_when_set(self, tool_executor, world_model):
        world_model.biometric_state.stress = StressData(
            level=65, category="moderate", last_update=1.0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert data["stress"]["level"] == 65
        assert data["stress"]["category"] == "moderate"

    @pytest.mark.asyncio
    async def test_returns_fatigue_when_set(self, tool_executor, world_model):
        world_model.biometric_state.fatigue = FatigueData(
            score=40, factors=["poor_sleep", "high_stress"], last_update=1.0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert data["fatigue"]["score"] == 40
        assert data["fatigue"]["factors"] == ["poor_sleep", "high_stress"]

    @pytest.mark.asyncio
    async def test_returns_activity_when_set(self, tool_executor, world_model):
        world_model.biometric_state.activity = ActivityData(
            steps=8500, steps_goal=10000, calories=350, level="moderate",
            last_update=1.0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert data["activity"]["steps"] == 8500
        assert data["activity"]["steps_goal"] == 10000
        assert data["activity"]["calories"] == 350
        assert data["activity"]["level"] == "moderate"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_data(self, tool_executor, world_model):
        """With default BiometricState, only bridge_connected and provider are returned."""
        result = await tool_executor.execute("get_biometrics", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert "bridge_connected" in data
        assert "provider" in data
        assert "heart_rate" not in data
        assert "spo2" not in data
        assert "stress" not in data
        assert "fatigue" not in data
        assert "activity" not in data

    @pytest.mark.asyncio
    async def test_bridge_connected_flag(self, tool_executor, world_model):
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.provider = "gadgetbridge"
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert data["bridge_connected"] is True
        assert data["provider"] == "gadgetbridge"

    @pytest.mark.asyncio
    async def test_omits_heart_rate_when_bpm_none(self, tool_executor, world_model):
        """heart_rate is only included when bpm is not None."""
        world_model.biometric_state.heart_rate = HeartRateData(
            bpm=None, resting_bpm=60, zone="rest", last_update=1.0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert "heart_rate" not in data

    @pytest.mark.asyncio
    async def test_omits_stress_when_no_update(self, tool_executor, world_model):
        """stress is only included when last_update > 0."""
        world_model.biometric_state.stress = StressData(
            level=50, category="normal", last_update=0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert "stress" not in data

    @pytest.mark.asyncio
    async def test_omits_fatigue_when_no_update(self, tool_executor, world_model):
        """fatigue is only included when last_update > 0."""
        world_model.biometric_state.fatigue = FatigueData(
            score=30, factors=[], last_update=0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert "fatigue" not in data

    @pytest.mark.asyncio
    async def test_omits_activity_when_no_update(self, tool_executor, world_model):
        """activity is only included when last_update > 0."""
        world_model.biometric_state.activity = ActivityData(
            steps=5000, steps_goal=10000, calories=200, level="light",
            last_update=0,
        )
        result = await tool_executor.execute("get_biometrics", {})
        data = json.loads(result["result"])
        assert "activity" not in data


class TestGetSleepSummary:
    """Test _handle_get_sleep_summary — reads from world_model or bridge API."""

    @pytest.mark.asyncio
    async def test_returns_sleep_data_from_world_model(self, tool_executor, world_model):
        world_model.biometric_state.sleep = SleepData(
            stage="deep", duration_minutes=420, deep_minutes=90,
            rem_minutes=100, light_minutes=230, quality_score=82,
            last_update=1.0,
        )
        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["duration_minutes"] == 420
        assert data["deep_minutes"] == 90
        assert data["rem_minutes"] == 100
        assert data["light_minutes"] == 230
        assert data["quality_score"] == 82
        assert data["stage"] == "deep"

    @pytest.mark.asyncio
    async def test_returns_no_data_message_when_empty(self, tool_executor, world_model):
        """With default SleepData (last_update=0) and no biometric_url, returns Japanese message."""
        tool_executor.biometric_url = ""
        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        assert result["result"] == "睡眠データがまだありません"

    @pytest.mark.asyncio
    async def test_falls_back_to_bridge_api(self, tool_executor, world_model, mock_session):
        """When no world model data but biometric_url is set, queries bridge API."""
        tool_executor.biometric_url = "http://biometric-bridge:8000"
        bridge_data = {
            "duration_minutes": 380,
            "deep_minutes": 70,
            "rem_minutes": 85,
            "light_minutes": 225,
            "quality_score": 75,
            "stage": "awake",
        }
        resp = mock_session._make_response(200, bridge_data)
        mock_session.get = MagicMock(return_value=resp)

        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["duration_minutes"] == 380
        assert data["quality_score"] == 75
        mock_session.get.assert_called_once()
        call_url = mock_session.get.call_args[0][0]
        assert "/api/biometric/sleep" in call_url

    @pytest.mark.asyncio
    async def test_bridge_api_no_data_response(self, tool_executor, world_model, mock_session):
        """When bridge API returns status=no_data, returns the no-data message."""
        tool_executor.biometric_url = "http://biometric-bridge:8000"
        resp = mock_session._make_response(200, {"status": "no_data"})
        mock_session.get = MagicMock(return_value=resp)

        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        assert result["result"] == "睡眠データがまだありません"

    @pytest.mark.asyncio
    async def test_bridge_api_error_falls_through(self, tool_executor, world_model, mock_session):
        """When bridge API returns non-200, falls through to no-data message."""
        tool_executor.biometric_url = "http://biometric-bridge:8000"
        resp = mock_session._make_response(503, {"detail": "Service unavailable"})
        mock_session.get = MagicMock(return_value=resp)

        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        assert result["result"] == "睡眠データがまだありません"

    @pytest.mark.asyncio
    async def test_bridge_api_exception_falls_through(self, tool_executor, world_model, mock_session):
        """When bridge API raises an exception, falls through to no-data message."""
        tool_executor.biometric_url = "http://biometric-bridge:8000"
        mock_session.get = MagicMock(side_effect=Exception("Connection refused"))

        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        assert result["result"] == "睡眠データがまだありません"

    @pytest.mark.asyncio
    async def test_world_model_data_takes_priority_over_bridge(
        self, tool_executor, world_model, mock_session,
    ):
        """When world model has sleep data, bridge API is not called."""
        tool_executor.biometric_url = "http://biometric-bridge:8000"
        world_model.biometric_state.sleep = SleepData(
            stage="rem", duration_minutes=360, deep_minutes=80,
            rem_minutes=90, light_minutes=190, quality_score=70,
            last_update=1.0,
        )
        result = await tool_executor.execute("get_sleep_summary", {})
        assert result["success"] is True
        data = json.loads(result["result"])
        assert data["stage"] == "rem"
        # Bridge should NOT have been called
        mock_session.get.assert_not_called()
