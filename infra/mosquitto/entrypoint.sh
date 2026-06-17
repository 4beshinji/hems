#!/bin/sh
# Generate mosquitto password file from environment variables, then exec mosquitto.
# All services share the same MQTT_PASS secret but use distinct usernames so
# the ACL file can enforce per-service write isolation.
set -e

: "${MQTT_PASS:?Set MQTT_PASS in .env before starting HEMS}"

PW_FILE=/mosquitto/config/passwords.txt
rm -f "$PW_FILE"
touch "$PW_FILE"

add() { mosquitto_passwd -b "$PW_FILE" "$1" "$MQTT_PASS"; }

add hems-health
add hems-brain
add hems-backend
add hems-voice
add hems-openclaw
add hems-localcraw
add hems-obsidian
add hems-gas
add hems-ha
add hems-weather
add hems-biometric
add hems-perception
add hems-iot
add hems-switchbot
add hems-tapo
add hems-zigbee
add hems-news
add hems-knowledge

chmod 600 "$PW_FILE"
chown 1883:1883 "$PW_FILE" 2>/dev/null || true

exec "$@"
