"""Regression tests for brain → backend ``BACKEND_API_KEY`` wiring.

Follow-up to ``docs/technical-debt-followups-2026-05-25.md`` (P1: the shared-key
gate added in R7.1 was never wired to the brain's REST clients). Every
brain→backend call must carry ``Authorization: Bearer <BACKEND_API_KEY>`` when
the key is set, and must NOT leak that key onto the voice-service path (which
uses the independent ``HEMS_INTERNAL_TOKEN`` gate).
"""

from unittest.mock import MagicMock

import pytest

from brain_constants import backend_auth_headers
from world_model.data_classes import CPUData, MemoryData


class TestBackendAuthHeaders:
    def test_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        assert backend_auth_headers() == {}

    def test_bearer_when_set(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert backend_auth_headers() == {"Authorization": "Bearer s3cret"}

    def test_reads_env_each_call(self, monkeypatch):
        # Hot-reload friendliness: no module-level caching.
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        assert backend_auth_headers() == {}
        monkeypatch.setenv("BACKEND_API_KEY", "later")
        assert backend_auth_headers() == {"Authorization": "Bearer later"}


class TestDashboardClientWiring:
    def _client(self, mock_session):
        from dashboard_client import DashboardClient

        return DashboardClient(session=mock_session)

    @pytest.mark.asyncio
    async def test_backend_snapshot_sends_bearer(self, world_model, mock_session, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "abc123")
        world_model.pc_state.cpu = CPUData(usage_percent=10, core_count=4, last_update=1.0)
        world_model.pc_state.memory = MemoryData(used_gb=4, total_gb=16, percent=25, last_update=1.0)
        resp = mock_session._make_response(200, {"ok": True})
        mock_session.post = MagicMock(return_value=resp)

        await self._client(mock_session).push_pc_snapshot(world_model)

        mock_session.post.assert_called_once()
        headers = mock_session.post.call_args[1]["headers"]
        assert headers == {"Authorization": "Bearer abc123"}

    @pytest.mark.asyncio
    async def test_backend_snapshot_no_header_when_unset(self, world_model, mock_session, monkeypatch):
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        world_model.pc_state.cpu = CPUData(usage_percent=10, core_count=4, last_update=1.0)
        world_model.pc_state.memory = MemoryData(used_gb=4, total_gb=16, percent=25, last_update=1.0)
        resp = mock_session._make_response(200, {"ok": True})
        mock_session.post = MagicMock(return_value=resp)

        await self._client(mock_session).push_pc_snapshot(world_model)

        # Empty dict → no Authorization injected (backend runs open / LAN-trusted).
        assert mock_session.post.call_args[1]["headers"] == {}

    @pytest.mark.asyncio
    async def test_backend_key_does_not_leak_to_voice_path(self, mock_session, monkeypatch):
        """speak(): voice synth uses HEMS_INTERNAL_TOKEN, voice-events log uses BACKEND_API_KEY."""
        monkeypatch.setenv("BACKEND_API_KEY", "backendkey")
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        synth = mock_session._make_response(200, {"audio_url": "/audio/x.wav"})
        mock_session.post = MagicMock(return_value=synth)

        await self._client(mock_session).speak("hi", zone="home")

        calls = mock_session.post.call_args_list
        voice_call = next(c for c in calls if "/api/voice/synthesize" in str(c[0][0]))
        event_call = next(c for c in calls if "/voice-events/" in str(c[0][0]))
        # Voice synth must NOT receive the backend key (internal token unset → no header).
        assert voice_call[1]["headers"] == {}
        # Backend voice-events log must receive the backend key.
        assert event_call[1]["headers"] == {"Authorization": "Bearer backendkey"}


class TestTaskReminderWiring:
    """``TaskReminder`` hits backend ``/tasks/`` directly (not via DashboardClient)."""

    def _reminder(self, mock_session):
        from task_reminder import TaskReminder

        return TaskReminder(dashboard_api_url="http://backend:8000", session=mock_session)

    @pytest.mark.asyncio
    async def test_fetch_tasks_sends_bearer(self, mock_session, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "rk")
        mock_session.get = MagicMock(return_value=mock_session._make_response(200, []))

        await self._reminder(mock_session).get_tasks_needing_reminder()

        mock_session.get.assert_called_once()
        assert mock_session.get.call_args[1]["headers"] == {"Authorization": "Bearer rk"}

    @pytest.mark.asyncio
    async def test_update_timestamp_sends_bearer(self, mock_session, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "rk")
        mock_session.put = MagicMock(return_value=mock_session._make_response(200, {}))

        await self._reminder(mock_session).update_reminder_timestamp(7)

        mock_session.put.assert_called_once()
        assert "/tasks/7/reminded" in str(mock_session.put.call_args[0][0])
        assert mock_session.put.call_args[1]["headers"] == {"Authorization": "Bearer rk"}

    @pytest.mark.asyncio
    async def test_no_header_when_unset(self, mock_session, monkeypatch):
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        mock_session.get = MagicMock(return_value=mock_session._make_response(200, []))

        await self._reminder(mock_session).get_tasks_needing_reminder()

        assert mock_session.get.call_args[1]["headers"] == {}


class TestCoreToolHandlersWiring:
    """``CoreToolHandlers`` shopping/voice-event paths bypass DashboardClient."""

    @pytest.mark.asyncio
    async def test_add_shopping_item_sends_bearer(self, tool_executor, mock_session, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "shopkey")
        mock_session.post = MagicMock(return_value=mock_session._make_response(200, {"id": 1}))

        await tool_executor._handle_add_shopping_item({"name": "milk"})

        shop_call = next(c for c in mock_session.post.call_args_list if "/shopping/" in str(c[0][0]))
        assert shop_call[1]["headers"] == {"Authorization": "Bearer shopkey"}

    @pytest.mark.asyncio
    async def test_get_shopping_list_sends_bearer(self, tool_executor, mock_session, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "shopkey")
        mock_session.get = MagicMock(return_value=mock_session._make_response(200, []))

        await tool_executor._handle_get_shopping_list({})

        shop_call = next(c for c in mock_session.get.call_args_list if "/shopping/" in str(c[0][0]))
        assert shop_call[1]["headers"] == {"Authorization": "Bearer shopkey"}

    @pytest.mark.asyncio
    async def test_speak_voice_event_log_sends_bearer(self, tool_executor, mock_session, monkeypatch):
        """The direct ``/voice-events/`` POST in _handle_speak carries the backend key,
        while the voice-service synth call stays on HEMS_INTERNAL_TOKEN."""
        monkeypatch.setenv("BACKEND_API_KEY", "bk")
        monkeypatch.delenv("HEMS_INTERNAL_TOKEN", raising=False)
        tool_executor.persona_rewriter = None
        tool_executor.motion_retriever = None
        mock_session.post = MagicMock(return_value=mock_session._make_response(200, {"audio_url": "/a.wav"}))

        await tool_executor._handle_speak({"message": "hi", "zone": "home", "_skip_persona_rewrite": True})

        calls = mock_session.post.call_args_list
        synth_call = next(c for c in calls if "/api/voice/synthesize" in str(c[0][0]))
        event_call = next(c for c in calls if "/voice-events/" in str(c[0][0]))
        assert synth_call[1]["headers"] == {}
        assert event_call[1]["headers"] == {"Authorization": "Bearer bk"}


class TestVoiceCapsuleWiring:
    """voice_capsule persist + ack-learner play-log fetch hit admin mobile routes."""

    @pytest.mark.asyncio
    async def test_push_manifest_sends_bearer(self, mock_session, monkeypatch):
        from voice_capsule.persist import push_manifest

        monkeypatch.setenv("BACKEND_API_KEY", "mk")
        mock_session.post = MagicMock(return_value=mock_session._make_response(201, {}))

        await push_manifest(session=mock_session, backend_url="http://backend:8000", manifest={"id": "x"})

        call = mock_session.post.call_args
        assert "/mobile/voice-capsule" in str(call[0][0])
        assert call[1]["headers"] == {"Authorization": "Bearer mk"}

    @pytest.mark.asyncio
    async def test_fetch_play_logs_sends_bearer(self, mock_session, monkeypatch):
        from voice_capsule.ack_learner import AckLearner

        monkeypatch.setenv("BACKEND_API_KEY", "mk")
        mock_session.get = MagicMock(return_value=mock_session._make_response(200, []))
        learner = AckLearner(session=mock_session, backend_url="http://backend:8000")

        await learner._fetch_play_logs(since_days=7)

        call = mock_session.get.call_args
        assert "/mobile/voice-capsule/play-log" in str(call[0][0])
        assert call[1]["headers"] == {"Authorization": "Bearer mk"}
