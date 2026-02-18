#!/usr/bin/env python3
"""
SOMS port-aware startup script.
Detects host port conflicts and maps to free alternatives (+100 offset).
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
COMPOSE_FILE = REPO_ROOT / "infra/docker-compose.yml"
PORTS_ENV_FILE = REPO_ROOT / "infra/.env.ports"

# (env_var, default_port, display_name)
PORT_MAP = [
    ("SOMS_PORT_FRONTEND",   80,    "frontend (nginx)"),
    ("SOMS_PORT_BACKEND",    8000,  "backend API"),
    ("SOMS_PORT_MOCK_LLM",   8001,  "mock-llm"),
    ("SOMS_PORT_VOICE",      8002,  "voice-service"),
    ("SOMS_PORT_MQTT",       1883,  "MQTT"),
    ("SOMS_PORT_MQTT_WS",    9001,  "MQTT WebSocket"),
    ("SOMS_PORT_POSTGRES",   5432,  "PostgreSQL"),
    ("SOMS_PORT_WALLET_APP", 8004,  "wallet-app"),
]

SERVICES = [
    "mosquitto", "postgres", "backend", "brain", "mock-llm",
    "wallet", "wallet-app", "frontend", "voice-service",
]


def is_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def next_free(start: int) -> int:
    p = start + 100
    while is_in_use(p):
        p += 1
    return p


def main():
    print("=== SOMS Port Conflict Check ===")
    env_overrides = {}

    for var, default_port, name in PORT_MAP:
        if is_in_use(default_port):
            new_port = next_free(default_port)
            env_overrides[var] = new_port
            print(f"  CONFLICT  {name}: {default_port} → {new_port}")
        else:
            print(f"  OK        {name}: {default_port}")

    # Write .env.ports for test scripts to source
    with PORTS_ENV_FILE.open("w") as f:
        for var, port in env_overrides.items():
            f.write(f"{var}={port}\n")
        backend_port = env_overrides.get("SOMS_PORT_BACKEND", 8000)
        frontend_port = env_overrides.get("SOMS_PORT_FRONTEND", 80)
        f.write(f"BACKEND_URL=http://localhost:{backend_port}\n")
        f.write(f"FRONTEND_URL=http://localhost:{frontend_port}\n")
    print(f"\nPort config written to {PORTS_ENV_FILE}")

    # Build env for subprocess
    env = os.environ.copy()
    for var, port in env_overrides.items():
        env[var] = str(port)

    print(f"\nStarting services: {', '.join(SERVICES)}")
    cmd = [
        "docker", "compose",
        "-f", str(COMPOSE_FILE),
        "up", "-d", "--build",
    ] + SERVICES

    result = subprocess.run(cmd, env=env, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        sys.exit(result.returncode)

    # Print summary
    print("\n=== SOMS Running ===")
    for var, default_port, name in PORT_MAP:
        port = env_overrides.get(var, default_port)
        print(f"  {name:25s}: http://localhost:{port}")
    print(f"\nLoad port env for tests:  source {PORTS_ENV_FILE}")


if __name__ == "__main__":
    main()
