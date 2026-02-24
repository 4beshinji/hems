#!/usr/bin/env bash
# HEMS Mosquitto user setup script
# Generates/updates the passwd file with per-service credentials.
#
# Usage:
#   bash infra/mosquitto/setup-users.sh          # interactive (prompts for passwords)
#   bash infra/mosquitto/setup-users.sh --gen    # auto-generate strong passwords
#
# Output: infra/mosquitto/passwd (updated in-place)
#         infra/mosquitto/service-passwords.env  (generated passwords, keep secret!)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASSWD_FILE="${SCRIPT_DIR}/passwd"
ENV_FILE="${SCRIPT_DIR}/service-passwords.env"

AUTO_GEN=false
if [[ "${1:-}" == "--gen" ]]; then
    AUTO_GEN=true
fi

gen_password() {
    openssl rand -base64 24 | tr -d '/+=' | head -c 32
}

SERVICES=(
    hems-brain
    hems-backend
    hems-voice
    hems-ha-bridge
    hems-biometric
    hems-gas
    hems-obsidian
    hems-localcraw
    hems-perception
    hems-iot
)

declare -A PASSWORDS

echo "=== HEMS Mosquitto User Setup ==="
echo "Passwd file: $PASSWD_FILE"
echo ""

# Remove old passwd file to start fresh
rm -f "$PASSWD_FILE"

for svc in "${SERVICES[@]}"; do
    if $AUTO_GEN; then
        pw=$(gen_password)
    else
        read -r -s -p "Password for $svc (Enter to auto-generate): " pw
        echo ""
        if [[ -z "$pw" ]]; then
            pw=$(gen_password)
            echo "  → Auto-generated password for $svc"
        fi
    fi
    PASSWORDS["$svc"]="$pw"
    mosquitto_passwd -b "$PASSWD_FILE" "$svc" "$pw"
    echo "Created user: $svc"
done

# Write env file for docker-compose
echo "# HEMS MQTT Service Passwords" > "$ENV_FILE"
echo "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ENV_FILE"
echo "# KEEP THIS FILE SECRET — do not commit to git" >> "$ENV_FILE"
echo "" >> "$ENV_FILE"
for svc in "${SERVICES[@]}"; do
    var_name=$(echo "$svc" | tr '[:lower:]-' '[:upper:]_')
    echo "MQTT_PASS_${var_name}=${PASSWORDS[$svc]}" >> "$ENV_FILE"
done

echo ""
echo "=== Done ==="
echo "Passwords written to: $ENV_FILE"
echo "Add $ENV_FILE to .gitignore and source it in your shell before 'docker compose up'."
echo ""
echo "Next steps:"
echo "  1. Add the following to .env (from service-passwords.env):"
for svc in "${SERVICES[@]}"; do
    var_name=$(echo "$svc" | tr '[:lower:]-' '[:upper:]_')
    echo "     MQTT_PASS_${var_name}=<password>"
done
echo ""
echo "  2. Update docker-compose.yml to use per-service credentials"
echo "  3. docker compose up -d --build"
