"""User feedback collection router for Phase 1 learning loop.

Frontend and other clients POST feedback here; the Brain consumes it via MQTT
or polling and replicates it into the event_store learning mart.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import paho.mqtt.publish as mqtt_publish
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

VALID_TARGET_TYPES = {"task", "voice", "device_action", "approval", "scene", "rule"}
VALID_FEEDBACK_TYPES = {
    "explicit_up",
    "explicit_down",
    "cancel",
    "rerun",
    "snooze",
    "dismiss",
    "complete",
    "implicit_override",
}
VALID_CHANNELS = {"frontend", "voice", "mqtt", "implicit"}


def _mqtt_auth() -> dict:
    auth = None
    if MQTT_USER and MQTT_PASS:
        auth = {"username": MQTT_USER, "password": MQTT_PASS}
    return auth


async def _publish_feedback_event(feedback: models.AgentFeedback) -> None:
    """Notify Brain that a new feedback row is available."""
    try:
        topic = f"hems/feedback/{feedback.target_type}/{feedback.target_id}"
        payload = {
            "feedback_id": feedback.id,
            "target_type": feedback.target_type,
            "target_id": feedback.target_id,
            "feedback_type": feedback.feedback_type,
            "channel": feedback.channel,
            "payload": feedback.payload,
            "context": feedback.context,
            "user_id": feedback.user_id,
            "recorded_at": feedback.recorded_at.isoformat() if feedback.recorded_at else None,
        }
        await asyncio.to_thread(
            mqtt_publish.single,
            topic,
            payload=json.dumps(payload, ensure_ascii=False, default=str),
            hostname=MQTT_BROKER,
            port=MQTT_PORT,
            auth=_mqtt_auth(),
        )
    except Exception as e:
        logger.warning(f"Failed to publish feedback event to MQTT: {e}")


def _feedback_score_from_type(feedback_type: str) -> float | None:
    """Map simple explicit feedback to a numeric score for convenience."""
    return {
        "explicit_up": 1.0,
        "explicit_down": -1.0,
        "cancel": -0.5,
        "rerun": 0.0,
        "snooze": -0.2,
        "dismiss": -0.3,
        "complete": 0.5,
        "implicit_override": -0.5,
    }.get(feedback_type)


@router.post("/", response_model=schemas.AgentFeedback, status_code=201)
async def create_feedback(
    body: schemas.AgentFeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    if body.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"target_type must be one of {sorted(VALID_TARGET_TYPES)}",
        )
    if body.feedback_type not in VALID_FEEDBACK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"feedback_type must be one of {sorted(VALID_FEEDBACK_TYPES)}",
        )
    if body.channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail=f"channel must be one of {sorted(VALID_CHANNELS)}",
        )

    feedback = models.AgentFeedback(
        target_type=body.target_type,
        target_id=body.target_id,
        feedback_type=body.feedback_type,
        channel=body.channel,
        payload=body.payload,
        context=body.context,
        user_id=body.user_id,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    # Best-effort mirror to the target resource for quick UI updates.
    score = _feedback_score_from_type(body.feedback_type)
    if score is not None and body.target_type == "voice":
        try:
            voice_id = int(body.target_id)
            voice_event = await db.execute(select(models.VoiceEvent).filter(models.VoiceEvent.id == voice_id))
            voice = voice_event.scalars().first()
            if voice:
                voice.feedback_score = score
                await db.commit()
        except ValueError:
            pass
    elif score is not None and body.target_type == "device_action":
        try:
            action_id = int(body.target_id)
            action = await db.execute(select(models.DeviceActionLog).filter(models.DeviceActionLog.id == action_id))
            row = action.scalars().first()
            if row:
                row.feedback_score = score
                await db.commit()
        except ValueError:
            pass

    await _publish_feedback_event(feedback)
    return feedback


@router.get("/", response_model=list[schemas.AgentFeedback])
async def list_feedback(
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    feedback_type: str | None = Query(None),
    channel: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(models.AgentFeedback).order_by(models.AgentFeedback.recorded_at.desc())
    if target_type:
        query = query.filter(models.AgentFeedback.target_type == target_type)
    if target_id:
        query = query.filter(models.AgentFeedback.target_id == target_id)
    if feedback_type:
        query = query.filter(models.AgentFeedback.feedback_type == feedback_type)
    if channel:
        query = query.filter(models.AgentFeedback.channel == channel)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/stats", response_model=schemas.AgentFeedbackStats)
async def feedback_stats(
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    hours: int = Query(168, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    query = select(models.AgentFeedback).where(models.AgentFeedback.recorded_at >= since)
    if target_type:
        query = query.where(models.AgentFeedback.target_type == target_type)
    if target_id:
        query = query.where(models.AgentFeedback.target_id == target_id)
    result = await db.execute(query)
    rows: Sequence[models.AgentFeedback] = result.scalars().all()

    stats = schemas.AgentFeedbackStats(target_type=target_type, target_id=target_id)
    stats.total = len(rows)
    for row in rows:
        if row.feedback_type == "explicit_up":
            stats.positive += 1
        elif row.feedback_type == "explicit_down":
            stats.negative += 1
        elif row.feedback_type == "rerun":
            stats.reruns += 1
        elif row.feedback_type == "cancel":
            stats.cancels += 1
    return stats


@router.post("/trajectory", response_model=schemas.AgentTrajectory, status_code=201)
async def create_trajectory(
    body: schemas.AgentTrajectoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Brain posts decision-to-outcome trajectories for learning persistence."""
    trajectory = models.AgentTrajectory(
        cycle_id=body.cycle_id,
        decision_id=body.decision_id,
        timestamp=body.timestamp or datetime.now(UTC),
        trigger_events=body.trigger_events,
        tool_calls=body.tool_calls,
        world_state_snapshot=body.world_state_snapshot,
        outcome_summary=body.outcome_summary,
    )
    db.add(trajectory)
    await db.commit()
    await db.refresh(trajectory)
    return trajectory


@router.get("/trajectory", response_model=list[schemas.AgentTrajectory])
async def list_trajectories(
    cycle_id: str | None = Query(None),
    decision_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(models.AgentTrajectory).order_by(models.AgentTrajectory.timestamp.desc())
    if cycle_id:
        query = query.filter(models.AgentTrajectory.cycle_id == cycle_id)
    if decision_id:
        query = query.filter(models.AgentTrajectory.decision_id == decision_id)
    query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
