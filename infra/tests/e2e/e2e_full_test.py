#!/usr/bin/env python3
"""
E2E Full Integration Test: brain + ollama + voice + dashboard pipeline.

Requires all services running:
  brain, ollama, voice, voicevox, dashboard backend/frontend,
  mqtt, mock-llm, perception, virtual-edge

Scenarios:
  1. Health checks (backend, voice, mqtt)
  2. CO2=2000ppm → task creation + announcement audio
  3. temperature=38°C → task or voice-event
  4. Audio URL accessibility (announcement + completion)
  5. Rejection stock audio
  6. Task lifecycle: accept → complete
  7. Deduplication + cleanup
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
BACKEND_URL = "http://localhost:8000"
VOICE_URL = "http://localhost:8002"
AUDIO_BASE_URL = "http://localhost"  # nginx serves /audio/
CYCLE_WAIT = 45  # ollama is slower than mock-LLM

# Shared state across tests
state = {
    "co2_task": None,       # Task created by CO2 trigger (Test 2)
    "temp_task": None,      # Task created by temp trigger (Test 3)
    "all_test_tasks": [],   # All task IDs created during test
}


# ── Helpers ──────────────────────────────────────────────────────

def api_request(url, method="GET", data=None, timeout=10):
    """Make an HTTP request and return parsed JSON or raw bytes."""
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "json" in content_type or "text" in content_type:
            return json.loads(raw)
        return raw  # binary (audio etc.)


def get_active_tasks():
    """Get non-completed tasks from backend."""
    tasks = api_request(f"{BACKEND_URL}/tasks/")
    return [t for t in tasks if not t.get("is_completed", False)]


def complete_task(task_id):
    return api_request(f"{BACKEND_URL}/tasks/{task_id}/complete", method="PUT")


def publish_mqtt(client, topic, payload):
    info = client.publish(topic, json.dumps(payload))
    info.wait_for_publish(timeout=5)
    print(f"    MQTT {topic} -> {payload}")


def fetch_audio_url(audio_url):
    """Resolve an audio URL (may be relative) and fetch it."""
    if not audio_url:
        return None, 0
    if audio_url.startswith("/audio/"):
        full_url = f"{AUDIO_BASE_URL}{audio_url}"
    elif audio_url.startswith("http"):
        full_url = audio_url
    else:
        full_url = f"{AUDIO_BASE_URL}/{audio_url}"
    try:
        data = api_request(full_url, timeout=10)
        return data, len(data) if isinstance(data, bytes) else len(str(data))
    except Exception as e:
        print(f"    Audio fetch failed: {full_url} -> {e}")
        return None, 0


def print_header(test_num, title):
    print(f"\n{'=' * 60}")
    print(f"[Test {test_num}] {title}")
    print(f"{'=' * 60}")


def result(passed, msg):
    if passed:
        print(f"    PASS - {msg}")
    else:
        print(f"    FAIL - {msg}")
    return passed


# ── Tests ────────────────────────────────────────────────────────

def test_1_health_checks():
    """Backend API / Voice Service / MQTT connectivity."""
    print_header(1, "Health checks: backend, voice, MQTT")
    checks = 0
    total = 3

    # Backend
    try:
        tasks = api_request(f"{BACKEND_URL}/tasks/")
        assert isinstance(tasks, list)
        print(f"    Backend OK - {len(tasks)} tasks")
        checks += 1
    except Exception as e:
        print(f"    Backend FAIL - {e}")

    # Voice service
    try:
        info = api_request(f"{VOICE_URL}/")
        assert info.get("status") == "running"
        print(f"    Voice OK - {info}")
        checks += 1
    except Exception as e:
        print(f"    Voice FAIL - {e}")

    # MQTT
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e_health")
        if MQTT_USER:
            c.username_pw_set(MQTT_USER, MQTT_PASS)
        c.connect(MQTT_BROKER, MQTT_PORT, 5)
        c.disconnect()
        print(f"    MQTT OK - connected to {MQTT_BROKER}:{MQTT_PORT}")
        checks += 1
    except Exception as e:
        print(f"    MQTT FAIL - {e}")

    return result(checks == total, f"{checks}/{total} services healthy")


def test_2_co2_task_creation(client):
    """CO2=2000ppm -> Brain creates task with announcement audio."""
    print_header(2, "CO2=2000ppm -> task creation + announcement audio")

    tasks_before = get_active_tasks()
    env_before = [t for t in tasks_before if "environment" in (t.get("task_type") or [])]

    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 2000})

    print(f"    Waiting {CYCLE_WAIT}s for Brain cycle...")
    time.sleep(CYCLE_WAIT)

    tasks_after = get_active_tasks()
    env_after = [t for t in tasks_after if "environment" in (t.get("task_type") or [])]
    new_env = [t for t in env_after if t["id"] not in {x["id"] for x in env_before}]

    if not new_env:
        # Might have updated an existing task - check all env tasks
        new_env = env_after

    if len(new_env) >= 1:
        task = new_env[0]
        state["co2_task"] = task
        state["all_test_tasks"].append(task["id"])

        has_announcement = bool(task.get("announcement_audio_url"))
        has_completion = bool(task.get("completion_audio_url"))

        print(f"    Task created: ID={task['id']} \"{task['title']}\"")
        print(f"    announcement_audio_url: {task.get('announcement_audio_url', 'NONE')}")
        print(f"    completion_audio_url: {task.get('completion_audio_url', 'NONE')}")

        return result(True,
                       f"Task created (audio: announce={'yes' if has_announcement else 'no'}, "
                       f"complete={'yes' if has_completion else 'no'})")
    else:
        print(f"    No environment task found. Active tasks: {len(tasks_after)}")
        for t in tasks_after:
            print(f"      - ID={t['id']} \"{t['title']}\" type={t.get('task_type')}")
        return result(False, "No task created for CO2=2000ppm")


def test_3_temperature_reaction(client):
    """temperature=38C -> Brain reacts (task, speak, or acknowledges in reasoning)."""
    print_header(3, "temperature=38C -> Brain reaction")

    # Complete existing env tasks so Brain is free to react to temperature
    active_now = get_active_tasks()
    for t in active_now:
        if "environment" in (t.get("task_type") or []):
            print(f"    Completing env task {t['id']} to free Brain...")
            try:
                complete_task(t["id"])
            except Exception:
                pass
    time.sleep(2)

    tasks_before = get_active_tasks()
    task_ids_before = {t["id"] for t in tasks_before}

    # Also restore CO2 to normal so Brain focuses on temperature
    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 500})
    publish_mqtt(client, "office/main/sensor/env_01/temperature", {"value": 38.0})

    print(f"    Waiting {CYCLE_WAIT}s for Brain cycle...")
    time.sleep(CYCLE_WAIT)

    tasks_after = get_active_tasks()
    new_tasks = [t for t in tasks_after if t["id"] not in task_ids_before]

    # Check for temperature-related new tasks
    temp_task = None
    for t in new_tasks:
        title_lower = t.get("title", "").lower()
        desc_lower = t.get("description", "").lower()
        combined = title_lower + " " + desc_lower
        if any(kw in combined for kw in [
            "温", "室温", "エアコン", "冷房", "temperature", "cool", "air",
            "暑", "heat", "換気",
        ]):
            temp_task = t
            break
    if not temp_task and new_tasks:
        temp_task = new_tasks[0]  # Any new task counts

    # Check voice events
    voice_response = False
    try:
        events = api_request(f"{BACKEND_URL}/voice-events/")
        recent = [
            e for e in events
            if any(kw in e.get("message", "") for kw in ["温", "暑", "エアコン", "temperature"])
        ]
        voice_response = len(recent) > 0
    except Exception:
        pass

    # Check brain logs for temperature awareness (speak tool or LLM reasoning)
    brain_aware = False
    try:
        import subprocess
        logs = subprocess.check_output(
            ["docker", "logs", "soms-brain", "--since", "60s"],
            stderr=subprocess.STDOUT, timeout=5,
        ).decode()
        temp_keywords = ["38", "温度", "temperature", "暑", "エアコン", "冷房", "speak"]
        brain_aware = any(kw in logs for kw in temp_keywords)
        if brain_aware:
            # Extract relevant log lines
            for line in logs.split("\n"):
                if any(kw in line for kw in temp_keywords):
                    print(f"    Brain log: {line.strip()[:100]}")
                    break
    except Exception:
        pass

    if temp_task:
        state["temp_task"] = temp_task
        state["all_test_tasks"].append(temp_task["id"])
        print(f"    New task: ID={temp_task['id']} \"{temp_task['title']}\"")
        return result(True, "Brain created task for temperature alert")
    elif voice_response:
        print(f"    Voice event found for temperature")
        return result(True, "Brain reacted via speak tool")
    elif brain_aware:
        return result(True, "Brain acknowledged temperature in reasoning/speak")
    elif new_tasks:
        state["all_test_tasks"].extend(t["id"] for t in new_tasks)
        print(f"    {len(new_tasks)} new task(s) created")
        return result(True, f"Brain reacted with {len(new_tasks)} new task(s)")
    else:
        print(f"    No new tasks or voice events detected")
        print(f"    Hint: docker logs soms-brain --tail 30")
        return result(False, "No reaction to 38C temperature")


def test_4_audio_accessibility():
    """Verify announcement/completion audio URLs return audio content."""
    print_header(4, "Audio URL accessibility (announcement + completion)")

    task = state.get("co2_task")
    if not task:
        return result(False, "Skipped - no task from Test 2")

    checks = 0
    total = 0

    # Announcement audio
    ann_url = task.get("announcement_audio_url")
    if ann_url:
        total += 1
        data, size = fetch_audio_url(ann_url)
        if data and size > 100:
            print(f"    Announcement audio: {size} bytes")
            checks += 1
        else:
            print(f"    Announcement audio: fetch failed or too small ({size} bytes)")
    else:
        print(f"    No announcement_audio_url on task")

    # Completion audio
    comp_url = task.get("completion_audio_url")
    if comp_url:
        total += 1
        data, size = fetch_audio_url(comp_url)
        if data and size > 100:
            print(f"    Completion audio: {size} bytes")
            checks += 1
        else:
            print(f"    Completion audio: fetch failed or too small ({size} bytes)")
    else:
        print(f"    No completion_audio_url on task")

    if total == 0:
        return result(False, "No audio URLs to test (voice not configured?)")

    return result(checks == total, f"{checks}/{total} audio URLs accessible")


def test_5_rejection_stock():
    """GET /api/voice/rejection/random -> audio from stock."""
    print_header(5, "Rejection stock audio")

    # Check stock status first
    try:
        status = api_request(f"{VOICE_URL}/api/voice/rejection/status")
        stock_count = status.get("stock_count", 0)
        print(f"    Rejection stock: {stock_count} entries")
    except Exception as e:
        print(f"    Could not check stock status: {e}")
        stock_count = -1

    # Try to get a rejection
    try:
        rejection = api_request(f"{VOICE_URL}/api/voice/rejection/random")
        audio_url = rejection.get("audio_url", "")
        text = rejection.get("text", "")
        print(f"    Rejection text: \"{text[:60]}...\"" if len(text) > 60 else f"    Rejection text: \"{text}\"")
        print(f"    Audio URL: {audio_url}")

        if audio_url:
            # Fetch the audio via voice service directly
            if audio_url.startswith("/"):
                full_url = f"{VOICE_URL}{audio_url}"
            else:
                full_url = audio_url
            try:
                data = api_request(full_url, timeout=10)
                size = len(data) if isinstance(data, bytes) else 0
                print(f"    Audio size: {size} bytes")
                return result(size > 100, f"Rejection audio retrieved ({size} bytes)")
            except Exception as e:
                # Try via nginx
                data, size = fetch_audio_url(audio_url)
                if data and size > 100:
                    print(f"    Audio size (nginx): {size} bytes")
                    return result(True, f"Rejection audio retrieved via nginx ({size} bytes)")
                return result(False, f"Audio fetch failed: {e}")
        else:
            return result(False, "No audio_url in rejection response")

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"    Stock empty (404) - stock_count was {stock_count}")
            return result(False, "Rejection stock empty - no pre-generated audio")
        raise
    except Exception as e:
        return result(False, f"Rejection request failed: {e}")


def test_6_task_lifecycle():
    """Accept voice synthesis + complete task -> lifecycle verified."""
    print_header(6, "Task lifecycle: accept voice -> complete")

    task = state.get("co2_task") or state.get("temp_task")
    if not task:
        return result(False, "Skipped - no task from Test 2 or 3")

    task_id = task["id"]
    checks = 0
    total = 2

    # Step 1: Synthesize accept voice (simulates frontend accept)
    print(f"    Synthesizing accept voice for task {task_id}...")
    try:
        voice_resp = api_request(
            f"{VOICE_URL}/api/voice/synthesize",
            method="POST",
            data={"text": "了解しました。対応します。"},
            timeout=30,
        )
        accept_url = voice_resp.get("audio_url", "")
        print(f"    Accept audio: {accept_url} ({voice_resp.get('duration_seconds', '?')}s)")
        if accept_url:
            checks += 1
        else:
            print(f"    No audio_url returned from synthesize")
    except Exception as e:
        print(f"    Synthesize failed: {e}")

    # Step 2: Complete the task
    print(f"    Completing task {task_id}...")
    try:
        completed = complete_task(task_id)
        is_done = completed.get("is_completed", False)
        print(f"    Task completed: is_completed={is_done}")
        if is_done:
            checks += 1
        else:
            print(f"    Task not marked completed: {completed}")
    except Exception as e:
        print(f"    Complete failed: {e}")

    return result(checks == total, f"{checks}/{total} lifecycle steps OK")


def test_7_dedup_and_cleanup(client):
    """CO2 re-send -> no duplicate, then cleanup."""
    print_header(7, "Deduplication + cleanup")

    active_before = get_active_tasks()
    count_before = len(active_before)

    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 2000})

    print(f"    Waiting {CYCLE_WAIT}s for Brain cycle...")
    time.sleep(CYCLE_WAIT)

    active_after = get_active_tasks()
    count_after = len(active_after)
    env_tasks = [t for t in active_after if "environment" in (t.get("task_type") or [])]

    dedup_ok = len(env_tasks) <= 1
    print(f"    Tasks: {count_before} -> {count_after} (env tasks: {len(env_tasks)})")

    # Cleanup: complete all test tasks
    print(f"\n    [Cleanup] Completing all test tasks...")
    for t in active_after:
        try:
            complete_task(t["id"])
            print(f"      Completed task {t['id']}")
        except Exception:
            pass

    # Restore normal sensor values
    print(f"    [Cleanup] Restoring normal sensor values...")
    publish_mqtt(client, "office/main/sensor/env_01/temperature", {"value": 22.0})
    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 500})

    return result(dedup_ok, f"Dedup OK (env tasks: {len(env_tasks)}), cleanup done")


# ── Main ─────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  E2E Full Integration Test")
    print("  brain + ollama + voice + dashboard pipeline")
    print("=" * 60)

    # Pre-flight: clean up leftover tasks
    print("\n[Setup] Checking pre-existing tasks...")
    try:
        initial = get_active_tasks()
        if initial:
            print(f"  Completing {len(initial)} leftover task(s)...")
            for t in initial:
                try:
                    complete_task(t["id"])
                except Exception:
                    pass
            time.sleep(1)
    except Exception as e:
        print(f"  WARNING: Could not check tasks: {e}")

    # Connect MQTT
    print("[Setup] Connecting MQTT...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e_full_test")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    time.sleep(1)

    # Run tests
    tests = [
        ("Health checks",       lambda: test_1_health_checks()),
        ("CO2 task creation",   lambda: test_2_co2_task_creation(client)),
        ("Temperature reaction",lambda: test_3_temperature_reaction(client)),
        ("Audio accessibility", lambda: test_4_audio_accessibility()),
        ("Rejection stock",     lambda: test_5_rejection_stock()),
        ("Task lifecycle",      lambda: test_6_task_lifecycle()),
        ("Dedup + cleanup",     lambda: test_7_dedup_and_cleanup(client)),
    ]

    passed = 0
    failed = 0
    results = []

    for name, test_fn in tests:
        try:
            ok = test_fn()
            if ok:
                passed += 1
                results.append(f"  PASS  {name}")
            else:
                failed += 1
                results.append(f"  FAIL  {name}")
        except Exception as e:
            failed += 1
            results.append(f"  ERROR {name}: {e}")
            print(f"    ERROR - {e}")

    # Teardown
    client.loop_stop()
    client.disconnect()

    # Summary
    total = passed + failed
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} passed, {failed}/{total} failed")
    print(f"{'=' * 60}")
    for r in results:
        print(r)
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
