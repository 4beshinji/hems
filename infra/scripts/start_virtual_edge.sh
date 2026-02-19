#!/bin/bash
echo "Starting SOMS with Virtual Edge Simulation..."

# Check Docker
if ! command -v docker &> /dev/null
then
    echo "Docker could not be found."
    exit
fi

# Get script directory
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
PROJECT_ROOT=$(dirname "$(dirname "$SCRIPT_DIR")")

# Build & Run with Override
docker-compose -f "$PROJECT_ROOT/infra/docker-compose.yml" -f "$PROJECT_ROOT/infra/docker-compose.edge-mock.yml" up --build -d

echo "Virtual Edge Started. View logs with: 'docker logs -f soms-virtual-edge'"
