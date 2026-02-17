"""
Tests for WorldModel service state integration — MQTT routing, LLM context, events.
"""
import time
import pytest


class TestWorldModelServiceRouting:
    """Test hems/services/{name}/* MQTT topic routing."""

    def test_service_status_update(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail",
            "available": True,
            "unread_count": 3,
            "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        ss = world_model.services_state
        assert "gmail" in ss.services
        assert ss.services["gmail"].unread_count == 3
        assert ss.services["gmail"].available is True

    def test_service_status_update_with_error(self, world_model):
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github",
            "available": False,
            "unread_count": 0,
            "summary": "GitHub接続エラー",
            "error": "API 401",
            "last_check": time.time(),
        })
        svc = world_model.services_state.services["github"]
        assert svc.available is False
        assert svc.error == "API 401"

    def test_multiple_services(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 2, "summary": "未読: 2通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github", "unread_count": 5, "summary": "通知: 5件",
            "last_check": time.time(),
        })
        ss = world_model.services_state
        assert len(ss.services) == 2
        assert ss.services["gmail"].unread_count == 2
        assert ss.services["github"].unread_count == 5

    def test_service_status_overwrite(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読: 3通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 1, "summary": "未読: 1通",
            "last_check": time.time(),
        })
        assert world_model.services_state.services["gmail"].unread_count == 1

    def test_service_event_topic(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/event", {
            "type": "unread_increased",
            "name": "gmail",
            "prev_count": 0,
            "new_count": 3,
            "summary": "未読メール: 3通",
        })
        events = world_model.services_state.events
        assert len(events) == 1
        assert events[0].event_type == "service_unread_increased"


class TestWorldModelServiceEvents:
    """Test event generation from service state changes."""

    def test_unread_increase_generates_event(self, world_model):
        # First update: 0 unread
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 0, "summary": "未読なし",
            "last_check": time.time(),
        })
        assert len(world_model.services_state.events) == 0

        # Second update: 3 unread (increase)
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        events = world_model.services_state.events
        assert len(events) == 1
        assert events[0].event_type == "service_unread_increase"
        assert "3通" in events[0].description

    def test_unread_decrease_no_event(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 5, "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 2, "last_check": time.time(),
        })
        # First creates an event (0→5), decrease should not
        assert len(world_model.services_state.events) == 1

    def test_same_unread_no_event(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "last_check": time.time(),
        })
        # Only one event from 0→3
        assert len(world_model.services_state.events) == 1

    def test_events_ring_buffer(self, world_model):
        for i in range(25):
            world_model.services_state.add_event(
                __import__("world_model.data_classes", fromlist=["Event"]).Event(
                    event_type="test", description=f"event_{i}",
                )
            )
        assert len(world_model.services_state.events) == 20  # max_events


class TestWorldModelServiceLLMContext:
    """Test services section in LLM context."""

    def test_no_services_section_when_empty(self, world_model):
        world_model.update_from_mqtt("office/living_room/sensor/temp1/temperature", {
            "temperature": 22.0,
        })
        ctx = world_model.get_llm_context()
        assert "サービス" not in ctx

    def test_services_section_when_data_exists(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "unread_count": 3, "summary": "未読メール: 3通",
            "last_check": time.time(),
        })
        world_model.update_from_mqtt("hems/services/github/status", {
            "name": "github", "unread_count": 0, "summary": "通知なし",
            "last_check": time.time(),
        })
        ctx = world_model.get_llm_context()
        assert "### サービス" in ctx
        assert "gmail: 未読メール: 3通" in ctx
        assert "github: 通知なし" in ctx

    def test_services_error_indicator(self, world_model):
        world_model.update_from_mqtt("hems/services/gmail/status", {
            "name": "gmail", "available": False, "summary": "Gmail接続エラー",
            "error": "timeout", "last_check": time.time(),
        })
        ctx = world_model.get_llm_context()
        assert "⚠" in ctx
        assert "Gmail接続エラー" in ctx
