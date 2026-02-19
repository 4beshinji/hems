FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir paho-mqtt==2.0.0 python-dotenv==1.0.0

COPY src/ .

CMD ["python", "main.py"]
