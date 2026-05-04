"""
Configuration for Knowledge Bridge — environment variables.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

# Source directories (JSON array)
# Format: [{"name": "pws", "path": "/sources/pws", "extensions": [".md", ".py", ".json"]}]
_sources_raw = os.getenv("KNOWLEDGE_SOURCES", "[]")
try:
    KNOWLEDGE_SOURCES: list[dict] = json.loads(_sources_raw)
except json.JSONDecodeError:
    KNOWLEDGE_SOURCES = []

# Default extensions applied when source doesn't specify
DEFAULT_EXTENSIONS = [
    ".md",
    ".py",
    ".json",
    ".txt",
    ".pdf",
    ".docx",
    ".csv",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".toml",
    ".rst",
    ".cfg",
]
DEFAULT_EXCLUDE_PATTERNS = [".*", "__pycache__", "node_modules", ".git", ".venv"]

# MQTT
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Index
MAX_SEARCH_RESULTS = int(os.getenv("KNOWLEDGE_MAX_SEARCH_RESULTS", "20"))

# Watcher
WATCHER_DEBOUNCE = float(os.getenv("KNOWLEDGE_WATCHER_DEBOUNCE", "3.0"))

# Embedding (vector search)
EMBEDDING_URL = os.getenv("EMBEDDING_URL", "")  # e.g. http://embed:80 (TEI), http://ollama:11434 (legacy)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_CACHE_DIR = os.getenv("EMBEDDING_CACHE_DIR", "/app/data/embeddings")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

# Hybrid search weights (RRF k parameter, higher = more emphasis on lower-ranked results)
RRF_K = int(os.getenv("RRF_K", "60"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
