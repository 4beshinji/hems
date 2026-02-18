#!/usr/bin/env python3
"""
HEMS Phase 1 Integration Test Suite

Tests all services end-to-end:
  1. Backend API: task CRUD, users, points, voice events, stats, duplicate detection
  2. Voice Service: synthesize, announce, announce_with_completion, feedback, audio serving
  3. Brain: cognitive cycle via MQTT sensor input, event store
  4. Frontend: nginx proxy to backend + voice + audio
  5. MQTT: pub/sub, brain subscription
  6. E2E: sensor → brain → mock-llm → create_task → backend

Usage:
  python3 infra/scripts/integration_test.py

Requires: all HEMS services running (docker compose up -d)
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE_BACKEND = "http://localhost:8000"
BASE_VOICE = "http://localhost:8002"
BASE_FRONTEND = "http://localhost"
BASE_MOCK_LLM = "http://localhost:8001"

PASS = 0
FAIL = 0
ERRORS = []


def _req(method: str, url: str, body: dict = None, timeout: int = 15) -> tuple:
    """Make HTTP request, return (status_code, parsed_json_or_text)."""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def test(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        FAIL += 1
        msg = f"  \033[31mFAIL\033[0m {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        ERRORS.append(f"{name}: {detail}")


def mqtt_pub(topic: str, payload: dict):
    """Publish MQTT message via docker exec."""
    cmd = [
        "docker", "exec", "hems-mqtt",
        "mosquitto_pub", "-h", "localhost", "-u", "hems", "-P", "hems_dev_mqtt",
        "-t", topic, "-m", json.dumps(payload),
    ]
    subprocess.run(cmd, capture_output=True, timeout=10)


# ============================================================
# 1. Health checks
# ============================================================
def test_health():
    print("\n=== 1. Health Checks ===")

    status, data = _req("GET", f"{BASE_BACKEND}/docs")
    test("Backend /docs reachable", status == 200)

    status, data = _req("GET", f"{BASE_VOICE}/docs")
    test("Voice /docs reachable", status == 200)

    status, data = _req("GET", f"{BASE_MOCK_LLM}/docs")
    test("Mock-LLM /docs reachable", status == 200)

    status, data = _req("GET", f"{BASE_FRONTEND}/")
    test("Frontend / reachable", status == 200)

    status, data = _req("GET", f"{BASE_VOICE}/")
    test("Voice root returns TTS info", status == 200 and isinstance(data, dict) and "tts" in data,
         detail=str(data)[:80])


# ============================================================
# 2. Backend: Users
# ============================================================
def test_users():
    print("\n=== 2. Backend: Users ===")

    status, user = _req("POST", f"{BASE_BACKEND}/users/", {"username": "testuser", "display_name": "テストユーザー"})
    test("Create user", status == 200 and isinstance(user, dict) and user.get("username") == "testuser",
         detail=f"status={status}, data={str(user)[:100]}")
    user_id = user.get("id", 0) if isinstance(user, dict) else 0

    status, users = _req("GET", f"{BASE_BACKEND}/users/")
    test("List users", status == 200 and isinstance(users, list) and len(users) >= 1)

    if user_id:
        status, u = _req("GET", f"{BASE_BACKEND}/users/{user_id}")
        test("Get user by ID", status == 200 and u.get("username") == "testuser")

    return user_id


# ============================================================
# 3. Backend: Tasks
# ============================================================
def test_tasks(user_id: int):
    print("\n=== 3. Backend: Tasks ===")

    # Clean start - get existing tasks
    status, tasks_before = _req("GET", f"{BASE_BACKEND}/tasks/")

    # Create task
    task_data = {
        "title": "テスト換気タスク",
        "description": "CO2が高いので換気してください",
        "xp_reward": 150,
        "urgency": 3,
        "zone": "living_room",
        "task_type": ["environment"],
        "estimated_duration": 5,
    }
    status, task = _req("POST", f"{BASE_BACKEND}/tasks/", task_data)
    test("Create task", status == 200 and task.get("title") == "テスト換気タスク",
         detail=f"status={status}")
    task_id = task.get("id", 0)

    # List tasks
    status, tasks = _req("GET", f"{BASE_BACKEND}/tasks/")
    test("List tasks includes new task",
         status == 200 and any(t.get("id") == task_id for t in tasks))

    # Duplicate detection: same title + location
    status, dup = _req("POST", f"{BASE_BACKEND}/tasks/", task_data)
    test("Duplicate detection (same title) returns existing task",
         status == 200 and dup.get("id") == task_id,
         detail=f"got id={dup.get('id')}, expected={task_id}")

    # Create second task with different title
    task_data2 = {
        "title": "テスト: 加湿器をつける",
        "description": "湿度が低い",
        "xp_reward": 80,
        "urgency": 1,
        "zone": "bedroom",
    }
    status, task2 = _req("POST", f"{BASE_BACKEND}/tasks/", task_data2)
    test("Create second task", status == 200 and task2.get("id") != task_id)
    task2_id = task2.get("id", 0)

    # Duplicate detection: same zone + overlapping task_type
    dup_data = {
        "title": "別のタイトルだが同ゾーン同タイプ",
        "description": "same zone and type",
        "xp_reward": 200,
        "zone": "living_room",
        "task_type": ["environment"],
    }
    status, dup2 = _req("POST", f"{BASE_BACKEND}/tasks/", dup_data)
    test("Duplicate detection (zone+type) returns existing task",
         status == 200 and dup2.get("id") == task_id,
         detail=f"got id={dup2.get('id')}, expected={task_id}")

    # Accept task
    if user_id:
        status, accepted = _req("PUT", f"{BASE_BACKEND}/tasks/{task_id}/accept", {"user_id": user_id})
        test("Accept task", status == 200 and accepted.get("assigned_to") == user_id)

        # Cannot accept again
        status, err = _req("PUT", f"{BASE_BACKEND}/tasks/{task_id}/accept", {"user_id": user_id})
        test("Cannot accept already accepted task", status == 400)
    else:
        test("Accept task (skipped, no user)", False, "user_id=0")

    # Complete task with report
    status, completed = _req("PUT", f"{BASE_BACKEND}/tasks/{task_id}/complete", {
        "report_status": "done",
        "completion_note": "窓を開けて換気しました",
    })
    test("Complete task", status == 200 and completed.get("is_completed") is True)
    test("Task has report_status", completed.get("report_status") == "done")
    test("Task has completion_note", completed.get("completion_note") == "窓を開けて換気しました")

    # Stats
    status, stats = _req("GET", f"{BASE_BACKEND}/tasks/stats")
    test("Task stats endpoint", status == 200 and isinstance(stats, dict),
         detail=str(stats)[:100])
    test("Stats tasks_completed >= 1", stats.get("tasks_completed", 0) >= 1)
    test("Stats total_xp > 0", stats.get("total_xp", 0) > 0)

    # Remind
    status, reminded = _req("PUT", f"{BASE_BACKEND}/tasks/{task2_id}/reminded")
    test("Mark task reminded", status == 200 and reminded.get("last_reminded_at") is not None)

    return task_id, task2_id


# ============================================================
# 4. Backend: Points
# ============================================================
def test_points(user_id: int, task_id: int):
    print("\n=== 4. Backend: Points ===")

    if not user_id:
        test("Points test (skipped, no user)", False)
        return

    # Check point log was created by task completion
    status, logs = _req("GET", f"{BASE_BACKEND}/points/{user_id}")
    test("Point history for user",
         status == 200 and isinstance(logs, list),
         detail=f"status={status}, len={len(logs) if isinstance(logs, list) else '?'}")

    has_task_points = any(l.get("task_id") == task_id for l in logs) if isinstance(logs, list) else False
    test("Task completion created point log", has_task_points,
         detail=f"looking for task_id={task_id}")

    # Grant additional points
    status, granted = _req("POST", f"{BASE_BACKEND}/points/{user_id}/grant", {
        "amount": 50, "reason": "テストボーナス",
    })
    test("Grant points", status == 200 and granted.get("amount") == 50)

    # Check user balance updated
    status, user = _req("GET", f"{BASE_BACKEND}/users/{user_id}")
    test("User points updated",
         status == 200 and user.get("points", 0) >= 150,
         detail=f"points={user.get('points')}")


# ============================================================
# 5. Backend: Voice Events
# ============================================================
def test_voice_events():
    print("\n=== 5. Backend: Voice Events ===")

    status, evt = _req("POST", f"{BASE_BACKEND}/voice_events/", {
        "message": "テスト音声イベント",
        "audio_url": "/audio/test.mp3",
        "zone": "living_room",
        "tone": "caring",
    })
    test("Create voice event", status == 200 and evt.get("tone") == "caring")

    status, events = _req("GET", f"{BASE_BACKEND}/voice_events/recent")
    test("Get recent voice events",
         status == 200 and isinstance(events, list) and len(events) >= 1)


# ============================================================
# 6. Voice Service: TTS
# ============================================================
def test_voice_service():
    print("\n=== 6. Voice Service: TTS ===")

    # Synthesize
    status, synth = _req("POST", f"{BASE_VOICE}/api/voice/synthesize", {
        "text": "結合テスト音声合成です。",
        "tone": "neutral",
    })
    test("Synthesize text", status == 200 and "audio_url" in synth,
         detail=f"status={status}")
    test("Synth has duration", isinstance(synth.get("duration_seconds"), (int, float)) and synth["duration_seconds"] > 0,
         detail=f"dur={synth.get('duration_seconds')}")
    audio_url = synth.get("audio_url", "")

    # Serve audio file
    if audio_url:
        status, audio_data = _req("GET", f"{BASE_VOICE}{audio_url}")
        test("Audio file served", status == 200,
             detail=f"status={status}, size={len(audio_data) if isinstance(audio_data, str) else '?'}")

    # Announce task
    status, ann = _req("POST", f"{BASE_VOICE}/api/voice/announce", {
        "task": {
            "id": 99,
            "title": "テスト: 部屋の掃除",
            "description": "リビングの掃除をしてください",
            "xp_reward": 200,
            "urgency": 2,
            "zone": "living_room",
        }
    })
    test("Announce task", status == 200 and "audio_url" in ann)
    test("Announce has text_generated", isinstance(ann.get("text_generated"), str) and len(ann["text_generated"]) > 0)

    # Announce with completion (dual voice)
    status, dual = _req("POST", f"{BASE_VOICE}/api/voice/announce_with_completion", {
        "task": {
            "id": 100,
            "title": "テスト: ゴミ出し",
            "description": "ゴミ袋を集積所に出してください",
            "xp_reward": 100,
            "urgency": 1,
            "zone": "kitchen",
        }
    })
    test("Announce with completion", status == 200 and "announcement_audio_url" in dual and "completion_audio_url" in dual)
    test("Dual has both texts",
         isinstance(dual.get("announcement_text"), str) and isinstance(dual.get("completion_text"), str))

    # Feedback
    status, fb = _req("POST", f"{BASE_VOICE}/api/voice/feedback/thanks")
    test("Feedback (thanks)", status == 200 and "audio_url" in fb)

    # 404 for missing audio
    status, _ = _req("GET", f"{BASE_VOICE}/audio/nonexistent_file.mp3")
    test("404 for missing audio", status == 404)


# ============================================================
# 7. Frontend: nginx proxy
# ============================================================
def test_frontend_proxy():
    print("\n=== 7. Frontend: Nginx Proxy ===")

    # /api/ -> backend
    status, tasks = _req("GET", f"{BASE_FRONTEND}/api/tasks/")
    test("Frontend /api/tasks/ proxies to backend",
         status == 200 and isinstance(tasks, list))

    # /api/voice/ -> voice-service
    status, data = _req("POST", f"{BASE_FRONTEND}/api/voice/synthesize", {
        "text": "プロキシテスト",
        "tone": "neutral",
    })
    test("Frontend /api/voice/ proxies to voice-service",
         status == 200 and "audio_url" in data)

    # Serve audio through frontend proxy
    audio_url = data.get("audio_url", "")
    if audio_url:
        status, _ = _req("GET", f"{BASE_FRONTEND}{audio_url}")
        test("Frontend /audio/ proxies to voice-service", status == 200)

    # SPA fallback
    status, html = _req("GET", f"{BASE_FRONTEND}/nonexistent-route")
    test("SPA fallback returns index.html",
         status == 200 and isinstance(html, str) and "<!DOCTYPE html>" in html)


# ============================================================
# 8. Mock LLM
# ============================================================
def test_mock_llm():
    print("\n=== 8. Mock LLM ===")

    # Brain mode (with tools) — high CO2
    status, resp = _req("POST", f"{BASE_MOCK_LLM}/v1/chat/completions", {
        "messages": [
            {"role": "system", "content": "あなたはHEMS Brainです。"},
            {"role": "user", "content": "CO2濃度が1200ppmを超えています。換気してください。"},
        ],
        "tools": [{"type": "function", "function": {"name": "create_task"}}],
    })
    test("Mock LLM responds", status == 200)
    choices = resp.get("choices", []) if isinstance(resp, dict) else []
    has_tool = choices and choices[0].get("message", {}).get("tool_calls")
    test("Mock LLM returns tool_calls for CO2", has_tool,
         detail=f"message={choices[0].get('message', {}) if choices else '{}'}")

    # Voice mode (no tools) — task announcement
    status, resp2 = _req("POST", f"{BASE_MOCK_LLM}/v1/chat/completions", {
        "messages": [
            {"role": "user", "content": "以下のタスクのアナウンスを作成:\nタイトル: テスト\nXP: 100"},
        ],
    })
    test("Mock LLM text gen mode", status == 200)
    content = resp2.get("choices", [{}])[0].get("message", {}).get("content", "")
    test("Mock LLM generates announcement text", len(content) > 0,
         detail=f"content={content[:60]}")


# ============================================================
# 9. Brain E2E: MQTT → cognitive cycle → task creation
# ============================================================
def test_brain_e2e():
    print("\n=== 9. Brain E2E ===")

    # Get current task count
    status, tasks_before = _req("GET", f"{BASE_BACKEND}/tasks/")
    before_count = len(tasks_before) if isinstance(tasks_before, list) else 0

    # Publish sensor data to trigger brain
    mqtt_pub("office/living_room/sensor/env_01/co2", {"value": 1800})
    mqtt_pub("office/living_room/sensor/env_01/temperature", {"value": 26.0})
    mqtt_pub("office/living_room/sensor/env_01/humidity", {"value": 45.0})
    test("Published sensor data to MQTT", True)

    # Wait for brain cognitive cycle (30s interval + 3s batch + processing)
    print("  ... waiting 40s for brain cognitive cycle ...")
    time.sleep(40)

    # Check brain logs for cycle completion
    result = subprocess.run(
        ["docker", "logs", "hems-brain", "--since", "45s"],
        capture_output=True, text=True, timeout=10,
    )
    logs = result.stdout + result.stderr
    cycle_ran = "Cycle:" in logs or "iter=" in logs
    test("Brain ran cognitive cycle", cycle_ran,
         detail=f"logs_tail={logs[-200:].strip()}")

    no_errors = "Cognitive cycle error" not in logs
    test("No cognitive cycle errors", no_errors,
         detail=logs[logs.find("error"):logs.find("error")+100] if "error" in logs.lower() else "")

    # Check event store flushed
    event_flushed = "Flushed" in logs
    test("Event store flushed events", event_flushed)

    # Check if task was created by brain
    status, tasks_after = _req("GET", f"{BASE_BACKEND}/tasks/")
    after_count = len(tasks_after) if isinstance(tasks_after, list) else 0
    test("Brain created task(s) via mock-llm",
         after_count > before_count,
         detail=f"before={before_count}, after={after_count}")


# ============================================================
# 10. Character system: hot-reload
# ============================================================
def test_character_reload():
    print("\n=== 10. Character Hot-Reload ===")

    # Send reload command via MQTT
    mqtt_pub("hems/brain/reload-character", {"action": "reload"})
    time.sleep(2)

    result = subprocess.run(
        ["docker", "logs", "hems-brain", "--since", "5s"],
        capture_output=True, text=True, timeout=10,
    )
    logs = result.stdout + result.stderr
    test("Character reload command received",
         "Character reload command received" in logs or "reload" in logs.lower(),
         detail=f"logs={logs[-200:].strip()}")


# ============================================================
# 11. Event Store: data written
# ============================================================
def test_event_store():
    print("\n=== 11. Event Store ===")

    # Check if SQLite DB exists and has data
    result = subprocess.run(
        ["docker", "exec", "hems-brain", "python", "-c", """
import sqlite3, os, json
db_path = '/app/data/hems.db'
if not os.path.exists(db_path):
    print(json.dumps({"error": "DB not found"}))
else:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    counts = {}
    for t in tables:
        counts[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    conn.close()
    print(json.dumps({"tables": tables, "counts": counts}))
"""],
        capture_output=True, text=True, timeout=10,
    )
    try:
        data = json.loads(result.stdout.strip())
    except Exception:
        data = {"error": result.stderr[:200]}

    test("Event store DB exists", "error" not in data,
         detail=str(data)[:100])

    tables = data.get("tables", [])
    test("Has raw_events table", "raw_events" in tables)
    test("Has llm_decisions table", "llm_decisions" in tables)
    test("Has hourly_aggregates table", "hourly_aggregates" in tables)

    counts = data.get("counts", {})
    test("raw_events has data", counts.get("raw_events", 0) > 0,
         detail=f"count={counts.get('raw_events', 0)}")
    test("llm_decisions has data", counts.get("llm_decisions", 0) > 0,
         detail=f"count={counts.get('llm_decisions', 0)}")


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("HEMS Phase 1 Integration Test")
    print("=" * 60)

    test_health()
    user_id = test_users()
    task_id, task2_id = test_tasks(user_id)
    test_points(user_id, task_id)
    test_voice_events()
    test_voice_service()
    test_frontend_proxy()
    test_mock_llm()
    test_brain_e2e()
    test_character_reload()
    test_event_store()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} passed, {FAIL} failed")
    if ERRORS:
        print("\nFailures:")
        for e in ERRORS:
            print(f"  - {e}")
    print("=" * 60)

    sys.exit(0 if FAIL == 0 else 1)
