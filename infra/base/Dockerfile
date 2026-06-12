# syntax=docker/dockerfile:1.7
#
# hems-base:py3.11 — shared Python runtime for all HEMS Python services.
#
# Build (context is the REPO ROOT, so services/_common can be copied in):
#   docker build -t hems-base:py3.11 -f infra/base/Dockerfile .
# (Or via Makefile: `make docker-base`, or
#  `docker compose --profile bootstrap build base`.)
#
# Service Dockerfiles `FROM hems-base:py3.11` get the common deps preinstalled
# (paho-mqtt, fastapi, uvicorn, aiohttp, pydantic, loguru, python-dotenv) plus
# the `hems_common` package (shared bridge infra). Their own requirements.txt
# is still installed on top — pip skips already-satisfied packages and upgrades
# the rest.

FROM python:3.11-slim
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY infra/base/requirements.txt /tmp/base-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/base-requirements.txt \
    && rm /tmp/base-requirements.txt

# Shared bridge infra package, installed into site-packages so every service
# image can `import hems_common` without relying on a bind mount.
COPY services/_common /tmp/_common
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/_common \
    && rm -rf /tmp/_common

# Standard appuser layout (services may chown /app afterward as needed).
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /app appuser

# Subsequent COPYs in service stages should chown to appuser:appgroup.
