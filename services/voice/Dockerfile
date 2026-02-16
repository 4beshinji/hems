FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg espeak-ng && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install fastapi uvicorn aiohttp loguru pydub pyyaml edge-tts
RUN mkdir -p /app/audio
COPY src/ .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
