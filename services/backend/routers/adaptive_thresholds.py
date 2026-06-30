"""Adaptive threshold proposal and adjustment API for Phase 2 learning loop.

Brain drift detectors POST proposals here; frontend approves/rejects them.
Applied offsets are read back by Brain on startup and after daily recalibration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/thresholds", tags=["thresholds"])

VALID_STATUSES = {"proposed", "approved", "rejected", "auto_applied"}
VALID_DECISIONS = {"approve", "reject", "auto_apply"}


@router.post("/proposals", response_model=schemas.ThresholdDriftLog, status_code=201)
async def create_proposal(
    body: schemas.ThresholdDriftLogCreate,
    db: AsyncSession = Depends(get_db),
):
    """Brain posts a detected drift proposal."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(VALID_STATUSES)}",
        )

    # Deduplicate: ignore a repeat proposal for the same metric_key that is still proposed.
    existing = await db.execute(
        select(models.ThresholdDriftLog).where(
            models.ThresholdDriftLog.metric_key == body.metric_key,
            models.ThresholdDriftLog.status == "proposed",
        )
    )
    if existing.scalars().first() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An open proposal already exists for metric_key={body.metric_key}",
        )

    proposal = models.ThresholdDriftLog(
        metric_key=body.metric_key,
        detector=body.detector,
        old_value=body.old_value,
        proposed_value=body.proposed_value,
        reason=body.reason,
        status=body.status,
        context_json=body.context_json,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    logger.info(
        "Threshold drift proposed: metric_key=%s detector=%s old=%s proposed=%s",
        proposal.metric_key,
        proposal.detector,
        proposal.old_value,
        proposal.proposed_value,
    )
    return proposal


@router.get("/proposals", response_model=list[schemas.ThresholdDriftLog])
async def list_proposals(
    status: str | None = Query(None),
    metric_key: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List drift proposals, optionally filtered by status or metric_key."""
    query = select(models.ThresholdDriftLog).order_by(models.ThresholdDriftLog.detected_at.desc())
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of {sorted(VALID_STATUSES)}",
            )
        query = query.where(models.ThresholdDriftLog.status == status)
    if metric_key:
        query = query.where(models.ThresholdDriftLog.metric_key == metric_key)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/proposals/{proposal_id}", response_model=schemas.ThresholdDriftLog)
async def get_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.ThresholdDriftLog).where(models.ThresholdDriftLog.id == proposal_id))
    proposal = result.scalars().first()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@router.post("/proposals/{proposal_id}/decide", response_model=schemas.ThresholdDriftLog)
async def decide_proposal(
    proposal_id: int,
    body: schemas.ThresholdDecideRequest,
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, or auto-apply a drift proposal."""
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"decision must be one of {sorted(VALID_DECISIONS)}",
        )

    result = await db.execute(select(models.ThresholdDriftLog).where(models.ThresholdDriftLog.id == proposal_id))
    proposal = result.scalars().first()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "proposed":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal already decided (status={proposal.status})",
        )

    if body.decision == "reject":
        proposal.status = "rejected"
        proposal.context_json = {
            **proposal.context_json,
            "decided_at": datetime.now(UTC).isoformat(),
            "reviewer_id": body.reviewer_id,
            "decision_reason": body.reason,
        }
        await db.commit()
        await db.refresh(proposal)
        return proposal

    # approve or auto_apply
    approved_by = "auto" if body.decision == "auto_apply" else "user"
    proposal.status = "approved" if body.decision == "approve" else "auto_applied"
    proposal.context_json = {
        **proposal.context_json,
        "decided_at": datetime.now(UTC).isoformat(),
        "reviewer_id": body.reviewer_id,
        "decision_reason": body.reason,
    }

    # Create the adjustment row.
    offset = 0.0
    if proposal.old_value is not None and proposal.proposed_value is not None:
        offset = proposal.proposed_value - proposal.old_value

    adjustment = models.ThresholdAdjustment(
        metric_key=proposal.metric_key,
        base_value=proposal.old_value if proposal.old_value is not None else 0.0,
        offset=offset,
        approved_by=approved_by,
        drift_log_id=proposal.id,
    )
    db.add(adjustment)
    await db.commit()
    await db.refresh(proposal)
    logger.info(
        "Threshold proposal %s: id=%s metric_key=%s offset=%s",
        body.decision,
        proposal.id,
        proposal.metric_key,
        offset,
    )
    return proposal


@router.get("/adjustments", response_model=list[schemas.ThresholdAdjustment])
async def list_adjustments(
    metric_key: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List applied threshold adjustments."""
    query = select(models.ThresholdAdjustment).order_by(models.ThresholdAdjustment.applied_at.desc())
    if metric_key:
        query = query.where(models.ThresholdAdjustment.metric_key == metric_key)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/adjustments", response_model=schemas.ThresholdAdjustment, status_code=201)
async def create_adjustment(
    body: schemas.ThresholdAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for Brain to record auto-applied offsets."""
    adjustment = models.ThresholdAdjustment(
        metric_key=body.metric_key,
        base_value=body.base_value,
        offset=body.offset,
        approved_by=body.approved_by,
        drift_log_id=body.drift_log_id,
    )
    db.add(adjustment)
    await db.commit()
    await db.refresh(adjustment)
    return adjustment
