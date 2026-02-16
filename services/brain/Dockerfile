FROM python:3.11-slim
WORKDIR /app
RUN pip install paho-mqtt aiohttp loguru python-dotenv sqlalchemy aiosqlite anthropic pyyaml
RUN mkdir -p /app/data /config
COPY src/ .
CMD ["python", "main.py"]
