"""
Knowledge Bridge — multi-format document ingestion service for HEMS.
Hybrid search: BM25 + Vector (OpenAI-compat embedding, default TEI) + Title boost via RRF.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

from config import (
    KNOWLEDGE_SOURCES, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS,
    WATCHER_DEBOUNCE, MAX_SEARCH_RESULTS, LOG_LEVEL,
    DEFAULT_EXTENSIONS, DEFAULT_EXCLUDE_PATTERNS,
    EMBEDDING_URL, EMBEDDING_MODEL, EMBEDDING_CACHE_DIR, EMBEDDING_BATCH_SIZE,
)
from embedding import EmbeddingClient
from document_index import DocumentIndex
from source_watcher import SourceWatcher
from mqtt_publisher import MQTTPublisher

logger.configure(handlers=[{"sink": "ext://sys.stderr", "level": LOG_LEVEL}])

# Shared state
embedder = EmbeddingClient(
    url=EMBEDDING_URL, model=EMBEDDING_MODEL, cache_dir=EMBEDDING_CACHE_DIR,
)
doc_index = DocumentIndex(embedding_client=embedder)
mqtt_pub = MQTTPublisher(MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
watcher = SourceWatcher(doc_index, mqtt_pub, debounce=WATCHER_DEBOUNCE)
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect MQTT
    mqtt_pub.connect()

    # Initialize embedding client (probe the embeddings server)
    await embedder.initialize()

    # Register and index all sources
    for src in KNOWLEDGE_SOURCES:
        name = src.get("name", "")
        path = src.get("path", "")
        extensions = src.get("extensions", DEFAULT_EXTENSIONS)
        exclude = src.get("exclude_patterns", DEFAULT_EXCLUDE_PATTERNS)
        if not name or not path:
            logger.warning(f"Skipping invalid source config: {src}")
            continue
        doc_index.add_source(name, path, extensions, exclude)
        watcher.add_source(name, path, extensions, exclude)

    # Build BM25 index (sync, fast)
    doc_index.build_all()

    # Build vector index (async, may be slow on first run)
    await doc_index.build_vectors()

    # Start watchers
    watcher.start()

    # Background tasks
    tasks = [
        asyncio.create_task(watcher.process_loop()),
        asyncio.create_task(watcher.publish_stats_loop()),
    ]

    search_mode = "BM25 + Vector + Title" if embedder.available else "BM25 + Title"
    source_names = [s.get("name") for s in KNOWLEDGE_SOURCES]
    logger.info(f"Knowledge Bridge started (sources={source_names}, "
                f"total={doc_index.get_total_docs()}, search={search_mode})")
    yield

    for t in tasks:
        t.cancel()
    watcher.stop()
    await embedder.close()
    mqtt_pub.disconnect()


app = FastAPI(title="Knowledge Bridge", lifespan=lifespan)


# --- Request/Response models ---

class SearchRequest(BaseModel):
    query: str = ""
    source: str | None = None
    doc_type: str | None = None
    tags: list[str] | None = None
    path_prefix: str | None = None
    max_results: int = 10


# --- REST endpoints ---

@app.get("/health")
async def health():
    stats = doc_index.get_source_stats()
    return {
        "status": "ok",
        "total_docs": doc_index.get_total_docs(),
        "sources": stats,
        "search_mode": "hybrid" if embedder.available else "bm25",
        "embedding_model": EMBEDDING_MODEL if embedder.available else None,
        "uptime_s": round(time.time() - start_time),
    }


@app.post("/api/knowledge/search")
async def search_documents(req: SearchRequest):
    """Hybrid search across all knowledge sources."""
    max_r = min(req.max_results, MAX_SEARCH_RESULTS)
    results = await doc_index.search(
        query=req.query, source=req.source, doc_type=req.doc_type,
        tags=req.tags, path_prefix=req.path_prefix, max_results=max_r,
    )
    return {"results": results, "count": len(results)}


@app.get("/api/knowledge/read")
async def read_document(source: str, path: str):
    """Read a specific document by source name and path."""
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid path: traversal sequences not allowed")

    doc_key = f"{source}:{path}"
    entry = doc_index.documents.get(doc_key)
    if not entry:
        raise HTTPException(404, "Document not found")

    return {
        "source": entry.source_name,
        "path": entry.path,
        "title": entry.title,
        "doc_type": entry.doc_type,
        "tags": entry.tags,
        "metadata": entry.metadata,
        "content": entry.content,
        "word_count": entry.word_count,
        "modified_at": entry.modified_at,
    }


@app.get("/api/knowledge/sources")
async def list_sources():
    """List all configured knowledge sources with statistics."""
    stats = doc_index.get_source_stats()
    return {"sources": stats, "total_docs": doc_index.get_total_docs()}


@app.get("/api/knowledge/recent")
async def get_recent(limit: int = 10, source: str | None = None):
    """Get recently modified documents."""
    limit = min(limit, 50)
    docs = doc_index.get_recent(limit=limit, source=source)
    return {"documents": docs, "count": len(docs)}


@app.post("/api/knowledge/reindex")
async def reindex(source: str | None = None):
    """Manually trigger re-indexing (BM25 + vectors)."""
    if source:
        doc_index.build_source_index(source)
        doc_index._rebuild_bm25()
    else:
        doc_index.build_all()
    await doc_index.build_vectors()
    return {
        "success": True,
        "total_docs": doc_index.get_total_docs(),
        "sources": doc_index.get_source_stats(),
    }
