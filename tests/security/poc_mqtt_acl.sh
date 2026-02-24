#!/usr/bin/env bash
# PoC V1: MQTT ACL 欠落テスト
# 任意 topic に認証ユーザーで pub/sub できるか確認

set -euo pipefail

MQTT_HOST="${MQTT_HOST:-127.0.0.1}"
MQTT_PORT="${MQTT_PORT:-1893}"
MQTT_USER="${MQTT_USER:-hems}"
MQTT_PASS="${MQTT_PASS:-hems_dev_mqtt}"
TIMEOUT=5

PASS=0
FAIL=0
SKIP=0

check_pub() {
    local topic="$1"
    local payload="$2"
    local description="$3"
    if mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" \
        -u "$MQTT_USER" -P "$MQTT_PASS" \
        -t "$topic" -m "$payload" \
        --timeout "$TIMEOUT" 2>/dev/null; then
        echo "[VULNERABLE] $description — published to $topic"
        FAIL=$((FAIL + 1))
    else
        echo "[BLOCKED]    $description — publish to $topic denied"
        PASS=$((PASS + 1))
    fi
}

check_sub() {
    local topic="$1"
    local description="$2"
    # Try to subscribe for 2 seconds; success = vuln
    if timeout 2 mosquitto_sub -h "$MQTT_HOST" -p "$MQTT_PORT" \
        -u "$MQTT_USER" -P "$MQTT_PASS" \
        -t "$topic" -C 0 2>/dev/null; then
        echo "[VULNERABLE] $description — subscribed to $topic"
        FAIL=$((FAIL + 1))
    else
        echo "[BLOCKED]    $description — subscribe to $topic denied"
        PASS=$((PASS + 1))
    fi
}

echo "=== V1: MQTT ACL Test (host=$MQTT_HOST:$MQTT_PORT) ==="
echo ""

# Check mosquitto_pub is available
if ! command -v mosquitto_pub &>/dev/null; then
    echo "[SKIP] mosquitto_pub not found — install mosquitto-clients"
    SKIP=$((SKIP + 1))
else
    # 1. Fake sensor data injection
    check_pub "office/living_room/sensor/fake_dev/temperature" \
        '{"temperature": 99.9}' \
        "Fake sensor data injection"

    # 2. Brain reload-character injection
    check_pub "hems/brain/reload-character" \
        '{"character": "evil"}' \
        "Brain character reload injection"

    # 3. Fake HA smart home command
    check_pub "hems/home/living_room/light/light.main/state" \
        '{"on": true, "brightness": 255}' \
        "HA smart home state spoof"

    # 4. Fake biometric data
    check_pub "hems/personal/biometrics/gadgetbridge/heart_rate" \
        '{"bpm": 250}' \
        "Biometric data spoof"

    # 5. Subscribe to sensitive topic
    check_sub "hems/#" "Subscribe to all hems/# topics"
fi

echo ""
echo "=== Results: PASS=$PASS FAIL=$FAIL SKIP=$SKIP ==="
if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: VULNERABLE ($FAIL issues)"
    exit 1
else
    echo "STATUS: SECURE"
    exit 0
fi
