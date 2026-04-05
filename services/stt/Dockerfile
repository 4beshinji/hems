FROM python:3.11-slim

ARG GPU_TYPE=none

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch — ROCm or CPU (CUDA uses faster-whisper CTranslate2 instead)
RUN if [ "$GPU_TYPE" = "rocm" ]; then \
      pip install --no-cache-dir torch torchaudio \
        --index-url https://download.pytorch.org/whl/rocm6.3; \
    else \
      pip install --no-cache-dir torch torchaudio --index-url https://download.pytorch.org/whl/cpu; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /app/models \
    && addgroup --system appgroup \
    && adduser --system --ingroup appgroup --home /app appuser \
    && chown -R appuser:appgroup /app /app/models

ENV HOME=/app
ENV HF_HOME=/app/models

COPY src/ .

EXPOSE 8000
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
