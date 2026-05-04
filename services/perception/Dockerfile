# syntax=docker/dockerfile:1.7
ARG GPU_TYPE=none

FROM hems-base:py3.11
ARG GPU_TYPE

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pre-install torch from the right wheel index BEFORE ultralytics resolves it.
# Without this, pip pulls the default GPU build from PyPI (~4GB CUDA libs)
# even on CPU-only hosts.
RUN --mount=type=cache,target=/root/.cache/pip \
    case "$GPU_TYPE" in \
      cuda) pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 ;; \
      rocm) pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.3 ;; \
      *)    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu ;; \
    esac

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN chown -R appuser:appgroup /app

COPY --chown=appuser:appgroup src/ .
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
