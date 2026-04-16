"""
AutomationRule CRUD + test (dry-run) endpoint.

Rules are evaluated by Brain's AutomationEngine (sensor_threshold / schedule /
event / device_state). This router only exposes DB CRUD and stats; Brain pulls
rules via GET /automations/ and pushes fire stats via PUT /automations/{id}/fire.
"""
import logging
import os
from datetime import datetime, timezone
from typing import List

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
import models
import schemas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automations", tags=["automations"])

BRAIN_URL = os.getenv("BRAIN_CHAT_URL", "http://brain:8080")
HEMS_API_KEY = os.getenv("HEMS_API_KEY", "")
_AUTH_HEADERS = {"Authorization": f"Bearer {HEMS_API_KEY}"} if HEMS_API_KEY else {}

_ALLOWED_TRIGGER_TYPES = {"sensor_threshold", "schedule", "event", "device_state"}
_ALLOWED_MODES = {"direct", "llm_review"}


def _validate_trigger(trigger_type: str, cfg: dict) -> str | None:
    if trigger_type == "sensor_threshold":
        if not cfg.get("device_id") or not cfg.get("channel") or cfg.get("value") is None:
            return "sensor_threshold requires device_id, channel, value"
        if cfg.get("op") not in ("<", ">", "<=", ">=", "==", "!="):
            return "sensor_threshold.op must be <, >, <=, >=, ==, !="
    elif trigger_type == "schedule":
        if not (cfg.get("cron") or cfg.get("time")):
            return "schedule requires cron or time"
    elif trigger_type == "event":
        if not cfg.get("event"):
            return "event requires event name"
    elif trigger_type == "device_state":
        if not cfg.get("device_id") or not cfg.get("state_key"):
            return "device_state requires device_id, state_key"
    return None


@router.get("/", response_model=List[schemas.AutomationRule])
async def list_rules(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.AutomationRule)
    if enabled_only:
        query = query.filter(models.AutomationRule.enabled == True)
    query = query.order_by(models.AutomationRule.id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{rule_id}", response_model=schemas.AutomationRule)
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.AutomationRule).filter(models.AutomationRule.id == rule_id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.post("/", response_model=schemas.AutomationRule)
async def create_rule(
    body: schemas.AutomationRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    if body.trigger_type not in _ALLOWED_TRIGGER_TYPES:
        raise HTTPException(status_code=400,
                            detail=f"trigger_type must be one of {sorted(_ALLOWED_TRIGGER_TYPES)}")
    if body.mode not in _ALLOWED_MODES:
        raise HTTPException(status_code=400,
                            detail=f"mode must be one of {sorted(_ALLOWED_MODES)}")
    if body.cooldown_s < 60:
        raise HTTPException(status_code=400, detail="cooldown_s must be >= 60")
    err = _validate_trigger(body.trigger_type, body.trigger_config)
    if err:
        raise HTTPException(status_code=400, detail=err)

    rule = models.AutomationRule(
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        actions=[a.model_dump() for a in body.actions],
        cooldown_s=body.cooldown_s,
        mode=body.mode,
        require_confirm=body.require_confirm,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=schemas.AutomationRule)
async def update_rule(
    rule_id: int,
    body: schemas.AutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.AutomationRule).filter(models.AutomationRule.id == rule_id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates = body.model_dump(exclude_unset=True)
    if "trigger_type" in updates and updates["trigger_type"] not in _ALLOWED_TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid trigger_type")
    if "mode" in updates and updates["mode"] not in _ALLOWED_MODES:
        raise HTTPException(status_code=400, detail="Invalid mode")
    if "cooldown_s" in updates and updates["cooldown_s"] < 60:
        raise HTTPException(status_code=400, detail="cooldown_s must be >= 60")
    if "actions" in updates and updates["actions"] is not None:
        updates["actions"] = [a if isinstance(a, dict) else a.model_dump()
                              for a in updates["actions"]]
    # Validate trigger if type or config changed
    new_type = updates.get("trigger_type", rule.trigger_type)
    new_cfg = updates.get("trigger_config", rule.trigger_config)
    if "trigger_type" in updates or "trigger_config" in updates:
        err = _validate_trigger(new_type, new_cfg)
        if err:
            raise HTTPException(status_code=400, detail=err)

    for field, value in updates.items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.AutomationRule).filter(models.AutomationRule.id == rule_id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"success": True}


@router.put("/{rule_id}/fire", response_model=schemas.AutomationRule)
async def record_fire(
    rule_id: int,
    body: schemas.AutomationRuleFireUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Brain records a successful rule firing — stats only, no action."""
    result = await db.execute(
        select(models.AutomationRule).filter(models.AutomationRule.id == rule_id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.last_fired_at = body.last_fired_at
    rule.fire_count = body.fire_count
    if body.last_evaluation_ts is not None:
        rule.last_evaluation_ts = body.last_evaluation_ts
    await db.commit()
    await db.refresh(rule)
    return rule


@router.post("/{rule_id}/test")
async def test_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Ask Brain to evaluate the rule's trigger without executing actions (dry-run)."""
    result = await db.execute(
        select(models.AutomationRule).filter(models.AutomationRule.id == rule_id)
    )
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    try:
        async with aiohttp.ClientSession(headers=_AUTH_HEADERS) as session:
            async with session.post(
                f"{BRAIN_URL}/automations/evaluate",
                json={
                    "id": rule.id,
                    "trigger_type": rule.trigger_type,
                    "trigger_config": rule.trigger_config,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return {
                    "rule_id": rule.id,
                    "would_fire": data.get("would_fire", False),
                    "reason": data.get("reason", ""),
                    "sampled_value": data.get("sampled_value"),
                }
    except Exception as e:
        logger.error(f"Rule test proxy failed: {e}")
        return {"rule_id": rule.id, "would_fire": False,
                "reason": f"proxy error: {e}"}
