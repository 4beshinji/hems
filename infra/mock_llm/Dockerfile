FROM python:3.11-slim

WORKDIR /app

RUN pip install fastapi==0.109.0 uvicorn==0.27.0 python-multipart==0.0.6

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
