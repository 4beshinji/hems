"""
Configuration for HEMS Biometric Bridge.
"""

import os

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
MQTT_TOPIC_PREFIX = "hems/personal/biometrics"

# Canonical delivery worker (P1.2b)
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
BIOMETRIC_DELIVERY_BATCH_SIZE = int(os.getenv("BIOMETRIC_DELIVERY_BATCH_SIZE", "50"))
BIOMETRIC_DELIVERY_POLL_SECONDS = float(os.getenv("BIOMETRIC_DELIVERY_POLL_SECONDS", "2"))
BIOMETRIC_DELIVERY_LEASE_SECONDS = float(os.getenv("BIOMETRIC_DELIVERY_LEASE_SECONDS", "60"))
BIOMETRIC_DELIVERY_MAX_ATTEMPTS = int(os.getenv("BIOMETRIC_DELIVERY_MAX_ATTEMPTS", "8"))
BIOMETRIC_DELIVERY_BASE_BACKOFF_SECONDS = float(os.getenv("BIOMETRIC_DELIVERY_BASE_BACKOFF_SECONDS", "2"))
BIOMETRIC_DELIVERY_MAX_BACKOFF_SECONDS = float(os.getenv("BIOMETRIC_DELIVERY_MAX_BACKOFF_SECONDS", "300"))

# Provider
BIOMETRIC_PROVIDER = os.getenv("BIOMETRIC_PROVIDER", "gadgetbridge")

# Zepp Cloud API (optional, legacy — use Huami instead)
ZEPP_ENABLED = os.getenv("ZEPP_ENABLED", "").lower() in ("true", "1", "yes")
ZEPP_EMAIL = os.getenv("ZEPP_EMAIL", "")
ZEPP_PASSWORD = os.getenv("ZEPP_PASSWORD", "")
ZEPP_POLL_INTERVAL = int(os.getenv("ZEPP_POLL_INTERVAL", "1800"))

# Huami cloud API (Xiaomi Smart Band / Amazfit via Mi Fitness)
# Obtain token: pip install huami-token && huami-token --method xiaomi
HUAMI_ENABLED = os.getenv("HUAMI_ENABLED", "").lower() in ("true", "1", "yes")
HUAMI_AUTH_TOKEN = os.getenv("HUAMI_AUTH_TOKEN", "")
HUAMI_USER_ID = os.getenv("HUAMI_USER_ID", "")
HUAMI_SERVER_REGION = os.getenv("HUAMI_SERVER_REGION", "us")  # us, cn, eu, sg, ru
HUAMI_POLL_INTERVAL = int(os.getenv("HUAMI_POLL_INTERVAL", "900"))  # 15 min

# Deduplication window (seconds) for dual-path data overlap
DEDUP_WINDOW = int(os.getenv("BIOMETRIC_DEDUP_WINDOW", "300"))  # 5 min

# Fatigue calculation defaults — Wave 4.8 added HRV as a first-class component
# (was a post-hoc bonus). New weights: HR 20% + HRV 15% + sleep 35% + stress 30%.
FATIGUE_HR_WEIGHT = float(os.getenv("FATIGUE_HR_WEIGHT", "0.20"))
FATIGUE_HRV_WEIGHT = float(os.getenv("FATIGUE_HRV_WEIGHT", "0.15"))
FATIGUE_SLEEP_WEIGHT = float(os.getenv("FATIGUE_SLEEP_WEIGHT", "0.35"))
FATIGUE_STRESS_WEIGHT = float(os.getenv("FATIGUE_STRESS_WEIGHT", "0.30"))
