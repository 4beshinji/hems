#!/usr/bin/env python3
"""
HEMS Demo Seed Extras — seed_demo.py に追加して、
timeseries / automations / scenes など見栄え用データを補完する。
"""

import argparse
import math
from datetime import UTC, datetime, timedelta

import requests


def seed_extras(base: str):
    h = {"Content-Type": "application/json"}

    def post(path, data):
        r = requests.post(f"{base}{path}", headers=h, json=data, timeout=15)
        print(f"  POST {path} → {r.status_code}", r.text[:120] if r.status_code >= 400 else "")
        return r

    # --- Timeseries (24h, 5min interval = 288 points/metric) ---
    print("\n[Timeseries] 24h × 6 metrics × 3 zones")
    now = datetime.now(UTC)
    points = []
    for i in range(288):
        # Walk back from now
        t = now - timedelta(minutes=5 * (288 - i))
        iso = t.isoformat()
        phase = i / 288 * 2 * math.pi  # daily cycle
        # Temperature: 19-25 sinusoid + small noise
        for zone, base_t in [("living_room", 22.5), ("bedroom", 21.0), ("kitchen", 23.5)]:
            temp = base_t + 2.0 * math.sin(phase - math.pi / 2) + 0.3 * math.sin(phase * 7)
            points.append({"metric": "temperature", "value": round(temp, 2), "zone": zone, "recorded_at": iso})
            hum = 50 + 8 * math.sin(phase + 1.0) + 0.5 * math.sin(phase * 5)
            points.append({"metric": "humidity", "value": round(hum, 1), "zone": zone, "recorded_at": iso})
            co2 = 500 + 250 * max(0, math.sin(phase - 0.5)) + 80 * math.sin(phase * 3)
            points.append({"metric": "co2", "value": round(co2, 0), "zone": zone, "recorded_at": iso})
        # Heart rate (single)
        hr = 70 + 12 * math.sin(phase) + 5 * math.sin(phase * 11)
        points.append({"metric": "heart_rate", "value": round(hr, 0), "zone": None, "recorded_at": iso})
        # CPU usage
        cpu = 30 + 20 * max(0, math.sin(phase - 0.3)) + 5 * math.sin(phase * 13)
        points.append({"metric": "cpu_usage", "value": round(cpu, 1), "zone": None, "recorded_at": iso})
        # Power consumption
        pw = 350 + 200 * max(0, math.sin(phase - 0.2))
        points.append({"metric": "power", "value": round(pw, 0), "zone": None, "recorded_at": iso})

    # Send in chunks of 500
    for i in range(0, len(points), 500):
        chunk = points[i : i + 500]
        post("/timeseries/ingest", {"points": chunk})
    print(f"  → seeded {len(points)} points")

    # --- Automations ---
    print("\n[Automations]")
    rules = [
        {
            "name": "高CO2換気アラート",
            "description": "リビングのCO2が1000ppmを超えたら換気を促す",
            "enabled": True,
            "trigger_type": "sensor_threshold",
            "trigger_config": {
                "device_id": "sensor.living_room_co2",
                "channel": "co2",
                "op": ">",
                "value": 1000,
                "zone": "living_room",
            },
            "actions": [
                {
                    "device_id": "speak",
                    "action": "speak",
                    "params": {"text": "CO2が高くなっています。換気をおすすめします。"},
                    "delay_s": 0,
                },
            ],
            "cooldown_s": 600,
            "mode": "direct",
            "require_confirm": False,
        },
        {
            "name": "就寝時刻の照明オフ",
            "description": "23:30に全照明を消す",
            "enabled": True,
            "trigger_type": "schedule",
            "trigger_config": {"cron": "30 23 * * *"},
            "actions": [
                {"device_id": "ha.light.living_room", "action": "turnOff", "params": {}, "delay_s": 0},
                {"device_id": "ha.light.bedroom", "action": "turnOff", "params": {}, "delay_s": 5},
            ],
            "cooldown_s": 3600,
            "mode": "direct",
            "require_confirm": False,
        },
        {
            "name": "起床ルーチン",
            "description": "起床検知時にカーテンを開けてニュースを読み上げる",
            "enabled": True,
            "trigger_type": "event",
            "trigger_config": {"event": "wake_up"},
            "actions": [
                {"device_id": "ha.cover.bedroom", "action": "open", "params": {}, "delay_s": 0},
                {
                    "device_id": "speak",
                    "action": "speak",
                    "params": {"text": "おはようございます。本日のニュースをお伝えします。"},
                    "delay_s": 30,
                },
            ],
            "cooldown_s": 21600,
            "mode": "direct",
            "require_confirm": False,
        },
        {
            "name": "在宅復帰エアコン起動",
            "description": "玄関センサーが反応したらエアコンを起動",
            "enabled": False,
            "trigger_type": "device_state",
            "trigger_config": {"device_id": "zigbee.entrance_motion", "state_key": "occupancy", "state_value": True},
            "actions": [
                {
                    "device_id": "ha.climate.living_room",
                    "action": "set_mode",
                    "params": {"mode": "auto", "temperature": 24},
                    "delay_s": 0,
                },
            ],
            "cooldown_s": 1800,
            "mode": "llm_review",
            "require_confirm": True,
        },
    ]
    for rule in rules:
        post("/automations/", rule)

    # --- Scenes ---
    print("\n[Scenes]")
    scenes = [
        {
            "name": "movie_night",
            "display_name": "映画モード",
            "description": "リビングを暗くして映画鑑賞モードに",
            "actions": [
                {
                    "device_id": "ha.light.living_room",
                    "action": "set_brightness",
                    "params": {"brightness": 30},
                    "delay_s": 0,
                },
                {"device_id": "ha.cover.living_room", "action": "close", "params": {}, "delay_s": 0},
            ],
            "is_enabled": True,
        },
        {
            "name": "focus_work",
            "display_name": "集中モード",
            "description": "作業効率最大化",
            "actions": [
                {
                    "device_id": "ha.light.living_room",
                    "action": "set_brightness",
                    "params": {"brightness": 255, "color_temp": 250},
                    "delay_s": 0,
                },
            ],
            "is_enabled": True,
        },
        {
            "name": "good_night",
            "display_name": "就寝モード",
            "description": "全消灯+カーテン閉",
            "actions": [
                {"device_id": "ha.light.living_room", "action": "turnOff", "params": {}, "delay_s": 0},
                {"device_id": "ha.light.kitchen", "action": "turnOff", "params": {}, "delay_s": 0},
                {"device_id": "ha.cover.bedroom", "action": "close", "params": {}, "delay_s": 0},
            ],
            "is_enabled": True,
        },
    ]
    for s in scenes:
        post("/scenes/", s)

    # --- Voice events (more variety) ---
    print("\n[Voice Events extra]")
    extras = [
        {
            "message": "デスクから2時間離れていません。少し体を動かしましょう。",
            "tone": "caring",
            "audio_url": "",
            "zone": "living_room",
        },
        {"message": "今日は記録的な暑さになる予報です！", "tone": "alert", "audio_url": "", "zone": None},
        {
            "message": "Pull Request #42 がマージされました。お疲れさまです。",
            "tone": "humorous",
            "audio_url": "",
            "zone": None,
        },
        {
            "message": "気圧が急降下しています。頭痛が出るかもしれません。",
            "tone": "caring",
            "audio_url": "",
            "zone": None,
        },
        {"message": "今日のタスクは8件、完了は3件です。", "tone": "neutral", "audio_url": "", "zone": None},
    ]
    for ve in extras:
        post("/voice-events/", ve)

    # --- Conversations / Chat history ---
    print("\n[Chat conversations]")
    conv = post("/chat/", {"content": "こんにちは、今日のスケジュールを教えて", "tts": False, "conversation_id": None})
    if conv.ok:
        cid = conv.json().get("conversation_id")
        if cid:
            post(
                "/chat/",
                {"content": "了解。買い物のリマインドを18時にお願いします。", "tts": False, "conversation_id": cid},
            )

    print("\n✓ Extra demo data seeded.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8010")
    args = parser.parse_args()
    seed_extras(args.url)
