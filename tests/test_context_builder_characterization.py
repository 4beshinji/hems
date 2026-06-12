"""
Characterization tests for WorldModel._get_physical_context.

These tests golden-lock the current behaviour of _get_physical_context so that
the planned C2 refactor (splitting the ~257-line method) cannot silently change
its output.  All assertions are against the string returned by
_get_physical_context directly, not the full get_llm_context wrapper.

Strategy: structural assertion — each test checks which section headers/lines
ARE present and which are absent, plus exact key phrases.  This is stronger
than a substring scan alone but more resilient than a full byte-for-byte match
when irrelevant whitespace evolves.
"""

import time

import pytest

from world_model.data_classes import (
    BinarySensorState,
    ClimateState,
    CoverState,
    EnvironmentData,
    HASensorState,
    HomeDevicesState,
    LightState,
    OccupancyData,
    WeatherAlert,
    WeatherState,
    ZoneState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_zone(wm, zone_id: str, **env_kwargs) -> ZoneState:
    """Add a zone to world_model with specified EnvironmentData kwargs."""
    zone = wm._get_zone(zone_id)
    env_data = {k: v for k, v in env_kwargs.items() if k in EnvironmentData.__dataclass_fields__}
    occ_data = {k: v for k, v in env_kwargs.items() if k in OccupancyData.__dataclass_fields__}
    if env_data:
        zone.environment = EnvironmentData(**env_data)
    if occ_data:
        zone.occupancy = OccupancyData(**occ_data)
    return zone


# ---------------------------------------------------------------------------
# Scenario 1 — Completely empty world model
# ---------------------------------------------------------------------------


class TestEmptyWorldModel:
    """When no zones, no home devices, no weather — context should be empty."""

    def test_empty_returns_empty_string(self, world_model):
        result = world_model._get_physical_context()
        assert result == ""

    def test_no_zone_section(self, world_model):
        result = world_model._get_physical_context()
        assert "###" not in result

    def test_no_smartHome_section(self, world_model):
        result = world_model._get_physical_context()
        assert "スマートホーム" not in result

    def test_no_weather_section(self, world_model):
        result = world_model._get_physical_context()
        assert "天気" not in result


# ---------------------------------------------------------------------------
# Scenario 2 — Single zone, all sensors present, fresh data
# ---------------------------------------------------------------------------


class TestSingleZoneAllSensors:
    """Zone with all sensor channels populated and fresh timestamps."""

    @pytest.fixture
    def ctx(self, world_model):
        now = time.time()
        zone = world_model._get_zone("living_room")
        zone.environment = EnvironmentData(
            temperature=23.5,
            humidity=55.0,
            co2=750.0,
            pressure=1013.0,
            light=300.0,
            voc=120.0,
            pm25=8.0,
            soil_moisture=40.0,
            last_update=now,
            channel_last_seen={
                "temperature": now,
                "humidity": now,
                "co2": now,
            },
        )
        return world_model._get_physical_context()

    def test_zone_header_present(self, ctx):
        assert "### living_room" in ctx

    def test_sensors_summary_line_present(self, ctx):
        assert "sensors:" in ctx

    def test_temperature_in_sensors_summary(self, ctx):
        assert "temp 23.5C" in ctx

    def test_humidity_in_sensors_summary(self, ctx):
        assert "hum 55%" in ctx

    def test_pressure_in_sensors_summary(self, ctx):
        assert "pressure 1013hPa" in ctx

    def test_voc_in_sensors_summary(self, ctx):
        assert "voc 120" in ctx

    def test_pm25_in_sensors_summary(self, ctx):
        assert "pm25 8" in ctx

    def test_light_in_sensors_summary(self, ctx):
        assert "light 300lx" in ctx

    def test_soil_in_sensors_summary(self, ctx):
        assert "soil 40%" in ctx

    def test_temperature_detail_line(self, ctx):
        assert "温度: 23.5度" in ctx
        assert "comfortable" in ctx

    def test_humidity_detail_line(self, ctx):
        assert "湿度: 55.0%" in ctx

    def test_co2_detail_line(self, ctx):
        assert "CO2: 750ppm" in ctx

    def test_co2_no_stuffy_flag_when_below_threshold(self, ctx):
        assert "換気推奨" not in ctx

    def test_no_stale_warning_for_fresh_data(self, ctx):
        assert "古い" not in ctx


# ---------------------------------------------------------------------------
# Scenario 3 — Sensor subset missing (only temperature + humidity)
# ---------------------------------------------------------------------------


class TestPartialSensors:
    """Channels that are None must not appear in either summary or detail."""

    @pytest.fixture
    def ctx(self, world_model):
        now = time.time()
        zone = world_model._get_zone("bedroom")
        zone.environment = EnvironmentData(
            temperature=20.0,
            humidity=60.0,
            # co2, pressure, light, voc, pm25, soil_moisture all None
            last_update=now,
        )
        return world_model._get_physical_context()

    def test_zone_header_present(self, ctx):
        assert "### bedroom" in ctx

    def test_temperature_present(self, ctx):
        assert "temp 20.0C" in ctx

    def test_humidity_present(self, ctx):
        assert "hum 60%" in ctx

    def test_co2_absent(self, ctx):
        assert "CO2:" not in ctx

    def test_pressure_absent(self, ctx):
        assert "pressure" not in ctx

    def test_voc_absent_in_summary(self, ctx):
        assert "voc" not in ctx

    def test_pm25_absent_in_summary(self, ctx):
        assert "pm25" not in ctx

    def test_light_absent_in_summary(self, ctx):
        assert "light" not in ctx

    def test_soil_absent_in_summary(self, ctx):
        assert "soil" not in ctx


# ---------------------------------------------------------------------------
# Scenario 4 — Stale zone data
# ---------------------------------------------------------------------------


class TestStaleZoneData:
    """When last_update is old, a stale warning appears per channel."""

    @pytest.fixture
    def ctx(self, world_model):
        stale_ts = time.time() - 700  # 700s > ENV_STALE_SEC default 300s
        zone = world_model._get_zone("kitchen")
        zone.environment = EnvironmentData(
            temperature=25.0,
            humidity=70.0,
            last_update=stale_ts,
            channel_last_seen={
                "temperature": stale_ts,
                "humidity": stale_ts,
            },
        )
        return world_model._get_physical_context()

    def test_stale_zone_banner_present(self, ctx):
        # Zone-level stale banner (⚠️ データ更新なし)
        assert "データ更新なし" in ctx

    def test_stale_age_suffix_on_temp(self, ctx):
        # Inline stale note on temperature channel
        assert "古い" in ctx

    def test_temperature_still_shown(self, ctx):
        assert "温度: 25.0度" in ctx


# ---------------------------------------------------------------------------
# Scenario 5 — CO2 stuffy + suppressed
# ---------------------------------------------------------------------------


class TestCO2Stuffy:
    """CO2 > 1000ppm triggers 換気推奨 unless suppressed."""

    def test_co2_stuffy_flag(self, world_model):
        now = time.time()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(
            co2=1100.0,
            last_update=now,
            channel_last_seen={"co2": now},
        )
        ctx = world_model._get_physical_context()
        assert "換気推奨" in ctx

    def test_co2_stuffy_suppressed(self, world_model):
        now = time.time()
        zone = world_model._get_zone("office")
        zone.environment = EnvironmentData(
            co2=1100.0,
            last_update=now,
            channel_last_seen={"co2": now},
        )
        # Inject suppression
        world_model._suppressed_alerts[("office", "co2_high")] = now + 1000
        ctx = world_model._get_physical_context()
        assert "対応中" in ctx
        assert "換気推奨" not in ctx


# ---------------------------------------------------------------------------
# Scenario 6 — Temperature threshold suppressed / not suppressed
# ---------------------------------------------------------------------------


class TestTemperatureThreshold:
    """High-temp alert suppression adds (対応中) marker."""

    def test_temp_high_suppressed_marker(self, world_model):
        # Use the real default thresholds (temp_high=28 by default).
        # Override just what we need via env: temperature=30 > 28 → triggers.
        from rules.config import load_rule_thresholds
        from world_model import WorldModel

        wm = WorldModel(thresholds=load_rule_thresholds())
        now = time.time()
        zone = wm._get_zone("living_room")
        zone.environment = EnvironmentData(
            temperature=30.0,
            last_update=now,
            channel_last_seen={"temperature": now},
        )
        wm._suppressed_alerts[("living_room", "temp_high")] = now + 1000
        ctx = wm._get_physical_context()
        assert "対応中" in ctx

    def test_temp_high_not_suppressed_no_marker(self, world_model):
        from rules.config import load_rule_thresholds
        from world_model import WorldModel

        wm = WorldModel(thresholds=load_rule_thresholds())
        now = time.time()
        zone = wm._get_zone("living_room")
        zone.environment = EnvironmentData(
            temperature=30.0,
            last_update=now,
        )
        ctx = wm._get_physical_context()
        assert "対応中" not in ctx


# ---------------------------------------------------------------------------
# Scenario 7 — VLM model swap banner
# ---------------------------------------------------------------------------


class TestVLMModelSwapBanner:
    """vlm_model_swap_active triggers VLM banner at the top of physical context."""

    def test_vlm_banner_when_active(self, world_model):
        world_model.vlm_model_swap_active = True
        world_model._get_zone("room1").environment = EnvironmentData(temperature=22.0, last_update=time.time())
        ctx = world_model._get_physical_context()
        assert "VLMモデル切替中" in ctx
        assert "rule-basedモード" in ctx

    def test_no_vlm_banner_when_inactive(self, world_model):
        world_model.vlm_model_swap_active = False
        ctx = world_model._get_physical_context()
        assert "VLMモデル切替中" not in ctx


# ---------------------------------------------------------------------------
# Scenario 8 — Home devices (bridge connected)
# ---------------------------------------------------------------------------


class TestHomeDevicesSection:
    """When bridge_connected=True, スマートホーム section appears."""

    @pytest.fixture
    def wm_with_devices(self, world_model):
        hd = HomeDevicesState(bridge_connected=True)
        hd.lights["light.living_light"] = LightState(entity_id="light.living_light", on=True, brightness=200)
        hd.lights["light.bedroom_light"] = LightState(entity_id="light.bedroom_light", on=False, brightness=0)
        hd.climates["climate.ac"] = ClimateState(
            entity_id="climate.ac",
            mode="cool",
            target_temp=24.0,
            current_temp=27.5,
        )
        hd.covers["cover.curtain"] = CoverState(entity_id="cover.curtain", position=50)
        hd.switches["switch.fan"] = True
        hd.switches["switch.heater"] = False
        hd.binary_sensors["binary_sensor.leak"] = BinarySensorState(
            entity_id="binary_sensor.leak",
            state=True,
            device_class="moisture",
        )
        hd.sensors["sensor.power"] = HASensorState(
            entity_id="sensor.power",
            value=150.0,
            unit="W",
            device_class="power",
        )
        world_model.home_devices = hd
        return world_model

    def test_smartHome_section_header(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "### スマートホーム" in ctx

    def test_light_on_appears(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "living_light ON" in ctx

    def test_light_off_appears(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "bedroom_light OFF" in ctx

    def test_light_brightness_percent(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        # brightness 200/255 * 100 = 78%
        assert "78%" in ctx

    def test_climate_cool_mode(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "冷房" in ctx
        assert "24°C" in ctx
        assert "27.5" in ctx

    def test_cover_position(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "カーテン" in ctx
        assert "50%" in ctx

    def test_switch_on(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "fan ON" in ctx

    def test_switch_off(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "heater OFF" in ctx

    def test_moisture_sensor_alert(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "水漏れ" in ctx
        assert "検知" in ctx
        assert "⚠" in ctx

    def test_power_sensor(self, wm_with_devices):
        ctx = wm_with_devices._get_physical_context()
        assert "電力" in ctx
        assert "150W" in ctx

    def test_no_smartHome_when_bridge_disconnected(self, world_model):
        hd = HomeDevicesState(bridge_connected=False)
        hd.lights["light.x"] = LightState(entity_id="light.x", on=True)
        world_model.home_devices = hd
        ctx = world_model._get_physical_context()
        assert "スマートホーム" not in ctx


# ---------------------------------------------------------------------------
# Scenario 9 — Cover fully open / fully closed
# ---------------------------------------------------------------------------


class TestCoverEdgePositions:
    """Cover at 0%, 50%, and 100% maps to 閉 / N% / 全開."""

    @pytest.fixture
    def _ctx(self, world_model):
        def _make(position):
            from world_model import WorldModel

            wm = WorldModel()
            hd = HomeDevicesState(bridge_connected=True)
            hd.covers["cover.blind"] = CoverState(entity_id="cover.blind", position=position)
            wm.home_devices = hd
            return wm._get_physical_context()

        return _make

    def test_fully_closed(self, _ctx):
        assert "閉" in _ctx(0)

    def test_partially_open(self, _ctx):
        assert "50%" in _ctx(50)

    def test_fully_open(self, _ctx):
        assert "全開" in _ctx(100)


# ---------------------------------------------------------------------------
# Scenario 10 — Weather section
# ---------------------------------------------------------------------------


class TestWeatherSection:
    """Weather appears when last_update > 0 or alerts exist."""

    def test_weather_with_last_update(self, world_model):
        world_model.weather = WeatherState(
            condition="sunny",
            temperature=28.5,
            humidity=65.0,
            wind_speed=3.2,
            last_update=time.time(),
        )
        ctx = world_model._get_physical_context()
        assert "### 天気" in ctx
        assert "sunny" in ctx
        assert "28°C" in ctx
        assert "65%" in ctx
        assert "3.2m/s" in ctx

    def test_weather_alert_severe(self, world_model):
        world_model.weather = WeatherState(
            condition="rainy",
            temperature=15.0,
            humidity=80.0,
            wind_speed=8.0,
            last_update=time.time(),
            alerts=[
                WeatherAlert(
                    title="大雨警報",
                    severity="severe",
                    area="東京都",
                )
            ],
        )
        ctx = world_model._get_physical_context()
        assert "⚠ 警報[重大]" in ctx
        assert "大雨警報" in ctx
        assert "東京都" in ctx

    def test_weather_alert_moderate_no_warning_prefix(self, world_model):
        world_model.weather = WeatherState(
            condition="cloudy",
            temperature=20.0,
            humidity=70.0,
            wind_speed=2.0,
            last_update=time.time(),
            alerts=[
                WeatherAlert(
                    title="注意報",
                    severity="moderate",
                    area="",
                )
            ],
        )
        ctx = world_model._get_physical_context()
        # moderate severity — no ⚠ prefix
        assert "⚠ 警報" not in ctx
        assert "警報[中程度]" in ctx

    def test_no_weather_when_zero_update_and_no_alerts(self, world_model):
        # Default WeatherState has last_update=0 and no alerts
        ctx = world_model._get_physical_context()
        assert "天気" not in ctx

    def test_weather_alerts_only_without_last_update(self, world_model):
        """Alerts alone (no last_update) still render the weather section."""
        world_model.weather = WeatherState(
            condition="unknown",
            temperature=0,
            humidity=0,
            wind_speed=0,
            last_update=0,
            alerts=[WeatherAlert(title="竜巻注意情報", severity="minor")],
        )
        ctx = world_model._get_physical_context()
        assert "### 天気" in ctx
        assert "竜巻注意情報" in ctx


# ---------------------------------------------------------------------------
# Scenario 11 — Multiple zones, ordering
# ---------------------------------------------------------------------------


class TestMultipleZones:
    """Multiple zones each render their own ### header."""

    def test_two_zones_both_appear(self, world_model):
        now = time.time()
        for zone_id in ("room_a", "room_b"):
            zone = world_model._get_zone(zone_id)
            zone.environment = EnvironmentData(temperature=20.0, last_update=now)
        ctx = world_model._get_physical_context()
        assert "### room_a" in ctx
        assert "### room_b" in ctx

    def test_zone_order_preserved(self, world_model):
        now = time.time()
        for zone_id in ("alpha", "beta", "gamma"):
            zone = world_model._get_zone(zone_id)
            zone.environment = EnvironmentData(temperature=20.0, last_update=now)
        ctx = world_model._get_physical_context()
        pos_alpha = ctx.index("### alpha")
        pos_beta = ctx.index("### beta")
        pos_gamma = ctx.index("### gamma")
        assert pos_alpha < pos_beta < pos_gamma


# ---------------------------------------------------------------------------
# Scenario 12 — Occupancy in physical context
# ---------------------------------------------------------------------------


class TestOccupancyInPhysicalContext:
    """Occupancy count, activity, posture, motion, presence, door appear in zone block."""

    def test_occupancy_count(self, world_model):
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=2)
        ctx = world_model._get_physical_context()
        assert "在室: 2人" in ctx

    def test_activity_class_and_level(self, world_model):
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=1, activity_class="moderate", activity_level=0.7)
        ctx = world_model._get_physical_context()
        assert "活動: moderate (レベル0.7)" in ctx

    def test_posture_and_duration(self, world_model):
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(count=1, posture="sitting", posture_duration_sec=900)
        ctx = world_model._get_physical_context()
        assert "姿勢: sitting (15分)" in ctx

    def test_motion_event_count(self, world_model):
        zone = world_model._get_zone("hallway")
        zone.occupancy = OccupancyData(motion_event_count_5min=5)
        ctx = world_model._get_physical_context()
        assert "動体検知: 直近5分で5回" in ctx

    def test_presence_state_present(self, world_model):
        zone = world_model._get_zone("hallway")
        zone.occupancy = OccupancyData(presence_state=True, presence_duration_sec=120)
        ctx = world_model._get_physical_context()
        assert "在室センサー: 在室検知中 (2分間)" in ctx

    def test_presence_state_absent(self, world_model):
        zone = world_model._get_zone("hallway")
        zone.occupancy = OccupancyData(presence_state=False, presence_duration_sec=60)
        ctx = world_model._get_physical_context()
        assert "在室センサー: 不在 (1分間)" in ctx

    def test_door_state(self, world_model):
        zone = world_model._get_zone("entrance")
        zone.occupancy = OccupancyData(
            door_states={
                "front_door": {
                    "open": True,
                    "duration_sec": 300,
                    "changes_1h": 3,
                }
            }
        )
        ctx = world_model._get_physical_context()
        assert "ドア(front_door): 開放中 (5分間)" in ctx
        assert "[1h内 3回開閉]" in ctx

    def test_no_motion_line_when_zero(self, world_model):
        zone = world_model._get_zone("room")
        zone.occupancy = OccupancyData(motion_event_count_5min=0)
        ctx = world_model._get_physical_context()
        assert "動体検知" not in ctx


# ---------------------------------------------------------------------------
# Scenario 13 — VLM scene data freshness tiers
# ---------------------------------------------------------------------------


class TestVLMSceneTiers:
    """VLM data renders differently based on age (<300s / <1800s / ≥1800s)."""

    def test_fresh_vlm_scene_description(self, world_model):
        now = time.time()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            vlm_last_update=now - 100,  # 100s ago → fresh
            scene_description="人物が椅子に座っている",
            scene_objects=["椅子", "テーブル"],
            scene_anomalies=["窓が開いている"],
        )
        ctx = world_model._get_physical_context()
        assert "シーン:" in ctx
        assert "人物が椅子に座っている" in ctx
        assert "物体:" in ctx
        assert "異常検知:" in ctx
        assert "窓が開いている" in ctx

    def test_aged_vlm_scene_shows_prefix(self, world_model):
        now = time.time()
        zone = world_model._get_zone("living_room")
        zone.occupancy = OccupancyData(
            vlm_last_update=now - 600,  # 600s → aged (300<age<1800)
            scene_description="人物がいる",
            scene_objects=["ソファ"],
        )
        ctx = world_model._get_physical_context()
        assert "分前の観測" in ctx

    def test_stale_vlm_only_when_occupied(self, world_model):
        now = time.time()
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=1,  # occupied
            vlm_last_update=now - 2000,  # ≥1800s → stale
            scene_description="",
            scene_objects=["ベッド", "枕"],
        )
        ctx = world_model._get_physical_context()
        assert "VLM最終観測:" in ctx

    def test_stale_vlm_hidden_when_unoccupied(self, world_model):
        now = time.time()
        zone = world_model._get_zone("bedroom")
        zone.occupancy = OccupancyData(
            count=0,
            inferred_occupied=False,
            vlm_last_update=now - 2000,
            scene_objects=["ベッド"],
        )
        ctx = world_model._get_physical_context()
        assert "VLM最終観測:" not in ctx


# ---------------------------------------------------------------------------
# Scenario 14 — sensors summary line truncation
# ---------------------------------------------------------------------------


class TestSensorSummaryTruncation:
    """If the sensors summary exceeds 140 chars it is truncated with '…'."""

    def test_long_summary_truncated(self, world_model):
        now = time.time()
        zone = world_model._get_zone("zone1")
        zone.environment = EnvironmentData(
            temperature=23.0,
            humidity=55.0,
            pressure=1010.0,
            voc=200.0,
            pm25=15.0,
            light=500.0,
            soil_moisture=35.0,
            last_update=now,
        )
        ctx = world_model._get_physical_context()
        # Find the sensors: line
        sensors_line = next((l for l in ctx.splitlines() if l.strip().startswith("sensors:")), None)
        assert sensors_line is not None, "sensors: line missing"
        assert len(sensors_line) <= 140, f"sensors line not truncated: {len(sensors_line)}"
