#!/bin/bash
echo "Setting up SOMS Development Environment..."

# 1. Check Docker
if ! command -v docker &> /dev/null
then
    echo "Docker could not be found. Please install Docker."
    exit
fi

# 2. Create Volumes
docker volume create soms_mqtt_data
docker volume create soms_mqtt_log
docker volume create soms_db_data

# 3. Build Containers
echo "Building containers..."
docker compose -f ../docker-compose.yml build

echo "Setup Complete. Run 'docker compose -f ../docker-compose.yml up' to start."
