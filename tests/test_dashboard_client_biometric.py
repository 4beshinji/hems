"""
Tests for DashboardClient.push_biometric_snapshot.
"""
from unittest.mock import MagicMock

import pytest
from world_model.data_classes import (
    BiometricState, HeartRateData, SleepData, ActivityData,
    StressData, FatigueData, SpO2Data,
)


class TestPushBiometricSnapshot:

    def _make_client(self, mock_session):
        from dashboard_client import DashboardClient
        client = DashboardClient(session=mock_session)
        return client

    @pytest.mark.asyncio
    async def test_skips_when_not_connected_and_no_data(self, world_model, mock_session):
        """Should skip when bridge_connected=False AND last_update==0."""
        client = self._make_client(mock_session)
        world_model.biometric_state.bridge_connected = False
        # All sub-data last_update defaults to 0, so last_update property == 0
        await client.push_biometric_snapshot(world_model)
        for call in mock_session.post.call_args_list:
            assert "/biometric/snapshot" not in str(call)

    @pytest.mark.asyncio
    async def test_pushes_when_bridge_connected(self, world_model, mock_session):
        """Should push when bridge is connected even with no sensor data."""
        client = self._make_client(mock_session)
        world_model.biometric_state.bridge_connected = True
        world_model.biometric_state.provider = "fitbit"

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert "/biometric/snapshot" in call_url

    @pytest.mark.asyncio
    async def test_pushes_when_not_connected_but_has_data(self, world_model, mock_session):
        """Should push when bridge disconnected but last_update > 0 (stale data)."""
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = False
        bio.heart_rate.bpm = 72
        bio.heart_rate.last_update = 1000.0  # makes last_update > 0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        mock_session.post.assert_called_once()
        call_url = mock_session.post.call_args[0][0]
        assert "/biometric/snapshot" in call_url

    @pytest.mark.asyncio
    async def test_payload_includes_heart_rate_when_bpm_set(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.provider = "garmin"
        bio.heart_rate.bpm = 85
        bio.heart_rate.zone = "fat_burn"
        bio.heart_rate.resting_bpm = 62

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert "heart_rate" in payload
        assert payload["heart_rate"]["bpm"] == 85
        assert payload["heart_rate"]["zone"] == "fat_burn"
        assert payload["heart_rate"]["resting_bpm"] == 62

    @pytest.mark.asyncio
    async def test_payload_excludes_heart_rate_when_bpm_none(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        # heart_rate.bpm defaults to None

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]
        assert "heart_rate" not in payload

    @pytest.mark.asyncio
    async def test_payload_includes_spo2_when_set(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.spo2.percent = 98

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]
        assert payload["spo2"] == {"percent": 98}

    @pytest.mark.asyncio
    async def test_payload_includes_sleep_data(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.sleep.stage = "deep"
        bio.sleep.duration_minutes = 420
        bio.sleep.deep_minutes = 90
        bio.sleep.rem_minutes = 100
        bio.sleep.light_minutes = 230
        bio.sleep.quality_score = 82
        bio.sleep.last_update = 1000.0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert "sleep" in payload
        assert payload["sleep"]["stage"] == "deep"
        assert payload["sleep"]["duration_minutes"] == 420
        assert payload["sleep"]["deep_minutes"] == 90
        assert payload["sleep"]["rem_minutes"] == 100
        assert payload["sleep"]["light_minutes"] == 230
        assert payload["sleep"]["quality_score"] == 82

    @pytest.mark.asyncio
    async def test_payload_excludes_sleep_when_no_update(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        # sleep.last_update defaults to 0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]
        assert "sleep" not in payload

    @pytest.mark.asyncio
    async def test_payload_includes_activity_data(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.activity.steps = 7500
        bio.activity.steps_goal = 10000
        bio.activity.calories = 320
        bio.activity.active_minutes = 45
        bio.activity.level = "moderate"
        bio.activity.last_update = 1000.0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert "activity" in payload
        assert payload["activity"]["steps"] == 7500
        assert payload["activity"]["steps_goal"] == 10000
        assert payload["activity"]["calories"] == 320
        assert payload["activity"]["active_minutes"] == 45
        assert payload["activity"]["level"] == "moderate"

    @pytest.mark.asyncio
    async def test_payload_includes_stress_when_updated(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.stress.level = 65
        bio.stress.category = "moderate"
        bio.stress.last_update = 1000.0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert "stress" in payload
        assert payload["stress"]["level"] == 65
        assert payload["stress"]["category"] == "moderate"

    @pytest.mark.asyncio
    async def test_payload_includes_fatigue_when_updated(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.fatigue.score = 40
        bio.fatigue.factors = ["poor_sleep", "high_stress"]
        bio.fatigue.last_update = 1000.0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert "fatigue" in payload
        assert payload["fatigue"]["score"] == 40
        assert payload["fatigue"]["factors"] == ["poor_sleep", "high_stress"]

    @pytest.mark.asyncio
    async def test_payload_excludes_stress_and_fatigue_when_no_update(
        self, world_model, mock_session,
    ):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        # stress.last_update and fatigue.last_update default to 0

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]
        assert "stress" not in payload
        assert "fatigue" not in payload

    @pytest.mark.asyncio
    async def test_base_payload_always_has_bridge_connected_and_provider(
        self, world_model, mock_session,
    ):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True
        bio.provider = "apple_health"

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        payload = mock_session.post.call_args[1]["json"]

        assert payload["bridge_connected"] is True
        assert payload["provider"] == "apple_health"

    @pytest.mark.asyncio
    async def test_posts_to_biometric_snapshot_url(self, world_model, mock_session):
        client = self._make_client(mock_session)
        bio = world_model.biometric_state
        bio.bridge_connected = True

        resp = mock_session._make_response(200, {"updated": True})
        mock_session.post = MagicMock(return_value=resp)

        await client.push_biometric_snapshot(world_model)
        call_url = mock_session.post.call_args[0][0]
        assert call_url.endswith("/biometric/snapshot")
