"""ClassifierCache CRUD — brain persists its learned classifications here.

Entries are keyed by ``(kind, key_hash)`` (unique composite index) so the
brain treats this as a key-value store. ``value_json`` holds the classified
payload; the semantics live in brain and are opaque to the backend.

All routes are admin-only (``HEMS_API_KEY``) — the backend ORM is the source
of truth; no device client needs direct access.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from database import get_db

router = APIRouter(prefix="/classifier-cache", tags=["classifier-cache"])


@router.get("/{kind}/{key_hash}", response_model=schemas.ClassifierCacheRecord)
async def get_entry(kind: str, key_hash: str, db: AsyncSession = Depends(get_db)):
    """Fetch one entry and increment its hit_count (cheap read-through)."""
    result = await db.execute(
        select(models.ClassifierCache).where(
            models.ClassifierCache.kind == kind,
            models.ClassifierCache.key_hash == key_hash,
        )
    )
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    row.hit_count = (row.hit_count or 0) + 1
    await db.commit()
    await db.refresh(row)
    return row


@router.get("", response_model=list[schemas.ClassifierCacheRecord])
async def list_entries(
    kind: Optional[str] = Query(default=None),
    min_hit_count: int = Query(default=0, ge=0),
    source: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List entries, filterable by kind/source/hit_count — used by rule promoter."""
    query = select(models.ClassifierCache)
    if kind is not None:
        query = query.where(models.ClassifierCache.kind == kind)
    if source is not None:
        query = query.where(models.ClassifierCache.source == source)
    if min_hit_count > 0:
        query = query.where(models.ClassifierCache.hit_count >= min_hit_count)
    query = query.order_by(models.ClassifierCache.updated_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("", response_model=schemas.ClassifierCacheRecord, status_code=201)
async def upsert_entry(
    body: schemas.ClassifierCacheEntry,
    db: AsyncSession = Depends(get_db),
):
    """Upsert on ``(kind, key_hash)``. Existing rows preserve hit_count."""
    result = await db.execute(
        select(models.ClassifierCache).where(
            models.ClassifierCache.kind == body.kind,
            models.ClassifierCache.key_hash == body.key_hash,
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        existing.value_json = body.value_json
        existing.source = body.source
        existing.updated_at = datetime.now(timezone.utc)
    else:
        existing = models.ClassifierCache(
            kind=body.kind,
            key_hash=body.key_hash,
            value_json=body.value_json,
            source=body.source,
            hit_count=1,
        )
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return existing


@router.delete("/{kind}/{key_hash}")
async def delete_entry(kind: str, key_hash: str, db: AsyncSession = Depends(get_db)):
    """Remove an entry — used on user_override and rule promotion cleanup."""
    result = await db.execute(
        select(models.ClassifierCache).where(
            models.ClassifierCache.kind == kind,
            models.ClassifierCache.key_hash == key_hash,
        )
    )
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": True, "kind": kind, "key_hash": key_hash}
