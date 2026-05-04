# syntax=docker/dockerfile:1.7
#
# hems-base:py3.11 — shared Python runtime for all HEMS Python services.
#
# Build: docker build -t hems-base:py3.11 infra/base
# (Or via Makefile: `make docker-base`.)
#
# Service Dockerfiles `FROM hems-base:py3.11` get the common deps preinstalled
# (paho-mqtt, fastapi, uvicorn, aiohttp, pydantic, loguru, python-dotenv).
# Their own requirements.txt is still installed on top — pip skips already-
# satisfied packages and upgrades the rest.

FROM python:3.11-slim
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/base-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/base-requirements.txt \
    && rm /tmp/base-requirements.txt

# Standard appuser layout (services may chown /app afterward as needed).
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /app appuser

# Subsequent COPYs in service stages should chown to appuser:appgroup.
