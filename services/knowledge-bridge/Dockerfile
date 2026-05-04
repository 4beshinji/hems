# syntax=docker/dockerfile:1.7
FROM hems-base:py3.11

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

RUN chown -R appuser:appgroup /app

COPY --chown=appuser:appgroup src/ .
USER appuser
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
