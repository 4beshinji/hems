FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
COPY . .
RUN mkdir -p /app/data && chown -R appuser:appgroup /app
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
