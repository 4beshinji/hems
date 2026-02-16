FROM rocm/pytorch:rocm6.4.4_ubuntu22.04_py3.10_pytorch_release_2.7.1

# Maintain directory structure for config path resolution:
#   main.py uses: Path(__file__).parent.parent / "config" / "monitors.yaml"
#   /app/src/main.py -> parent=/app/src -> parent.parent=/app -> /app/config/
WORKDIR /app/src

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy config and source
COPY config/ /app/config/
COPY src/ /app/src/

CMD ["python", "main.py"]
