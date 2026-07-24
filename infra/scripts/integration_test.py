#!/usr/bin/env python3
"""Runtime E2E checks for the Docker Compose HEMS core stack.

The suite exercises HTTP, nginx proxying, MQTT -> Brain -> Backend, voice
synthesis, PostgreSQL migrations, and the Brain event store. It intentionally
uses only the Python standard library and Docker CLI.

Recommended test stack:

    COMPOSE_PROFILES=mock,postgres \
      LLM_API_URL=http://mock-llm:8000/v1 LLM_MODEL=mock \
      docker compose --profile mock --profile postgres up -d --build

Environment overrides:

    HEMS_E2E_BACKEND_URL       default http://localhost:8010
    HEMS_E2E_VOICE_URL         default http://localhost:8012
    HEMS_E2E_FRONTEND_URL      default http://localhost:8080
    HEMS_E2E_MOCK_LLM_URL      default http://localhost:8011
    HEMS_E2E_BRAIN_WAIT        default 45 seconds
    HEMS_E2E_*_CONTAINER       override Docker container names
    BACKEND_API_KEY            optional Backend bearer token
    HEMS_INTERNAL_TOKEN        optional Voice bearer token
    MQTT_PASS                  optional; read from the MQTT container if omitted
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any

BASE_BACKEND = os.getenv("HEMS_E2E_BACKEND_URL", "http://localhost:8010").rstrip("/")
BASE_VOICE = os.getenv("HEMS_E2E_VOICE_URL", "http://localhost:8012").rstrip("/")
BASE_FRONTEND = os.getenv("HEMS_E2E_FRONTEND_URL", "http://localhost:8080").rstrip("/")
BASE_MOCK_LLM = os.getenv("HEMS_E2E_MOCK_LLM_URL", "http://localhost:8011").rstrip("/")
BRAIN_WAIT = int(os.getenv("HEMS_E2E_BRAIN_WAIT", "45"))

MQTT_CONTAINER = os.getenv("HEMS_E2E_MQTT_CONTAINER", "hems-mqtt")
BRAIN_CONTAINER = os.getenv("HEMS_E2E_BRAIN_CONTAINER", "hems-brain")
POSTGRES_CONTAINER = os.getenv("HEMS_E2E_POSTGRES_CONTAINER", "hems-postgres")

BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "")
INTERNAL_TOKEN = os.getenv("HEMS_INTERNAL_TOKEN", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
POSTGRES_USER = os.getenv("HEMS_E2E_POSTGRES_USER", "hems")
POSTGRES_DB = os.getenv("HEMS_E2E_POSTGRES_DB", "hems")
RUN_ID = uuid.uuid4().hex[:10]

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def _headers(*, internal: bool = False) -> dict[str, str]:
    token = INTERNAL_TOKEN if internal else BACKEND_API_KEY
    return {"Authorization": f"Bearer {token}"} if token else {}


def _req(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get_content_type()
            if content_type == "application/json":
                return response.status, json.loads(raw)
            if content_type.startswith("text/"):
                return response.status, raw.decode(errors="replace")
            return response.status, raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error.code, raw.decode(errors="replace")
    except Exception as error:
        return 0, str(error)


def _docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _mqtt_password() -> str:
    if MQTT_PASS:
        return MQTT_PASS
    result = _docker("exec", MQTT_CONTAINER, "printenv", "MQTT_PASS")
    return result.stdout.strip() if result.returncode == 0 else ""


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m {name}")
        return
    FAIL += 1
    suffix = f" — {detail}" if detail else ""
    print(f"  \033[31mFAIL\033[0m {name}{suffix}")
    ERRORS.append(f"{name}: {detail}")


def test_health() -> None:
    print("\n=== 1. Service health ===")
    status, data = _req("GET", f"{BASE_BACKEND}/health")
    check("Backend health", status == 200 and data.get("status") == "ok", f"status={status}, data={data}")

    status, data = _req("GET", f"{BASE_VOICE}/api/voice/health")
    check("Voice health", status == 200 and data.get("service") == "HEMS Voice", f"status={status}, data={data}")

    status, _ = _req("GET", f"{BASE_MOCK_LLM}/docs")
    check("Mock LLM reachable", status == 200, f"status={status}")

    status, html = _req("GET", f"{BASE_FRONTEND}/")
    check("Frontend reachable", status == 200 and "<!doctype html>" in html.lower(), f"status={status}")


def test_backend_lifecycle() -> None:
    print("\n=== 2. Backend lifecycle ===")
    username = f"e2e-{RUN_ID}"
    status, user = _req(
        "POST",
        f"{BASE_BACKEND}/users/",
        {"username": username, "display_name": "E2E User"},
        headers=_headers(),
    )
    check(
        "Create user returns 201", status == 201 and user.get("username") == username, f"status={status}, data={user}"
    )
    user_id = user.get("id")

    status, duplicate = _req(
        "POST",
        f"{BASE_BACKEND}/users/",
        {"username": username, "display_name": "Duplicate"},
        headers=_headers(),
    )
    check("Duplicate username returns 409", status == 409, f"status={status}, data={duplicate}")

    task_body = {
        "title": f"E2E ventilation {RUN_ID}",
        "description": "End-to-end task lifecycle",
        "location": f"e2e-{RUN_ID}",
        "zone": f"e2e-{RUN_ID}",
        "task_type": [f"e2e-{RUN_ID}"],
        "urgency": 3,
        "estimated_duration": 5,
    }
    status, task = _req("POST", f"{BASE_BACKEND}/tasks/", task_body, headers=_headers())
    check("Create task", status == 200 and task.get("title") == task_body["title"], f"status={status}, data={task}")
    task_id = task.get("id")

    status, duplicate_task = _req("POST", f"{BASE_BACKEND}/tasks/", task_body, headers=_headers())
    check(
        "Task deduplication returns existing task",
        status == 200 and duplicate_task.get("id") == task_id,
        f"status={status}, expected={task_id}, data={duplicate_task}",
    )

    status, accepted = _req(
        "PUT",
        f"{BASE_BACKEND}/tasks/{task_id}/accept",
        {"user_id": user_id},
        headers=_headers(),
    )
    check("Accept task", status == 200 and accepted.get("assigned_to") == user_id, f"status={status}, data={accepted}")

    status, completed = _req(
        "PUT",
        f"{BASE_BACKEND}/tasks/{task_id}/complete",
        {"report_status": "done", "completion_note": "E2E complete"},
        headers=_headers(),
    )
    check(
        "Complete task",
        status == 200 and completed.get("is_completed") is True,
        f"status={status}, data={completed}",
    )

    status, stats = _req("GET", f"{BASE_BACKEND}/tasks/stats", headers=_headers())
    check(
        "Task stats reflect lifecycle",
        status == 200 and stats.get("tasks_created", 0) >= 1 and stats.get("tasks_completed", 0) >= 1,
        f"status={status}, data={stats}",
    )


def test_data_flow() -> None:
    print("\n=== 3. Backend data flow ===")
    zone_id = f"e2e-{RUN_ID}"
    snapshot = {
        "zones": [
            {
                "zone_id": zone_id,
                "environment": {"temperature": 24.5, "humidity": 51.0, "co2": 640.0},
                "occupancy": {"count": 1},
            }
        ]
    }
    status, result = _req("POST", f"{BASE_BACKEND}/zones/snapshot", snapshot, headers=_headers())
    check("Write zone snapshot", status == 200 and result.get("updated") == 1, f"status={status}, data={result}")

    status, zones = _req("GET", f"{BASE_BACKEND}/zones/", headers=_headers())
    current = (
        next((zone for zone in zones if zone.get("zone_id") == zone_id), None) if isinstance(zones, list) else None
    )
    check(
        "Read zone snapshot",
        status == 200 and current is not None and current["environment"]["co2"] == 640.0,
        f"status={status}, data={zones}",
    )

    status, event = _req(
        "POST",
        f"{BASE_BACKEND}/voice-events/",
        {
            "message": f"E2E voice event {RUN_ID}",
            "audio_url": "/audio/e2e.mp3",
            "zone": zone_id,
            "tone": "neutral",
        },
        headers=_headers(),
    )
    check("Create voice event", status == 200 and event.get("zone") == zone_id, f"status={status}, data={event}")

    status, events = _req("GET", f"{BASE_BACKEND}/voice-events/recent", headers=_headers())
    check(
        "Read recent voice event",
        status == 200 and any(item.get("id") == event.get("id") for item in events),
        f"status={status}, data={events}",
    )


def test_voice_and_proxy() -> None:
    print("\n=== 4. Voice and nginx proxy ===")
    status, voice = _req(
        "POST",
        f"{BASE_VOICE}/api/voice/synthesize",
        {"text": "E2E音声合成テストです。", "tone": "neutral"},
        headers=_headers(internal=True),
        timeout=60,
    )
    audio_url = voice.get("audio_url", "") if isinstance(voice, dict) else ""
    check("Synthesize voice", status == 200 and bool(audio_url), f"status={status}, data={voice}")

    if audio_url:
        audio_status, audio = _req("GET", f"{BASE_VOICE}{audio_url}")
        check("Serve synthesized audio", audio_status == 200 and isinstance(audio, bytes) and len(audio) > 0)

    status, tasks = _req("GET", f"{BASE_FRONTEND}/api/tasks/", headers=_headers())
    check("Frontend proxies Backend", status == 200 and isinstance(tasks, list), f"status={status}, data={tasks}")

    status, proxied_voice = _req(
        "POST",
        f"{BASE_FRONTEND}/api/voice/synthesize",
        {"text": "E2Eプロキシ音声です。", "tone": "neutral"},
        headers=_headers(internal=True),
        timeout=60,
    )
    proxied_audio_url = proxied_voice.get("audio_url", "") if isinstance(proxied_voice, dict) else ""
    check("Frontend proxies Voice", status == 200 and bool(proxied_audio_url), f"status={status}, data={proxied_voice}")

    if proxied_audio_url:
        audio_status, audio = _req("GET", f"{BASE_FRONTEND}{proxied_audio_url}", headers=_headers(internal=True))
        check("Frontend proxies audio", audio_status == 200 and isinstance(audio, bytes) and len(audio) > 0)

    status, html = _req("GET", f"{BASE_FRONTEND}/e2e-spa-route")
    check("Frontend SPA fallback", status == 200 and "<!doctype html>" in html.lower(), f"status={status}")


def test_mock_llm() -> None:
    print("\n=== 5. Mock LLM ===")
    status, response = _req(
        "POST",
        f"{BASE_MOCK_LLM}/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": "CO2が1800ppmを超えています。換気してください。"}],
            "tools": [{"type": "function", "function": {"name": "create_task"}}],
        },
    )
    choices = response.get("choices", []) if isinstance(response, dict) else []
    tool_calls = choices[0].get("message", {}).get("tool_calls") if choices else None
    check("Mock LLM returns create_task call", status == 200 and bool(tool_calls), f"status={status}, data={response}")


def _publish_sensor_data() -> bool:
    password = _mqtt_password()
    if not password:
        return False
    result = _docker(
        "exec",
        MQTT_CONTAINER,
        "mosquitto_pub",
        "-h",
        "localhost",
        "-u",
        "hems-iot",
        "-P",
        password,
        "-t",
        f"hems/sensors/e2e_{RUN_ID}/sensor/env_{RUN_ID}/co2",
        "-m",
        json.dumps({"value": 1800, "run_id": RUN_ID}),
    )
    return result.returncode == 0


def test_brain_e2e() -> None:
    print("\n=== 6. MQTT -> Brain -> Backend ===")
    brain_log_since = datetime.now(UTC).isoformat()
    status, before = _req("GET", f"{BASE_BACKEND}/tasks/", headers=_headers())
    brain_task_titles = {"エアコンをつけてください", "窓を開けて換気してください"}
    if status == 200 and isinstance(before, list):
        for task in before:
            if not task.get("is_completed") and task.get("title") in brain_task_titles:
                _req(
                    "PUT",
                    f"{BASE_BACKEND}/tasks/{task['id']}/complete",
                    {"report_status": "done", "completion_note": "E2E pre-run cleanup"},
                    headers=_headers(),
                )
    before_ids = {task["id"] for task in before} if status == 200 and isinstance(before, list) else set()

    published = _publish_sensor_data()
    check("Publish canonical sensor event", published, "MQTT_PASS is missing or mosquitto_pub failed")
    if not published:
        return

    print(f"  ... waiting up to {BRAIN_WAIT}s for the cognitive cycle ...")
    deadline = time.monotonic() + BRAIN_WAIT
    created: list[dict[str, Any]] = []
    logs = ""
    while time.monotonic() < deadline:
        time.sleep(2)
        status, tasks = _req("GET", f"{BASE_BACKEND}/tasks/", headers=_headers())
        if status == 200 and isinstance(tasks, list):
            created = [task for task in tasks if task.get("id") not in before_ids]
            if created:
                break
        logs_result = _docker("logs", BRAIN_CONTAINER, "--since", brain_log_since)
        logs = logs_result.stdout + logs_result.stderr
        if "Skipping create_task:" in logs:
            break

    logs_result = _docker("logs", BRAIN_CONTAINER, "--since", brain_log_since)
    logs = logs_result.stdout + logs_result.stderr
    check("Brain ran a cognitive cycle", "Cycle:" in logs, f"logs_tail={logs[-500:]}")
    check("Brain stayed running without traceback", "Traceback" not in logs, f"logs_tail={logs[-500:]}")
    deduplicated = "Skipping create_task:" in logs
    check(
        "Brain handled create_task outcome",
        bool(created) or deduplicated,
        f"new_tasks={created}, logs_tail={logs[-500:]}",
    )


def test_postgres_state() -> None:
    print("\n=== 7. PostgreSQL migration and event store ===")
    query = (
        "SELECT "
        "(SELECT version_num FROM public.alembic_version),"
        "(SELECT count(*) FROM events.raw_events),"
        "(SELECT count(*) FROM events.llm_decisions),"
        "(SELECT count(*) FROM events.world_events);"
    )
    deadline = time.monotonic() + 10
    result = None
    values: list[str] = []
    while time.monotonic() < deadline:
        result = _docker(
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-At",
            "-F",
            "|",
            "-c",
            query,
        )
        values = result.stdout.strip().split("|") if result.returncode == 0 else []
        if len(values) == 4 and int(values[1]) > 0 and int(values[2]) > 0:
            break
        time.sleep(1)
    assert result is not None
    detail = result.stdout + result.stderr
    check(
        "Backend migration is at head",
        len(values) == 4 and values[0] == "0004_mobile_observation",
        detail,
    )
    check("Event store contains raw events", len(values) == 4 and int(values[1]) > 0, detail)
    check("Event store contains LLM decisions", len(values) == 4 and int(values[2]) > 0, detail)
    check("Event store world_events table is queryable", len(values) == 4 and values[3].isdigit(), detail)


def test_character_reload() -> None:
    print("\n=== 8. Character hot reload ===")
    password = _mqtt_password()
    if not password:
        check("Character reload", False, "MQTT_PASS is missing")
        return
    publish = _docker(
        "exec",
        MQTT_CONTAINER,
        "mosquitto_pub",
        "-h",
        "localhost",
        "-u",
        "hems-brain",
        "-P",
        password,
        "-t",
        "hems/brain/reload-character",
        "-m",
        '{"action":"reload"}',
    )
    time.sleep(2)
    logs_result = _docker("logs", BRAIN_CONTAINER, "--since", "5s")
    logs = logs_result.stdout + logs_result.stderr
    check(
        "Character reload command handled",
        publish.returncode == 0 and "reload" in logs.lower(),
        f"publish={publish.stderr}, logs={logs[-300:]}",
    )


def main() -> int:
    print("=" * 64)
    print(f"HEMS runtime E2E suite (run {RUN_ID})")
    print("=" * 64)
    test_health()
    test_backend_lifecycle()
    test_data_flow()
    test_voice_and_proxy()
    test_mock_llm()
    test_brain_e2e()
    test_postgres_state()
    test_character_reload()

    print("\n" + "=" * 64)
    print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
    if ERRORS:
        print("\nFailures:")
        for error in ERRORS:
            print(f"  - {error}")
    print("=" * 64)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
