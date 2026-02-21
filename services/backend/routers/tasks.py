import logging
import os
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from typing import List

from database import get_db
import models
import schemas

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "hems_dev_mqtt")

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _safe_json_loads(value: str | None) -> list:
    """Parse JSON task_type, returning empty list on failure."""
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


async def _get_or_create_system_stats(db: AsyncSession) -> models.SystemStats:
    result = await db.execute(select(models.SystemStats).filter(models.SystemStats.id == 1))
    stats = result.scalars().first()
    if not stats:
        stats = models.SystemStats(id=1, total_xp=0, tasks_completed=0, tasks_created=0)
        db.add(stats)
        await db.flush()
    return stats


def _publish_task_report(task: models.Task):
    """Publish task completion report to MQTT for Brain consumption."""
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


def _task_to_response(task_model: models.Task) -> schemas.Task:
    return schemas.Task(
        id=task_model.id,
        title=task_model.title,
        description=task_model.description,
        location=task_model.location,
        xp_reward=task_model.xp_reward,
        is_completed=task_model.is_completed,
        is_queued=task_model.is_queued,
        created_at=task_model.created_at,
        completed_at=task_model.completed_at,
        dispatched_at=task_model.dispatched_at,
        expires_at=task_model.expires_at,
        task_type=_safe_json_loads(task_model.task_type),
        urgency=task_model.urgency,
        zone=task_model.zone,
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


@router.get("/", response_model=List[schemas.Task])
async def read_tasks(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    query = select(models.Task).filter(
        (models.Task.expires_at == None) | (models.Task.expires_at > func.now())
    ).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_task_to_response(t) for t in result.scalars().all()]


@router.post("/", response_model=schemas.Task)
async def create_task(task: schemas.TaskCreate, db: AsyncSession = Depends(get_db)):
    # Duplicate Check Stage 1: exact title + location
    query = select(models.Task).filter(
        models.Task.title == task.title,
        models.Task.location == task.location,
        models.Task.is_completed == False
    )
    result = await db.execute(query)
    existing_task = result.scalars().first()

    # Duplicate Check Stage 2: same zone + overlapping task_type
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
                if new_types & existing_types:
                    existing_task = candidate
                    break

    if existing_task:
        existing_task.description = task.description
        existing_task.xp_reward = task.xp_reward
        existing_task.expires_at = task.expires_at
        existing_task.task_type = json.dumps(task.task_type) if task.task_type else None
        existing_task.urgency = task.urgency
        existing_task.zone = task.zone
        existing_task.estimated_duration = task.estimated_duration
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
        xp_reward=task.xp_reward,
        expires_at=task.expires_at,
        task_type=json.dumps(task.task_type) if task.task_type else None,
        urgency=task.urgency,
        zone=task.zone,
        estimated_duration=task.estimated_duration,
        is_queued=False,
        dispatched_at=func.now(),
        announcement_audio_url=getattr(task, 'announcement_audio_url', None),
        announcement_text=getattr(task, 'announcement_text', None),
        completion_audio_url=getattr(task, 'completion_audio_url', None),
        completion_text=getattr(task, 'completion_text', None),
    )
    db.add(new_task)

    sys_stats = await _get_or_create_system_stats(db)
    sys_stats.tasks_created += 1

    await db.commit()
    await db.refresh(new_task)
    return _task_to_response(new_task)


@router.put("/{task_id}/accept", response_model=schemas.Task)
async def accept_task(task_id: int, body: schemas.TaskAccept, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.is_completed:
        raise HTTPException(status_code=400, detail="Task already completed")
    if task.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Task already accepted")

    task.assigned_to = body.user_id
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

    if body:
        if body.report_status:
            task.report_status = body.report_status
        if body.completion_note:
            task.completion_note = body.completion_note[:500]

    sys_stats = await _get_or_create_system_stats(db)
    sys_stats.total_xp += task.xp_reward or 0
    sys_stats.tasks_completed += 1

    # Award points to assigned user
    if task.assigned_to and task.xp_reward:
        user_result = await db.execute(
            select(models.User).filter(models.User.id == task.assigned_to)
        )
        user = user_result.scalars().first()
        if user:
            user.points += task.xp_reward
            point_log = models.PointLog(
                user_id=user.id,
                amount=task.xp_reward,
                reason=f"Task completed: {task.title}",
                task_id=task.id,
            )
            db.add(point_log)

    await db.commit()
    await db.refresh(task)

    _publish_task_report(task)
    return _task_to_response(task)


@router.put("/{task_id}/reminded", response_model=schemas.Task)
async def mark_task_reminded(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.last_reminded_at = func.now()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.get("/queue", response_model=List[schemas.Task])
async def get_queued_tasks(db: AsyncSession = Depends(get_db)):
    query = select(models.Task).filter(
        models.Task.is_queued == True
    ).order_by(models.Task.urgency.desc(), models.Task.created_at)
    result = await db.execute(query)
    return [_task_to_response(t) for t in result.scalars().all()]


@router.put("/{task_id}/dispatch", response_model=schemas.Task)
async def dispatch_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_queued = False
    task.dispatched_at = func.now()
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.get("/stats", response_model=schemas.SystemStatsResponse)
async def get_task_stats(db: AsyncSession = Depends(get_db)):
    queued_result = await db.execute(
        select(func.count()).select_from(models.Task).filter(models.Task.is_queued == True)
    )
    queued_count = queued_result.scalar()

    active_result = await db.execute(
        select(func.count()).select_from(models.Task).filter(
            models.Task.is_completed == False,
            models.Task.is_queued == False
        )
    )
    active_count = active_result.scalar()

    # completed_last_hour — SQLite compatible
    completed_result = await db.execute(
        select(func.count()).select_from(models.Task).filter(
            models.Task.is_completed == True,
            models.Task.completed_at >= func.datetime("now", "-1 hour")
        )
    )
    completed_last_hour = completed_result.scalar()

    sys_stats = await _get_or_create_system_stats(db)
    await db.commit()

    return schemas.SystemStatsResponse(
        total_xp=sys_stats.total_xp,
        tasks_completed=sys_stats.tasks_completed,
        tasks_created=sys_stats.tasks_created,
        tasks_active=active_count or 0,
        tasks_queued=queued_count or 0,
        tasks_completed_last_hour=completed_last_hour or 0,
    )
