"""Approval (HITL) request CRUD and decision API.

Brain posts approval requests here; frontend/user fetches the queue and
submits decisions. Decisions are published back to Brain over MQTT or polled
via GET /approvals/{id}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import paho.mqtt.publish as mqtt_publish
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from approval_queue import ApprovalQueueManager
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")


def _mqtt_auth() -> dict:
    auth = None
    if MQTT_USER and MQTT_PASS:
        auth = {"username": MQTT_USER, "password": MQTT_PASS}
    return auth


async def _publish_decision(approval: models.Approval) -> None:
    """Notify Brain that an approval decision is available."""
    try:
        topic = f"hems/approvals/{approval.id}/decide"
        payload = {
            "approval_id": str(approval.id),
            "status": approval.status,
            "decision": approval.decision,
            "reason": approval.decision_reason,
            "reviewer_id": approval.reviewer_id,
            "proposed_payload": approval.proposed_payload,
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
        logger.warning(f"Failed to publish approval decision to MQTT: {e}")


@router.get("/", response_model=list[schemas.Approval])
async def list_approvals(
    status: str | None = Query(None, description="Filter by status"),
    thread_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    manager = ApprovalQueueManager(db)
    return await manager.list_requests(status=status, thread_id=thread_id, limit=limit, offset=offset)


@router.post("/", response_model=schemas.Approval, status_code=201)
async def create_approval(
    body: schemas.ApprovalCreate,
    db: AsyncSession = Depends(get_db),
):
    manager = ApprovalQueueManager(db)
    try:
        return await manager.create(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{approval_id}", response_model=schemas.Approval)
async def get_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
):
    manager = ApprovalQueueManager(db)
    approval = await manager.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/{approval_id}/decide", response_model=schemas.Approval)
async def decide_approval(
    approval_id: str,
    body: schemas.ApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    manager = ApprovalQueueManager(db)
    approval = await manager.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        approval = await manager.decide(approval, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await _publish_decision(approval)
    return approval


@router.post("/{approval_id}/execute", response_model=schemas.Approval)
async def mark_executed(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Brain calls this after it has executed an approved action."""
    manager = ApprovalQueueManager(db)
    approval = await manager.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        return await manager.mark_executed(approval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{approval_id}/rollback", response_model=schemas.RollbackLog)
async def record_rollback(
    approval_id: str,
    trigger: str,
    status: str = "success",
    error_message: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Brain records that a rollback was performed for an approval."""
    manager = ApprovalQueueManager(db)
    approval = await manager.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return await manager.mark_rolled_back(approval, status, trigger, error_message)


@router.post("/{approval_id}/snapshots", response_model=schemas.ActionSnapshot)
async def add_snapshot(
    approval_id: str,
    body: schemas.ActionSnapshotCreate,
    db: AsyncSession = Depends(get_db),
):
    manager = ApprovalQueueManager(db)
    try:
        return await manager.record_snapshot(approval_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/cleanup/expired")
async def cleanup_expired(db: AsyncSession = Depends(get_db)):
    """Manually trigger expiry of stale pending approvals."""
    manager = ApprovalQueueManager(db)
    expired = await manager.expire_stale()
    return {"expired_count": len(expired)}
