"""
Obsidian Bridge — connects Obsidian vault to HEMS via MQTT + REST.
Indexes vault notes, watches for changes, provides search API.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

from config import (
    VAULT_PATH, MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS,
    WATCHER_DEBOUNCE, MAX_SEARCH_RESULTS, LOG_LEVEL,
)
from vault_index import VaultIndex
from vault_watcher import VaultWatcher
from note_writer import NoteWriter
from mqtt_publisher import MQTTPublisher

logger.configure(handlers=[{"sink": "ext://sys.stderr", "level": LOG_LEVEL}])

# Shared state
vault_index = VaultIndex(VAULT_PATH)
mqtt_pub = MQTTPublisher(MQTT_BROKER, MQTT_PORT, MQTT_USER, MQTT_PASS)
watcher = VaultWatcher(vault_index, mqtt_pub, debounce=WATCHER_DEBOUNCE)
note_writer = NoteWriter(VAULT_PATH)
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect MQTT
    mqtt_pub.connect()

    # Build initial index
    vault_index.build_full_index()

    # Start filesystem watcher
    watcher.start()

    # Background tasks
    tasks = [
        asyncio.create_task(watcher.process_loop()),
        asyncio.create_task(watcher.publish_stats_loop()),
    ]
    logger.info(f"Obsidian Bridge started (vault={VAULT_PATH})")
    yield
    for t in tasks:
        t.cancel()
    watcher.stop()
    mqtt_pub.disconnect()


app = FastAPI(title="Obsidian Bridge", lifespan=lifespan)


# --- Request/Response models ---

class SearchRequest(BaseModel):
    query: str = ""
    tags: list[str] | None = None
    path_prefix: str | None = None
    max_results: int = 5

class WriteNoteRequest(BaseModel):
    title: str
    content: str
    tags: list[str] | None = None
    category: str | None = None  # decisions, learnings, or custom

class DecisionLogRequest(BaseModel):
    trigger: str
    action: str
    context: str = ""

class LearningMemoRequest(BaseModel):
    title: str
    content: str


# --- REST endpoints ---

@app.get("/health")
async def health():
    stats = vault_index.get_stats()
    return {
        "status": "ok",
        "vault_path": VAULT_PATH,
        "total_notes": stats["total_notes"],
        "indexed": stats["indexed"],
        "uptime_s": round(time.time() - start_time),
    }


@app.post("/api/notes/search")
async def search_notes(req: SearchRequest):
    """Search vault notes by keyword, tags, or path prefix."""
    max_r = min(req.max_results, MAX_SEARCH_RESULTS)
    results = vault_index.search(
        query=req.query, tags=req.tags,
        path_prefix=req.path_prefix, max_results=max_r,
    )
    return {"results": results, "count": len(results)}


@app.get("/api/notes/recent")
async def get_recent_notes(limit: int = 10):
    """Get most recently modified notes."""
    limit = min(limit, 20)
    notes = vault_index.get_recent(limit=limit)
    return {"notes": notes, "count": len(notes)}


@app.get("/api/notes/read")
async def read_note(path: str):
    """Read a specific note by its vault-relative path."""
    entry = vault_index.notes.get(path)
    if not entry:
        raise HTTPException(404, f"Note not found: {path}")
    return {
        "path": entry.path,
        "title": entry.title,
        "tags": entry.tags,
        "links": entry.links,
        "content": entry.content,
        "word_count": entry.word_count,
        "modified_at": entry.modified_at,
    }


@app.post("/api/notes/write")
async def write_note(req: WriteNoteRequest):
    """Write a note to the vault (HEMS/ directory only)."""
    if len(req.content) > 10000:
        raise HTTPException(400, "Content exceeds 10000 character limit")

    if req.category:
        rel_path = f"HEMS/{req.category}/{req.title}.md"
    else:
        rel_path = f"HEMS/{req.title}.md"

    path = note_writer.write_note(rel_path, req.content, tags=req.tags)
    # Trigger reindex
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@app.post("/api/notes/decision-log")
async def write_decision_log(req: DecisionLogRequest):
    """Append a decision log entry."""
    path = note_writer.write_decision_log(req.trigger, req.action, req.context)
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@app.post("/api/notes/learning-memo")
async def write_learning_memo(req: LearningMemoRequest):
    """Append a learning memo entry."""
    path = note_writer.write_learning_memo(req.title, req.content)
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@app.get("/api/notes/tags")
async def get_all_tags():
    """Get all tags with usage counts."""
    tags = vault_index.get_all_tags()
    return {"tags": tags, "count": len(tags)}
