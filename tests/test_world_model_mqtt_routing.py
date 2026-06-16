"""
Regression tests for WorldModel MQTT routing branches split into mixins.
"""


def test_routes_weather_current_to_physical_weather(world_model):
    world_model.update_from_mqtt(
        "hems/weather/current",
        {"condition": "rainy", "temperature": 18.5, "humidity": 80, "wind_speed": 5.2},
    )

    assert world_model.physical.weather.condition == "rainy"
    assert world_model.weather.temperature == 18.5
    assert world_model.weather.humidity == 80.0
    assert world_model.weather.wind_speed == 5.2
    assert world_model.weather.last_update > 0


def test_routes_news_daily_to_digital_news_state(world_model):
    world_model.update_from_mqtt(
        "hems/news/daily",
        {"summary": "今日の要約", "chunks": ["one", "two"], "article_count": 2, "timestamp": 123.0},
    )

    assert world_model.digital.news_state.daily_summary == "今日の要約"
    assert world_model.news_state.daily_chunks == ["one", "two"]
    assert world_model.news_state.daily_timestamp == 123.0
    assert world_model.news_state.events[-1].event_type == "news_daily"


def test_routes_news_urgent_to_digital_news_state(world_model):
    world_model.update_from_mqtt(
        "hems/news/urgent",
        {"title": "速報", "summary": "details", "score": 0.9, "source": "wire", "url": "https://example.test"},
    )

    assert world_model.news_state.urgent_articles[-1]["title"] == "速報"
    assert world_model.news_state.urgent_articles[-1]["score"] == 0.9
    assert world_model.news_state.events[-1].event_type == "news_urgent"


def test_routes_personal_notes_to_knowledge_state(world_model):
    world_model.update_from_mqtt("hems/personal/notes/stats", {"total_notes": 10, "indexed": 8})
    world_model.update_from_mqtt(
        "hems/personal/notes/changed",
        {"path": "daily.md", "title": "Daily", "action": "modified"},
    )

    assert world_model.knowledge_state.bridge_connected is True
    assert world_model.knowledge_state.total_notes == 10
    assert world_model.knowledge_state.indexed == 8
    assert world_model.knowledge_state.recent_changes[-1]["title"] == "Daily"
    assert world_model.knowledge_state.events[-1].event_type == "note_changed"


def test_routes_personal_knowledge_to_knowledge_state(world_model):
    world_model.update_from_mqtt(
        "hems/personal/knowledge/stats",
        {"total_docs": 4, "sources": [{"name": "research", "doc_count": 4, "type_counts": {"markdown": 3}}]},
    )
    world_model.update_from_mqtt(
        "hems/personal/knowledge/changed",
        {"title": "Paper", "source": "research", "action": "created"},
    )

    assert world_model.knowledge_state.external_bridge_connected is True
    assert world_model.knowledge_state.external_total_docs == 4
    assert world_model.knowledge_state.external_sources[0].name == "research"
    assert world_model.knowledge_state.events[-1].event_type == "knowledge_changed"


def test_routes_tapo_state_to_zone_event(world_model):
    world_model.update_from_mqtt("hems/tapo/plug_desk/state", {"zone": "office", "power_watts": 42.5})

    event = world_model.zones["office"].events[-1]
    assert event.event_type == "tapo_power"
    assert event.data["vendor_ref"] == "plug_desk"
    assert event.data["power_watts"] == 42.5


def test_routes_task_report_to_zone_event(world_model):
    world_model.update_from_mqtt(
        "office/kitchen/task_report/task-1",
        {"title": "換気する", "report_status": "needs_followup"},
    )

    event = world_model.zones["kitchen"].events[-1]
    assert event.event_type == "task_report"
    assert event.severity == 1
    assert "換気する" in event.description


# ---------------------------------------------------------------------------
# W3.3: bridge status topic unification
# ---------------------------------------------------------------------------


class TestBridgeStatusRoutingW33:
    """New canonical topics and legacy compat topics both update bridge_connected."""

    # --- HA bridge ---

    def test_ha_canonical_topic_sets_bridge_connected(self, world_model):
        """hems/ha/bridge/status (new canonical) updates home_devices.bridge_connected."""
        world_model.update_from_mqtt(
            "hems/ha/bridge/status",
            {"connected": True, "mode": "websocket"},
        )
        assert world_model.home_devices.bridge_connected is True

    def test_ha_canonical_topic_disconnected(self, world_model):
        """connected=False in hems/ha/bridge/status clears bridge_connected."""
        world_model.home_devices.bridge_connected = True
        world_model.update_from_mqtt(
            "hems/ha/bridge/status",
            {"connected": False, "mode": "disconnected"},
        )
        assert world_model.home_devices.bridge_connected is False

    def test_ha_legacy_topic_still_works(self, world_model):
        """hems/home/bridge/status (legacy compat) still updates home_devices.bridge_connected."""
        world_model.update_from_mqtt(
            "hems/home/bridge/status",
            {"connected": True, "mode": "polling"},
        )
        assert world_model.home_devices.bridge_connected is True

    def test_ha_legacy_topic_disconnected(self, world_model):
        """connected=False via legacy topic clears bridge_connected."""
        world_model.home_devices.bridge_connected = True
        world_model.update_from_mqtt(
            "hems/home/bridge/status",
            {"connected": False},
        )
        assert world_model.home_devices.bridge_connected is False

    # --- Biometric bridge ---

    def test_biometric_canonical_topic_sets_bridge_connected(self, world_model):
        """hems/biometric/bridge/status (new canonical) updates biometric_state.bridge_connected."""
        world_model.update_from_mqtt(
            "hems/biometric/bridge/status",
            {"connected": True, "provider": "gadgetbridge", "active_providers": ["gadgetbridge"]},
        )
        assert world_model.biometric_state.bridge_connected is True
        assert world_model.biometric_state.provider == "gadgetbridge"

    def test_biometric_canonical_topic_disconnected(self, world_model):
        """connected=False in hems/biometric/bridge/status clears bridge_connected."""
        world_model.biometric_state.bridge_connected = True
        world_model.update_from_mqtt(
            "hems/biometric/bridge/status",
            {"connected": False},
        )
        assert world_model.biometric_state.bridge_connected is False

    def test_biometric_canonical_topic_no_provider_key(self, world_model):
        """hems/biometric/bridge/status without provider key leaves provider unchanged."""
        world_model.biometric_state.provider = "huami"
        world_model.update_from_mqtt(
            "hems/biometric/bridge/status",
            {"connected": True},
        )
        assert world_model.biometric_state.bridge_connected is True
        assert world_model.biometric_state.provider == "huami"

    def test_biometric_legacy_topic_still_works(self, world_model):
        """hems/personal/biometrics/bridge/status (legacy compat) updates biometric_state.bridge_connected."""
        world_model.update_from_mqtt(
            "hems/personal/biometrics/bridge/status",
            {"connected": True, "provider": "zepp"},
        )
        assert world_model.biometric_state.bridge_connected is True
        assert world_model.biometric_state.provider == "zepp"

    def test_biometric_legacy_topic_disconnected(self, world_model):
        """connected=False via legacy topic clears bridge_connected."""
        world_model.biometric_state.bridge_connected = True
        world_model.update_from_mqtt(
            "hems/personal/biometrics/bridge/status",
            {"connected": False, "provider": ""},
        )
        assert world_model.biometric_state.bridge_connected is False


# ---------------------------------------------------------------------------
# W3.8a: hems/sensors/* concurrent read (migration compatibility)
# ---------------------------------------------------------------------------


class TestSensorsCanonicalW38c:
    """W3.8c: hems/sensors/* is the only prefix processed for physical telemetry.

    Legacy office/* sensor/camera/activity topics are ignored after the
    migration window closes.
    """

    # --- sensor/analog ---

    def test_canonical_prefix_temperature_updates_zone_environment(self, world_model):
        """hems/sensors/{zone}/sensor/{id}/{ch} updates zone environment."""
        world_model.update_from_mqtt(
            "hems/sensors/living/sensor/esp32_001/temperature",
            {"temperature": 24.5},
        )
        assert world_model.zones["living"].environment.temperature == 24.5

    def test_legacy_prefix_sensor_is_ignored(self, world_model):
        """office/{zone}/sensor/{id}/{ch} no longer updates world model."""
        world_model.update_from_mqtt(
            "office/living/sensor/esp32_001/temperature",
            {"temperature": 24.5},
        )
        assert "living" not in world_model.zones

    def test_canonical_prefix_invalid_value_rejected(self, world_model):
        """hems/sensors/* enforces the input-trust-boundary."""
        world_model.update_from_mqtt(
            "hems/sensors/living/sensor/esp32_001/temperature",
            {"temperature": "DROP TABLE"},
        )
        # Validation rejects the value early (return before zone auto-create).
        # Zone should NOT be created by a rejected message.
        assert "living" not in world_model.zones

    # --- sensor/camera (occupancy) ---

    def test_canonical_prefix_camera_updates_occupancy_count(self, world_model):
        """hems/sensors/{zone}/camera/{id}/status updates occupancy count."""
        world_model.update_from_mqtt(
            "hems/sensors/living/camera/cam_01/status",
            {"person_count": 2},
        )
        assert world_model.zones["living"].occupancy.count == 2

    def test_legacy_prefix_camera_is_ignored(self, world_model):
        """office/{zone}/camera/{id}/status no longer updates occupancy."""
        world_model.update_from_mqtt(
            "office/living/camera/cam_01/status",
            {"person_count": 2},
        )
        assert "living" not in world_model.zones

    # --- sensor/activity ---

    def test_canonical_prefix_activity_class_updates_occupancy(self, world_model):
        """hems/sensors/{zone}/activity/{id} updates occupancy activity_class."""
        world_model.update_from_mqtt(
            "hems/sensors/living/activity/monitor_01",
            {"activity_class": "working", "posture": "sitting"},
        )
        assert world_model.zones["living"].occupancy.activity_class == "working"
        assert world_model.zones["living"].occupancy.posture == "sitting"

    def test_legacy_prefix_activity_is_ignored(self, world_model):
        """office/{zone}/activity/{id} no longer updates occupancy."""
        world_model.update_from_mqtt(
            "office/living/activity/monitor_01",
            {"activity_class": "working", "posture": "sitting"},
        )
        assert "living" not in world_model.zones
