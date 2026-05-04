# syntax=docker/dockerfile:1.7
FROM hems-base:py3.11

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

# /app/data is a docker volume mount target; ensure the image-level dir exists
# with the correct owner so a freshly-created (empty) named volume inherits
# appuser:appgroup. Long-lived volumes keep their own ownership — see CHANGELOG
# for guidance on rotating stale volumes.
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
