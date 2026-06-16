"""
Obsidian Bridge — connects Obsidian vault to HEMS via MQTT + REST.
Indexes vault notes, watches for changes, provides search API.
"""

import sys
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from loguru import logger
from note_writer import NoteWriter
from pydantic import BaseModel
from vault_index import VaultIndex
from vault_watcher import VaultWatcher

from config import (
    LOG_LEVEL,
    MAX_SEARCH_RESULTS,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    VAULT_PATH,
    WATCHER_DEBOUNCE,
)
from hems_common import MqttPublisher, bridge_lifespan, publish_bridge_status, verify_internal_token

logger.configure(handlers=[{"sink": sys.stderr, "level": LOG_LEVEL}])

# Shared state
vault_index = VaultIndex(VAULT_PATH)
# obsidian profile: no retain, debug errors, raise on connect failure, no connection tracking
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
watcher = VaultWatcher(vault_index, mqtt_pub, debounce=WATCHER_DEBOUNCE)
note_writer = NoteWriter(VAULT_PATH)
start_time = time.time()

# Routers: /health stays public for Docker healthchecks; all other REST routes
# require the internal bearer token when HEMS_INTERNAL_TOKEN is configured.
public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(verify_internal_token)])


async def _startup():
    vault_index.build_full_index()
    watcher.start()
    publish_bridge_status(mqtt_pub, "obsidian")


async def _shutdown():
    watcher.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bridge_lifespan(
        app,
        mqtt=mqtt_pub,
        on_startup=_startup,
        task_factories=[watcher.process_loop, watcher.publish_stats_loop],
        on_shutdown=_shutdown,
    ):
        logger.info(f"Obsidian Bridge started (vault={VAULT_PATH})")
        yield
    logger.info("Obsidian Bridge stopped")


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


@public_router.get("/health")
async def health():
    stats = vault_index.get_stats()
    return {
        "status": "ok",
        "vault_path": VAULT_PATH,
        "total_notes": stats["total_notes"],
        "indexed": stats["indexed"],
        "uptime_s": round(time.time() - start_time),
    }


@private_router.post("/api/notes/search")
async def search_notes(req: SearchRequest):
    """Search vault notes by keyword, tags, or path prefix."""
    max_r = min(req.max_results, MAX_SEARCH_RESULTS)
    results = vault_index.search(
        query=req.query,
        tags=req.tags,
        path_prefix=req.path_prefix,
        max_results=max_r,
    )
    return {"results": results, "count": len(results)}


@private_router.get("/api/notes/recent")
async def get_recent_notes(limit: int = 10):
    """Get most recently modified notes."""
    limit = min(limit, 20)
    notes = vault_index.get_recent(limit=limit)
    return {"notes": notes, "count": len(notes)}


@private_router.get("/api/notes/read")
async def read_note(path: str):
    """Read a specific note by its vault-relative path."""
    # Path traversal prevention
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Invalid path: traversal sequences not allowed")
    entry = vault_index.notes.get(path)
    if not entry:
        raise HTTPException(404, "Note not found")
    return {
        "path": entry.path,
        "title": entry.title,
        "tags": entry.tags,
        "links": entry.links,
        "content": entry.content,
        "word_count": entry.word_count,
        "modified_at": entry.modified_at,
    }


@private_router.post("/api/notes/write")
async def write_note(req: WriteNoteRequest):
    """Write a note to the vault (HEMS/ directory only)."""
    if len(req.content) > 10000:
        raise HTTPException(400, "Content exceeds 10000 character limit")

    # Path traversal prevention on user-supplied title and category
    if ".." in req.title or "/" in req.title or req.title.startswith("."):
        raise HTTPException(400, "Invalid title: must not contain path separators or traversal sequences")
    if req.category and (".." in req.category or "/" in req.category or req.category.startswith(".")):
        raise HTTPException(400, "Invalid category: must not contain path separators or traversal sequences")

    if req.category:
        rel_path = f"HEMS/{req.category}/{req.title}.md"
    else:
        rel_path = f"HEMS/{req.title}.md"

    path = note_writer.write_note(rel_path, req.content, tags=req.tags)
    # Trigger reindex
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@private_router.post("/api/notes/decision-log")
async def write_decision_log(req: DecisionLogRequest):
    """Append a decision log entry."""
    path = note_writer.write_decision_log(req.trigger, req.action, req.context)
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@private_router.post("/api/notes/learning-memo")
async def write_learning_memo(req: LearningMemoRequest):
    """Append a learning memo entry."""
    path = note_writer.write_learning_memo(req.title, req.content)
    vault_index.reindex_file(path)
    return {"success": True, "path": path}


@private_router.get("/api/notes/tags")
async def get_all_tags():
    """Get all tags with usage counts."""
    tags = vault_index.get_all_tags()
    return {"tags": tags, "count": len(tags)}


app.include_router(public_router)
app.include_router(private_router)
