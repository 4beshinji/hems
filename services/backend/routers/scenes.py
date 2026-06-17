"""
Scene CRUD + manual execution endpoint.

Scenes are multi-device action sequences with per-action delay_s
(e.g. wake_up: desk light ON → IR ceiling on (+2s) → bulb dim rise).
Execution is proxied to Brain which dispatches each action through DeviceDispatcher.
"""

import logging
import os
from datetime import UTC, datetime

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from database import get_db
from hems_common.auth import internal_auth_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scenes", tags=["scenes"])

BRAIN_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")


@router.get("/", response_model=list[schemas.Scene])
async def list_scenes(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.Scene)
    if enabled_only:
        query = query.filter(models.Scene.is_enabled == True)
    query = query.order_by(models.Scene.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{scene_id}", response_model=schemas.Scene)
async def get_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Scene).filter(models.Scene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.post("/", response_model=schemas.Scene)
async def create_scene(body: schemas.SceneCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(models.Scene).filter(models.Scene.name == body.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"Scene '{body.name}' already exists")
    scene = models.Scene(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        actions=[a.model_dump() for a in body.actions],
        is_enabled=body.is_enabled,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene


@router.put("/{scene_id}", response_model=schemas.Scene)
async def update_scene(
    scene_id: int,
    body: schemas.SceneUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.Scene).filter(models.Scene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    updates = body.model_dump(exclude_unset=True)
    if "actions" in updates and updates["actions"] is not None:
        updates["actions"] = [a if isinstance(a, dict) else a.model_dump() for a in updates["actions"]]
    for field, value in updates.items():
        setattr(scene, field, value)
    await db.commit()
    await db.refresh(scene)
    return scene


@router.delete("/{scene_id}")
async def delete_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Scene).filter(models.Scene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    await db.delete(scene)
    await db.commit()
    return {"success": True}


@router.post("/{scene_id}/execute", response_model=schemas.SceneExecuteResponse)
async def execute_scene(scene_id: int, db: AsyncSession = Depends(get_db)):
    """Proxy scene execution to Brain; record stats on success."""
    result = await db.execute(select(models.Scene).filter(models.Scene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    if not scene.is_enabled:
        raise HTTPException(status_code=400, detail="Scene is disabled")

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"{BRAIN_URL}/scenes/execute",
                json={"name": scene.name, "actions": scene.actions},
                headers=internal_auth_headers(),
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp,
        ):
            data = await resp.json()
            if resp.status != 200:
                return schemas.SceneExecuteResponse(
                    success=False,
                    executed=0,
                    errors=[data.get("detail", f"HTTP {resp.status}")],
                )
            scene.last_executed_at = datetime.now(UTC)
            scene.execution_count = (scene.execution_count or 0) + 1
            await db.commit()
            return schemas.SceneExecuteResponse(
                success=data.get("success", True),
                executed=data.get("executed", 0),
                errors=data.get("errors", []),
            )
    except Exception as e:
        logger.error(f"Scene execute proxy failed: {e}")
        return schemas.SceneExecuteResponse(success=False, executed=0, errors=[str(e)])
