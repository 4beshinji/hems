#!/bin/bash
set -e

echo "Updating package index..."
sudo apt update

echo "Installing Docker and Docker Compose..."
# install docker.io and docker-buildx for compose plugin
sudo apt install -y docker.io docker-buildx docker-compose-v2

echo "Adding user $USER to docker group..."
sudo usermod -aG docker $USER

echo "Docker installation complete."
echo "IMPORTANT: You must log out and log back in (or restart) for the group changes to take effect."
echo "Verifying installation..."
docker --version
docker compose version
