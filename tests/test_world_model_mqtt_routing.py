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
