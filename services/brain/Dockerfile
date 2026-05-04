# syntax=docker/dockerfile:1.7
FROM hems-base:py3.11

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# /config is bind-mounted at runtime; /app/data is a named volume mount target.
# Pre-create with correct ownership so empty volumes inherit appuser:appgroup.
RUN mkdir -p /config /app/data && chown -R appuser:appgroup /app

COPY --chown=appuser:appgroup src/ .

USER appuser
EXPOSE 8080
CMD ["python", "main.py"]
