# syntax=docker/dockerfile:1.7
FROM hems-base:py3.11

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN mkdir -p /app/audio && chown -R appuser:appgroup /app

COPY --chown=appuser:appgroup src/ .

EXPOSE 8000
# Fix shared volume permissions at startup, then drop to appuser
CMD ["sh", "-c", "chown -R appuser:appgroup /app/audio 2>/dev/null; exec su -s /bin/sh appuser -c 'uvicorn main:app --host 0.0.0.0 --port 8000'"]
