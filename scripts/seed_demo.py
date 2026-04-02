#!/usr/bin/env python3
"""
HEMS Demo Seed Script — バックエンドにダミーデータを投入する。

Usage:
    python scripts/seed_demo.py [--url http://localhost:8010] [--key change_me_...]

Backend + Frontend だけで見栄えのするダッシュボードを表示するためのスクリプト。
Brain / MQTT / Ollama は不要。
"""
import argparse
import json
import time
import random
import requests

def seed(base: str, key: str):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def post(path, data):
        r = requests.post(f"{base}{path}", headers=h, json=data, timeout=10)
        print(f"  POST {path} → {r.status_code}")
        return r

    def put(path, data=None):
        r = requests.put(f"{base}{path}", headers=h, json=data or {}, timeout=10)
        print(f"  PUT  {path} → {r.status_code}")
        return r

    now = time.time()

    # --- Zones (実空間) ---
    print("\n[Zones]")
    post("/zones/snapshot", {"zones": [
        {
            "zone_id": "living_room",
            "environment": {
                "temperature": 23.5, "humidity": 48, "co2": 620,
                "pressure": 1013.2, "light": 450, "voc": 85,
                "last_update": now,
            },
            "occupancy": {"count": 1, "last_update": now},
            "events": [],
        },
        {
            "zone_id": "bedroom",
            "environment": {
                "temperature": 21.8, "humidity": 52, "co2": 480,
                "pressure": 1013.1, "light": 20, "voc": 60,
                "last_update": now,
            },
            "occupancy": {"count": 0, "last_update": now},
            "events": [],
        },
        {
            "zone_id": "kitchen",
            "environment": {
                "temperature": 25.1, "humidity": 55, "co2": 710,
                "pressure": 1013.0, "light": 600, "voc": 150,
                "last_update": now,
            },
            "occupancy": {"count": 0, "last_update": now},
            "events": [],
        },
    ]})

    # --- PC Metrics (個人電子空間) ---
    print("\n[PC Metrics]")
    post("/pc/snapshot", {
        "cpu": {"usage_percent": 34.2, "temperature": 58},
        "memory": {"used_gb": 12.4, "total_gb": 32.0, "percent": 38.8},
        "gpu": {"usage_percent": 22, "temperature": 52, "vram_used_gb": 3.2, "vram_total_gb": 12.0},
        "disks": [
            {"mount": "/", "used_gb": 180, "total_gb": 500, "percent": 36},
            {"mount": "/home", "used_gb": 420, "total_gb": 1000, "percent": 42},
        ],
        "top_processes": [
            {"name": "ollama", "cpu": 15.2, "memory_mb": 4200},
            {"name": "chrome", "cpu": 8.5, "memory_mb": 2800},
            {"name": "code", "cpu": 5.1, "memory_mb": 1500},
            {"name": "python", "cpu": 3.8, "memory_mb": 900},
            {"name": "docker", "cpu": 2.1, "memory_mb": 600},
        ],
        "last_update": now,
    })

    # --- Services (デジタル空間) ---
    print("\n[Services]")
    post("/services/snapshot", {
        "items": [
            {"name": "Gmail", "status": "ok", "unread": 3, "last_check": now},
            {"name": "GitHub", "status": "ok", "unread": 5, "last_check": now},
        ],
        "last_update": now,
    })

    # --- Biometric (ユーザー状態) ---
    print("\n[Biometric]")
    post("/biometric/snapshot", {
        "provider": "gadgetbridge",
        "heart_rate": 72,
        "resting_heart_rate": 62,
        "spo2": 98,
        "steps": 4520,
        "calories": 280,
        "active_minutes": 35,
        "stress_level": 32,
        "fatigue_score": 25,
        "sleep_duration_minutes": 420,
        "sleep_quality_score": 82,
        "hrv_ms": 48,
        "body_temperature": 36.5,
        "respiratory_rate": 16,
        "bridge_connected": True,
        "last_update": now,
    })

    # --- Perception (カメラ) ---
    print("\n[Perception]")
    post("/perception/snapshot", {
        "zones": {
            "living_room": {
                "person_count": 1,
                "poses": ["sitting"],
                "activity_level": 0.3,
                "last_update": now,
            },
        },
        "vlm": {
            "living_room": {
                "description": "デスクに向かって作業中。モニター2台が点灯。コーヒーカップがデスク上にある。",
                "model": "moondream",
                "last_update": now,
            },
        },
        "bridge_connected": True,
        "last_update": now,
    })

    # --- Knowledge (Obsidian) ---
    print("\n[Knowledge]")
    post("/knowledge/snapshot", {
        "total_notes": 342,
        "indexed": 342,
        "recent_changes": [
            {"title": "2026-03-27 daily note", "action": "modified", "timestamp": now - 3600},
            {"title": "HEMS/decisions/climate-rule-update", "action": "created", "timestamp": now - 7200},
            {"title": "Reading list", "action": "modified", "timestamp": now - 14400},
        ],
        "bridge_connected": True,
        "last_update": now,
    })

    # --- GAS (Google) ---
    print("\n[GAS]")
    post("/gas/snapshot", {
        "calendar": {
            "upcoming": [
                {"title": "Weekly standup", "start": "2026-03-27T10:00:00", "end": "2026-03-27T10:30:00"},
                {"title": "Dentist", "start": "2026-03-27T14:00:00", "end": "2026-03-27T15:00:00"},
                {"title": "Gym", "start": "2026-03-27T18:00:00", "end": "2026-03-27T19:30:00"},
            ],
            "free_slots": 4,
        },
        "tasks": {
            "due_today": 2,
            "overdue": 0,
            "total": 8,
        },
        "gmail": {
            "unread": 3,
            "last_update": now,
        },
        "bridge_connected": True,
        "last_update": now,
    })

    # --- Home (スマートホーム) ---
    print("\n[Home]")
    post("/home/snapshot", {
        "lights": [
            {"entity_id": "light.living_room", "name": "リビング照明", "state": "on",
             "brightness": 200, "color_temp": 370},
            {"entity_id": "light.bedroom", "name": "寝室照明", "state": "off",
             "brightness": 0},
            {"entity_id": "light.kitchen", "name": "キッチン照明", "state": "on",
             "brightness": 255, "color_temp": 300},
        ],
        "climate": [
            {"entity_id": "climate.living_room", "name": "リビング エアコン",
             "state": "cool", "current_temperature": 23.5, "target_temperature": 24,
             "fan_mode": "auto"},
        ],
        "covers": [
            {"entity_id": "cover.living_room", "name": "リビング カーテン",
             "state": "open", "position": 100},
            {"entity_id": "cover.bedroom", "name": "寝室 カーテン",
             "state": "closed", "position": 0},
        ],
        "sensors": [
            {"entity_id": "sensor.power_consumption", "name": "消費電力",
             "state": "450", "unit": "W"},
        ],
        "bridge_connected": True,
        "last_update": now,
    })

    # --- Tasks ---
    print("\n[Tasks]")
    tasks = [
        {"title": "CO2 濃度が上昇 — 換気を推奨", "description": "リビングの CO2 が 620ppm。窓を開けて換気してください。",
         "zone": "living_room", "urgency": 2, "task_type": ["environment"]},
        {"title": "長時間座位を検知 — 休憩推奨", "description": "2時間以上座り続けています。軽いストレッチを推奨します。",
         "zone": "living_room", "urgency": 3, "task_type": ["health"]},
        {"title": "GitHub PR レビュー 5件", "description": "未読の Pull Request レビューリクエストがあります。",
         "zone": None, "urgency": 1, "task_type": ["digital"]},
        {"title": "牛乳を買う", "description": "買い物リストに牛乳が追加されました。帰宅時に購入を推奨。",
         "zone": None, "urgency": 1, "task_type": ["shopping"]},
        {"title": "エアコンフィルター清掃", "description": "前回の清掃から 30 日経過。フィルター掃除を推奨します。",
         "zone": "living_room", "urgency": 1, "task_type": ["maintenance"]},
    ]
    for t in tasks:
        post("/tasks/", t)

    # Complete a couple of old tasks for stats
    r = requests.get(f"{base}/tasks/", headers=h, timeout=10)
    if r.ok:
        all_tasks = r.json()
        for t in all_tasks[:2]:
            put(f"/tasks/{t['id']}/complete", {"completion_note": "自動完了"})

    # --- Voice Events ---
    print("\n[Voice Events]")
    voice_events = [
        {"message": "おはようございます。本日の天気は晴れ、最高気温 22 度です。午後から雨の予報があるので傘をお忘れなく。",
         "zone": "living_room", "tone": "greeting", "audio_url": ""},
        {"message": "GitHub に PR レビューが 5 件溜まっています。",
         "zone": "living_room", "tone": "info", "audio_url": ""},
        {"message": "リビングの CO2 濃度が上昇しています。換気を推奨します。",
         "zone": "living_room", "tone": "warning", "audio_url": ""},
        {"message": "2 時間座り続けています。少し体を動かしましょう。",
         "zone": "living_room", "tone": "gentle", "audio_url": ""},
    ]
    for ve in voice_events:
        post("/voice-events/", ve)

    # --- Shopping ---
    print("\n[Shopping]")
    items = [
        {"name": "牛乳", "category": "乳製品", "quantity": 1, "unit": "本", "store": "ライフ", "price": 220, "priority": 2},
        {"name": "食パン", "category": "パン", "quantity": 1, "unit": "斤", "store": "ライフ", "price": 180, "priority": 2},
        {"name": "コーヒー豆", "category": "飲料", "quantity": 1, "unit": "袋", "store": "カルディ", "price": 850, "priority": 1,
         "is_recurring": True, "recurrence_days": 14},
        {"name": "洗剤", "category": "日用品", "quantity": 1, "unit": "本", "store": "ドラッグストア", "price": 350, "priority": 1},
        {"name": "鶏胸肉", "category": "肉", "quantity": 2, "unit": "パック", "store": "ライフ", "price": 480, "priority": 2},
    ]
    for item in items:
        post("/shopping/", item)

    print("\n✓ Demo data seeded successfully.")
    print(f"  Dashboard: http://localhost:8080")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed HEMS with demo data")
    parser.add_argument("--url", default="http://localhost:8010", help="Backend URL")
    parser.add_argument("--key", default="change_me_generate_with_openssl_rand_hex_32", help="API key")
    args = parser.parse_args()
    seed(args.url, args.key)
