# syntax=docker/dockerfile:1.7
ARG GPU_TYPE=none

FROM hems-base:py3.11
ARG GPU_TYPE

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pose inference runs on rtmlib + onnxruntime (CPU EP) — no torch. GPU_TYPE is
# retained for compose compatibility; GPU ONNX EPs (CUDA / ROCm) are an advanced
# opt-in and not wired here.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps "rtmlib>=0.0.13"

RUN chown -R appuser:appgroup /app

COPY --chown=appuser:appgroup src/ .
COPY --chown=appuser:appgroup NOTICE .

# appuser's home is /app (see infra/base). Pin HOME so rtmlib's cache resolves
# to /app/.cache/rtmlib (writable by appuser) at both build and run time.
ENV HOME=/app
USER appuser

# Bake the RTMO ONNX weights into the image (Apache-2.0) so the container needs
# no network at runtime — pinned + offline. Override at build with the same url
# you set for HEMS_PERCEPTION_POSE_MODEL.
ARG POSE_MODEL_URL=https://download.openmmlab.com/mmpose/v1/projects/rtmo/onnx_sdk/rtmo-s_8xb32-600e_body7-640x640-dac2bf74_20231211.zip
RUN python -c "from rtmlib import RTMO; RTMO(onnx_model='${POSE_MODEL_URL}', backend='onnxruntime', device='cpu')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
