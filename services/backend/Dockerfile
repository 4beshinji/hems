FROM python:3.11-slim
WORKDIR /app
RUN pip install fastapi uvicorn sqlalchemy aiosqlite paho-mqtt pydantic
RUN mkdir -p /app/data
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
