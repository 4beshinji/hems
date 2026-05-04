# syntax=docker/dockerfile:1.7
ARG GPU_TYPE=none

FROM hems-base:py3.11
ARG GPU_TYPE

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# PyTorch — ROCm or CPU. Cache mount keeps pip's download cache between builds.
# CUDA users typically don't need torch (faster-whisper uses CTranslate2 on CUDA).
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ "$GPU_TYPE" = "rocm" ]; then \
      pip install torch torchaudio --index-url https://download.pytorch.org/whl/rocm6.3; \
    else \
      pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu; \
    fi

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN mkdir -p /app/models && chown -R appuser:appgroup /app

ENV HOME=/app
ENV HF_HOME=/app/models

COPY --chown=appuser:appgroup src/ .

EXPOSE 8000
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
