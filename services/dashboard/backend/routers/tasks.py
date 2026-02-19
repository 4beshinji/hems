import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from sqlalchemy import text
from typing import List
import httpx

from database import get_db
import models
import json

logger = logging.getLogger(__name__)

WALLET_SERVICE_URL = os.getenv("WALLET_SERVICE_URL", "http://wallet:8000")
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "soms")
MQTT_PASS = os.getenv("MQTT_PASS", "soms_dev_mqtt")


async def _grant_device_xp(zone: str, task_id: int, xp_amount: int, event_type: str):
    """Fire-and-forget XP grant to zone devices via wallet service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{WALLET_SERVICE_URL}/devices/xp-grant",
                json={
                    "zone": zone,
                    "task_id": task_id,
                    "xp_amount": xp_amount,
                    "event_type": event_type,
                },
            )
    except Exception as e:
        logger.warning("XP grant failed for zone=%s task=%d: %s", zone, task_id, e)


async def _get_zone_multiplier(zone: str) -> float:
    """Fetch reward multiplier for a zone from wallet service. Returns 1.0 on failure."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{WALLET_SERVICE_URL}/devices/zone-multiplier/{zone}")
            if resp.status_code == 200:
                return resp.json().get("multiplier", 1.0)
    except Exception as e:
        logger.warning("Zone multiplier fetch failed for zone=%s: %s", zone, e)
    return 1.0


def _publish_task_report(task: "models.Task"):
    """Publish task completion report to MQTT for Brain consumption (fire-and-forget)."""
    zone = task.zone or "main"
    topic = f"office/{zone}/task_report/{task.id}"
    payload = json.dumps({
        "task_id": task.id,
        "title": task.title,
        "report_status": task.report_status,
        "completion_note": task.completion_note,
        "zone": zone,
    })
    try:
        import paho.mqtt.publish as mqtt_publish
        mqtt_publish.single(
            topic, payload, hostname=MQTT_BROKER,
            auth={"username": MQTT_USER, "password": MQTT_PASS},
        )
        logger.info("Published task report to %s", topic)
    except Exception as e:
        logger.warning("MQTT publish failed for task %d: %s", task.id, e)


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)

import schemas

async def _get_or_create_system_stats(db: AsyncSession) -> models.SystemStats:
    """Get the singleton SystemStats row (id=1), creating it if needed."""
    result = await db.execute(select(models.SystemStats).filter(models.SystemStats.id == 1))
    stats = result.scalars().first()
    if not stats:
        stats = models.SystemStats(id=1, total_xp=0, tasks_completed=0, tasks_created=0)
        db.add(stats)
        await db.flush()
    return stats

@router.get("/", response_model=List[schemas.Task])
async def read_tasks(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    # Filter out expired tasks
    query = select(models.Task).filter(
        (models.Task.expires_at == None) | (models.Task.expires_at > func.now())
    ).offset(skip).limit(limit)
    result = await db.execute(query)
    tasks_db = result.scalars().all()
    
    # Convert DB models to Schema models (handling JSON parsing)
    tasks = []
    for t in tasks_db:
        # Filter out SQLAlchemy internal state and copy dict
        t_dict = {k: v for k, v in t.__dict__.items() if not k.startswith('_')}
        if t.task_type:
            try:
                t_dict['task_type'] = json.loads(t.task_type)
            except:
                t_dict['task_type'] = []
        else:
            t_dict['task_type'] = []
        tasks.append(schemas.Task(**t_dict))
        
    return tasks

def _task_to_response(task_model: models.Task) -> schemas.Task:
    """Convert a Task DB model to a Task schema, handling JSON parsing."""
    return schemas.Task(
        id=task_model.id,
        title=task_model.title,
        description=task_model.description,
        location=task_model.location,
        bounty_gold=task_model.bounty_gold,
        bounty_xp=task_model.bounty_xp,
        is_completed=task_model.is_completed,
        is_queued=task_model.is_queued,
        created_at=task_model.created_at,
        completed_at=task_model.completed_at,
        dispatched_at=task_model.dispatched_at,
        expires_at=task_model.expires_at,
        task_type=json.loads(task_model.task_type) if task_model.task_type else [],
        urgency=task_model.urgency,
        zone=task_model.zone,
        min_people_required=task_model.min_people_required,
        estimated_duration=task_model.estimated_duration,
        announcement_audio_url=task_model.announcement_audio_url,
        announcement_text=task_model.announcement_text,
        completion_audio_url=task_model.completion_audio_url,
        completion_text=task_model.completion_text,
        assigned_to=task_model.assigned_to,
        accepted_at=task_model.accepted_at,
        last_reminded_at=task_model.last_reminded_at,
        report_status=task_model.report_status,
        completion_note=task_model.completion_note,
    )

@router.post("/", response_model=schemas.Task)
async def create_task(task: schemas.TaskCreate, db: AsyncSession = Depends(get_db)):
    # Duplicate Check Stage 1: exact title + location match
    query = select(models.Task).filter(
        models.Task.title == task.title,
        models.Task.location == task.location,
        models.Task.is_completed == False
    )
    result = await db.execute(query)
    existing_task = result.scalars().first()

    # Duplicate Check Stage 2: same zone + overlapping task_type
    # (LLM often generates slightly different titles for the same issue)
    if not existing_task and task.zone and task.task_type:
        query2 = select(models.Task).filter(
            models.Task.zone == task.zone,
            models.Task.is_completed == False
        )
        result2 = await db.execute(query2)
        candidates = result2.scalars().all()
        new_types = set(task.task_type)
        for candidate in candidates:
            if candidate.task_type:
                try:
                    existing_types = set(json.loads(candidate.task_type))
                except (json.JSONDecodeError, TypeError):
                    existing_types = set()
                if new_types & existing_types:  # Any overlap
                    existing_task = candidate
                    break

    if existing_task:
        # Update existing task in place (preserve ID to prevent repeated audio)
        existing_task.description = task.description
        existing_task.bounty_gold = task.bounty_gold
        existing_task.expires_at = task.expires_at
        existing_task.task_type = json.dumps(task.task_type) if task.task_type else None
        existing_task.urgency = task.urgency
        existing_task.zone = task.zone
        existing_task.min_people_required = task.min_people_required
        existing_task.estimated_duration = task.estimated_duration
        # Update voice data only if new data is provided
        if task.announcement_audio_url:
            existing_task.announcement_audio_url = task.announcement_audio_url
        if task.announcement_text:
            existing_task.announcement_text = task.announcement_text
        if task.completion_audio_url:
            existing_task.completion_audio_url = task.completion_audio_url
        if task.completion_text:
            existing_task.completion_text = task.completion_text
        await db.commit()
        await db.refresh(existing_task)
        return _task_to_response(existing_task)

    new_task = models.Task(
        title=task.title,
        description=task.description,
        location=task.location,
        bounty_gold=task.bounty_gold,
        bounty_xp=task.bounty_xp,
        expires_at=task.expires_at,
        task_type=json.dumps(task.task_type) if task.task_type else None,
        urgency=task.urgency,
        zone=task.zone,
        min_people_required=task.min_people_required,
        estimated_duration=task.estimated_duration,
        is_queued=False,
        dispatched_at=func.now(),
        announcement_audio_url=getattr(task, 'announcement_audio_url', None),
        announcement_text=getattr(task, 'announcement_text', None),
        completion_audio_url=getattr(task, 'completion_audio_url', None),
        completion_text=getattr(task, 'completion_text', None)
    )
    db.add(new_task)

    # Increment system tasks_created counter
    sys_stats = await _get_or_create_system_stats(db)
    sys_stats.tasks_created += 1

    await db.commit()
    await db.refresh(new_task)

    # Grant device XP for task creation (fire-and-forget)
    if new_task.zone:
        await _grant_device_xp(new_task.zone, new_task.id, 10, "task_created")

    return _task_to_response(new_task)

@router.put("/{task_id}/accept", response_model=schemas.Task)
async def accept_task(task_id: int, body: schemas.TaskAccept, db: AsyncSession = Depends(get_db)):
    """Assign a task to a user."""
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.is_completed:
        raise HTTPException(status_code=400, detail="Task already completed")
    if task.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Task already accepted")

    task.assigned_to = body.user_id  # None for anonymous kiosk accept
    task.accepted_at = func.now()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.put("/{task_id}/complete", response_model=schemas.Task)
async def complete_task(
    task_id: int,
    body: schemas.TaskComplete = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.is_completed = True
    task.completed_at = func.now()

    # Save completion report if provided
    if body:
        if body.report_status:
            task.report_status = body.report_status
        if body.completion_note:
            task.completion_note = body.completion_note[:500]

    # Accumulate system XP
    sys_stats = await _get_or_create_system_stats(db)
    sys_stats.total_xp += task.bounty_xp or 0
    sys_stats.tasks_completed += 1

    await db.commit()
    await db.refresh(task)

    # Grant device XP for task completion (fire-and-forget)
    if task.zone:
        await _grant_device_xp(task.zone, task.id, 20, "task_completed")

    # Pay bounty via wallet service (fire-and-forget)
    if task.assigned_to and task.bounty_gold:
        # Apply zone device XP multiplier (1.0x-3.0x)
        multiplier = 1.0
        if task.zone:
            multiplier = await _get_zone_multiplier(task.zone)
        adjusted_bounty = int(task.bounty_gold * multiplier)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{WALLET_SERVICE_URL}/transactions/task-reward",
                    json={
                        "user_id": task.assigned_to,
                        "amount": adjusted_bounty,
                        "task_id": task.id,
                        "description": f"Task: {task.title} ({multiplier:.1f}x)",
                    },
                )
        except Exception as e:
            logger.warning("Wallet payment failed for task %d: %s", task.id, e)

    # Publish task report to MQTT (fire-and-forget, for Brain consumption)
    _publish_task_report(task)

    return _task_to_response(task)

@router.put("/{task_id}/reminded", response_model=schemas.Task)
async def mark_task_reminded(task_id: int, db: AsyncSession = Depends(get_db)):
    """Update the last_reminded_at timestamp for a task."""
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.last_reminded_at = func.now()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)
# Queue Management Endpoints

@router.get("/queue", response_model=List[schemas.Task])
async def get_queued_tasks(db: AsyncSession = Depends(get_db)):
    """Get all queued tasks (not yet dispatched to dashboard)."""
    query = select(models.Task).filter(models.Task.is_queued == True).order_by(models.Task.urgency.desc(), models.Task.created_at)
    result = await db.execute(query)
    tasks_db = result.scalars().all()
    
    tasks = []
    for t in tasks_db:
        t_dict = {k: v for k, v in t.__dict__.items() if not k.startswith('_')}
        if t.task_type:
            try:
                t_dict['task_type'] = json.loads(t.task_type)
            except:
                t_dict['task_type'] = []
        else:
            t_dict['task_type'] = []
        tasks.append(schemas.Task(**t_dict))
    
    return tasks


@router.put("/{task_id}/dispatch", response_model=schemas.Task)
async def dispatch_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a queued task as dispatched (send to dashboard)."""
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.is_queued = False
    task.dispatched_at = func.now()
    await db.commit()
    await db.refresh(task)
    
    t_dict = {k: v for k, v in task.__dict__.items() if not k.startswith('_')}
    if task.task_type:
        try:
            t_dict['task_type'] = json.loads(task.task_type)
        except:
            t_dict['task_type'] = []
    else:
        t_dict['task_type'] = []
    
    return schemas.Task(**t_dict)


@router.get("/stats", response_model=schemas.SystemStatsResponse)
async def get_task_stats(db: AsyncSession = Depends(get_db)):
    """Get task statistics including cumulative system XP."""
    # Queued tasks count
    queued_query = select(func.count()).select_from(models.Task).filter(models.Task.is_queued == True)
    queued_result = await db.execute(queued_query)
    queued_count = queued_result.scalar()

    # Completed tasks in last hour
    completed_query = select(func.count()).select_from(models.Task).filter(
        models.Task.is_completed == True,
        models.Task.completed_at >= func.now() - text("interval '1 hour'")
    )
    completed_result = await db.execute(completed_query)
    completed_last_hour = completed_result.scalar()

    # Active (dispatched but not completed)
    active_query = select(func.count()).select_from(models.Task).filter(
        models.Task.is_completed == False,
        models.Task.is_queued == False
    )
    active_result = await db.execute(active_query)
    active_count = active_result.scalar()

    # Cumulative system stats
    sys_stats = await _get_or_create_system_stats(db)
    await db.commit()  # persist if newly created

    return schemas.SystemStatsResponse(
        total_xp=sys_stats.total_xp,
        tasks_completed=sys_stats.tasks_completed,
        tasks_created=sys_stats.tasks_created,
        tasks_active=active_count or 0,
        tasks_queued=queued_count or 0,
        tasks_completed_last_hour=completed_last_hour or 0,
    )
