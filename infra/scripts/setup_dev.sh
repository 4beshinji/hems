#!/bin/bash
echo "Setting up HEMS Development Environment..."

# 1. Check Docker
if ! command -v docker &> /dev/null
then
    echo "Docker could not be found. Please install Docker."
    exit
fi

# 2. Create Volumes
docker volume create hems_mqtt_data
docker volume create hems_mqtt_log
docker volume create hems_db_data

# 3. Build Containers
echo "Building containers..."
docker compose -f ../docker-compose.yml build

echo "Setup Complete. Run 'docker compose -f ../docker-compose.yml up' to start."
