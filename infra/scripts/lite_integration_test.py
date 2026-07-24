#!/usr/bin/env python3
"""Runtime E2E checks for a running HEMS Lite Docker Compose stack."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

NOTIFIER_URL = os.getenv("HEMS_LITE_E2E_NOTIFIER_URL", "http://localhost:8019").rstrip("/")
MQTT_CONTAINER = os.getenv("HEMS_LITE_E2E_MQTT_CONTAINER", "hems-lite-mqtt")
SENTINEL_CONTAINER = os.getenv("HEMS_LITE_E2E_SENTINEL_CONTAINER", "hems-lite-sentinel")
NOTIFIER_CONTAINER = os.getenv("HEMS_LITE_E2E_NOTIFIER_CONTAINER", "hems-lite-notifier")
MQTT_PASS = os.getenv("MQTT_PASS", "")
ALERT_WAIT = int(os.getenv("HEMS_LITE_E2E_ALERT_WAIT", "75"))

PASS = 0
FAIL = 0


def _docker(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=False)


def _mqtt_password() -> str:
    if MQTT_PASS:
        return MQTT_PASS
    result = _docker("exec", MQTT_CONTAINER, "printenv", "MQTT_PASS")
    return result.stdout.strip() if result.returncode == 0 else ""


def _publish_heart_rate(bpm: int) -> subprocess.CompletedProcess[str]:
    command = ["exec", MQTT_CONTAINER, "mosquitto_pub", "-h", "localhost"]
    password = _mqtt_password()
    if password:
        command.extend(["-u", "hems-sentinel", "-P", password])
    command.extend(
        [
            "-t",
            "hems/personal/biometrics/e2e/heart_rate",
            "-m",
            json.dumps({"bpm": bpm}),
        ]
    )
    return _docker(*command)


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return 0, {}


def _latest_alert_id() -> int:
    result = _docker(
        "exec",
        SENTINEL_CONTAINER,
        "python",
        "-c",
        (
            'import sqlite3; c=sqlite3.connect("/data/sentinel.db"); '
            'print(c.execute("SELECT COALESCE(MAX(id), 0) FROM alerts").fetchone()[0])'
        ),
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return -1


def _critical_alert_after(alert_id: int) -> bool:
    result = _docker(
        "exec",
        SENTINEL_CONTAINER,
        "python",
        "-c",
        (
            'import sqlite3; c=sqlite3.connect("/data/sentinel.db"); '
            f'print(c.execute("SELECT COUNT(*) FROM alerts WHERE id > {alert_id} '
            "AND rule_id = 'C3' AND level = 'CRITICAL' AND notified = 1\").fetchone()[0])"
        ),
    )
    try:
        return int(result.stdout.strip()) > 0
    except ValueError:
        return False


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32mPASS\033[0m {name}")
    else:
        FAIL += 1
        suffix = f" — {detail}" if detail else ""
        print(f"  \033[31mFAIL\033[0m {name}{suffix}")


def main() -> int:
    print("=" * 64)
    print("HEMS Lite runtime E2E suite")
    print("=" * 64)

    status, health = _get_json(f"{NOTIFIER_URL}/api/health")
    check("Notifier health", status == 200 and health.get("status") == "ok", f"status={status}, data={health}")

    normalized = _publish_heart_rate(70)
    time.sleep(2)
    alert_id = _latest_alert_id()
    check("Sentinel database reachable", alert_id >= 0, f"latest_id={alert_id}")

    started_at = datetime.now(UTC).isoformat()
    publish = _publish_heart_rate(180)
    check(
        "Publish critical heart rate",
        normalized.returncode == 0 and publish.returncode == 0,
        (normalized.stderr + publish.stderr).strip(),
    )

    delivered = False
    deadline = time.monotonic() + ALERT_WAIT
    while time.monotonic() < deadline:
        if _critical_alert_after(alert_id):
            delivered = True
            break
        time.sleep(1)
    check("Sentinel records and notifies C3 alert", delivered)

    logs = _docker("logs", NOTIFIER_CONTAINER, "--since", started_at)
    log_output = logs.stdout + logs.stderr
    check(
        "Notifier receives critical alert",
        "心拍数が危険に上昇" in log_output and 'POST /api/notify HTTP/1.1" 200' in log_output,
        log_output[-500:],
    )

    print("=" * 64)
    print(f"Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
