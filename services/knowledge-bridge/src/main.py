"""
Knowledge Bridge — multi-format document ingestion service for HEMS.
Hybrid search: BM25 + Vector (Ollama embedding) + Title boost via RRF.
"""

import sys
import time
from contextlib import asynccontextmanager

from document_index import DocumentIndex
from embedding import EmbeddingClient
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from hems_common import MqttPublisher, bridge_lifespan, publish_bridge_status, verify_internal_token
from loguru import logger
from pydantic import BaseModel
from source_watcher import SourceWatcher

from config import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_EXTENSIONS,
    EMBEDDING_CACHE_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_URL,
    KNOWLEDGE_SOURCES,
    LOG_LEVEL,
    MAX_SEARCH_RESULTS,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    WATCHER_DEBOUNCE,
)

logger.configure(handlers=[{"sink": sys.stderr, "level": LOG_LEVEL}])

# Shared state
embedder = EmbeddingClient(
    url=EMBEDDING_URL,
    model=EMBEDDING_MODEL,
    cache_dir=EMBEDDING_CACHE_DIR,
)
doc_index = DocumentIndex(embedding_client=embedder)
# knowledge: no retain, UTF-8 raw, debug errors, raise on connect failure, no connection tracking
mqtt_pub = MqttPublisher(
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_USER,
    MQTT_PASS,
    default_retain=False,
    default_qos=0,
    ensure_ascii=False,
    error_level="debug",
    raise_on_connect_error=True,
    track_connection=False,
    auto_reconnect=False,
)
watcher = SourceWatcher(doc_index, mqtt_pub, debounce=WATCHER_DEBOUNCE)
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _startup():
        # Initialize embedding client (probe Ollama)
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

        # Publish bridge status
        publish_bridge_status(mqtt_pub, "knowledge")

        search_mode = "BM25 + Vector + Title" if embedder.available else "BM25 + Title"
        source_names = [s.get("name") for s in KNOWLEDGE_SOURCES]
        logger.info(
            f"Knowledge Bridge started (sources={source_names}, total={doc_index.get_total_docs()}, search={search_mode})"
        )

    async def _shutdown():
        watcher.stop()
        await embedder.close()

    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=[watcher.process_loop, watcher.publish_stats_loop],
        on_shutdown=_shutdown,
    ):
        yield
    logger.info("Knowledge Bridge stopped")


# Routers: /health stays public for Docker healthchecks; all other REST routes
# require the internal bearer token when HEMS_INTERNAL_TOKEN is configured.
public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(verify_internal_token)])

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


@public_router.get("/health")
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


@private_router.post("/api/knowledge/search")
async def search_documents(req: SearchRequest):
    """Hybrid search across all knowledge sources."""
    max_r = min(req.max_results, MAX_SEARCH_RESULTS)
    results = await doc_index.search(
        query=req.query,
        source=req.source,
        doc_type=req.doc_type,
        tags=req.tags,
        path_prefix=req.path_prefix,
        max_results=max_r,
    )
    return {"results": results, "count": len(results)}


@private_router.get("/api/knowledge/read")
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


@private_router.get("/api/knowledge/sources")
async def list_sources():
    """List all configured knowledge sources with statistics."""
    stats = doc_index.get_source_stats()
    return {"sources": stats, "total_docs": doc_index.get_total_docs()}


@private_router.get("/api/knowledge/recent")
async def get_recent(limit: int = 10, source: str | None = None):
    """Get recently modified documents."""
    limit = min(limit, 50)
    docs = doc_index.get_recent(limit=limit, source=source)
    return {"documents": docs, "count": len(docs)}


@private_router.post("/api/knowledge/reindex")
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


app.include_router(public_router)
app.include_router(private_router)
