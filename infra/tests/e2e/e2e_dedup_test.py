#!/usr/bin/env python3
"""
E2E test: duplicate task prevention and temperature alert response.

Requires all services running (brain, backend, mqtt, mock-llm or ollama).

Scenario:
  1. Send CO2=2000ppm → Brain creates ONE ventilation task
  2. Wait another cycle → NO duplicate created
  3. Send temperature=38°C → Brain reacts (task or speak)
  4. Verify final state
"""
import json
import os
import sys
import time
import urllib.request
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")
API_URL = "http://localhost:8000"
CYCLE_WAIT = 40  # Brain cycle=30s + batch delay + margin


def get_active_tasks():
    """Get non-completed tasks from backend."""
    with urllib.request.urlopen(f"{API_URL}/tasks/", timeout=5) as resp:
        tasks = json.loads(resp.read())
    return [t for t in tasks if not t.get("is_completed", False)]


def complete_task(task_id):
    req = urllib.request.Request(
        f"{API_URL}/tasks/{task_id}/complete", method="PUT"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def publish_mqtt(client, topic, payload):
    info = client.publish(topic, json.dumps(payload))
    info.wait_for_publish(timeout=5)
    print(f"  📤 {topic} → {payload}")


def count_tasks_matching(tasks, zone=None, task_type_contains=None):
    matched = tasks
    if zone:
        matched = [t for t in matched if t.get("zone") == zone]
    if task_type_contains:
        matched = [
            t for t in matched
            if task_type_contains in (t.get("task_type") or [])
        ]
    return len(matched)


def main():
    print("=" * 60)
    print("🧪 E2E Test: Duplicate Prevention + Temperature Alert")
    print("=" * 60)

    # -- Setup --
    print("\n[Setup] Connecting to MQTT...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e_test")
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    time.sleep(1)

    initial_active = get_active_tasks()
    print(f"[Setup] Active tasks before test: {len(initial_active)}")
    if initial_active:
        print("  ⚠️  Completing leftover active tasks...")
        for t in initial_active:
            complete_task(t["id"])
        time.sleep(1)

    passed = 0
    failed = 0
    total = 4

    # ========================================
    # Test 1: CO2=2000 → Brain creates ONE task
    # ========================================
    print(f"\n{'='*60}")
    print("[Test 1] CO2=2000ppm → Expect exactly 1 new task")
    print(f"{'='*60}")

    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 2000})

    print(f"  ⏳ Waiting {CYCLE_WAIT}s for Brain cycle...")
    time.sleep(CYCLE_WAIT)

    active = get_active_tasks()
    env_tasks = [t for t in active if "environment" in (t.get("task_type") or [])]

    if len(env_tasks) == 1:
        print(f"  ✅ PASS — 1 environment task created: \"{env_tasks[0]['title']}\"")
        passed += 1
    elif len(env_tasks) == 0:
        print(f"  ❌ FAIL — No environment task created. Active: {len(active)}")
        for t in active:
            print(f"     - {t['title']} (type={t.get('task_type')})")
        failed += 1
    else:
        print(f"  ❌ FAIL — {len(env_tasks)} environment tasks (expected 1):")
        for t in env_tasks:
            print(f"     - ID={t['id']} \"{t['title']}\"")
        failed += 1

    # ========================================
    # Test 2: Wait another cycle → NO duplicate
    # ========================================
    print(f"\n{'='*60}")
    print("[Test 2] Wait another cycle → Expect NO new duplicate")
    print(f"{'='*60}")

    count_before = len(get_active_tasks())

    # Send same CO2 again to trigger another cycle
    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 2000})

    print(f"  ⏳ Waiting {CYCLE_WAIT}s for next Brain cycle...")
    time.sleep(CYCLE_WAIT)

    active_after = get_active_tasks()
    count_after = len(active_after)
    env_tasks_after = [t for t in active_after if "environment" in (t.get("task_type") or [])]

    if count_after == count_before and len(env_tasks_after) <= 1:
        print(f"  ✅ PASS — No duplicate. Active tasks: {count_before} → {count_after}")
        passed += 1
    else:
        print(f"  ❌ FAIL — Tasks changed: {count_before} → {count_after}")
        for t in active_after:
            print(f"     - ID={t['id']} \"{t['title']}\" (type={t.get('task_type')})")
        failed += 1

    # ========================================
    # Test 3: temperature=38°C → Brain reacts
    # ========================================
    print(f"\n{'='*60}")
    print("[Test 3] temperature=38°C → Expect Brain to react")
    print(f"{'='*60}")

    tasks_before_temp = len(get_active_tasks())

    publish_mqtt(client, "office/main/sensor/env_01/temperature", {"value": 38.0})

    print(f"  ⏳ Waiting {CYCLE_WAIT}s for Brain cycle...")
    time.sleep(CYCLE_WAIT)

    active_after_temp = get_active_tasks()
    tasks_after_temp = len(active_after_temp)

    # Check for new task or voice event
    new_tasks = tasks_after_temp - tasks_before_temp
    temp_task = any(
        "temperature" in str(t.get("task_type", [])).lower()
        or "温" in t.get("title", "")
        or "室温" in t.get("title", "")
        or "エアコン" in t.get("title", "")
        or "冷房" in t.get("title", "")
        for t in active_after_temp
    )

    # Also check voice events
    voice_response = False
    try:
        with urllib.request.urlopen(f"{API_URL}/voice-events/", timeout=5) as resp:
            events = json.loads(resp.read())
            recent = [e for e in events if "温" in e.get("message", "") or "暑" in e.get("message", "")]
            voice_response = len(recent) > 0
    except Exception:
        pass

    if new_tasks > 0 or temp_task or voice_response:
        reason = []
        if new_tasks > 0:
            reason.append(f"{new_tasks} new tasks")
        if temp_task:
            reason.append("temperature-related task found")
        if voice_response:
            reason.append("voice event about temperature")
        print(f"  ✅ PASS — Brain reacted: {', '.join(reason)}")
        for t in active_after_temp:
            print(f"     - ID={t['id']} \"{t['title']}\"")
        passed += 1
    else:
        print(f"  ❌ FAIL — No reaction to 38°C. Tasks before={tasks_before_temp} after={tasks_after_temp}")
        # Check brain logs for clues
        print("  💡 Check: docker logs soms-brain --tail 30")
        failed += 1

    # ========================================
    # Test 4: Final state check
    # ========================================
    print(f"\n{'='*60}")
    print("[Test 4] Final state — no runaway task creation")
    print(f"{'='*60}")

    final_active = get_active_tasks()
    final_count = len(final_active)

    if final_count <= 3:
        print(f"  ✅ PASS — Final active tasks: {final_count} (reasonable)")
        passed += 1
    else:
        print(f"  ❌ FAIL — Final active tasks: {final_count} (too many, possible duplication)")
        failed += 1

    for t in final_active:
        print(f"     - ID={t['id']} \"{t['title']}\" zone={t.get('zone')} type={t.get('task_type')}")

    # ========================================
    # Cleanup
    # ========================================
    print(f"\n[Cleanup] Completing test tasks...")
    for t in final_active:
        try:
            complete_task(t["id"])
        except Exception:
            pass

    # Restore normal temperature
    publish_mqtt(client, "office/main/sensor/env_01/temperature", {"value": 22.0})
    publish_mqtt(client, "office/main/sensor/co2_01/co2", {"value": 500})

    client.loop_stop()
    client.disconnect()

    # ========================================
    # Summary
    # ========================================
    print(f"\n{'='*60}")
    print(f"📊 Results: {passed}/{total} passed, {failed}/{total} failed")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
