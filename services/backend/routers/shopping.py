import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func

import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_USER = os.getenv("MQTT_USER", "hems")
MQTT_PASS = os.getenv("MQTT_PASS", "hems_dev_mqtt")

router = APIRouter(prefix="/shopping", tags=["shopping"])
public_router = APIRouter(prefix="/shopping", tags=["shopping-public"])


def _publish_shopping_event(event_type: str, data: dict):
    """Publish shopping list changes to MQTT."""
    topic = f"hems/shopping/{event_type}"
    payload = json.dumps(data, ensure_ascii=False, default=str)
    try:
        import paho.mqtt.publish as mqtt_publish

        mqtt_publish.single(
            topic,
            payload,
            hostname=MQTT_BROKER,
            auth={"username": MQTT_USER, "password": MQTT_PASS},
        )
    except Exception as e:
        logger.warning("MQTT publish failed for shopping: %s", e)


@router.get("/", response_model=list[schemas.ShoppingItem])
async def list_items(
    category: str | None = None,
    store: str | None = None,
    include_purchased: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.ShoppingItem)
    if not include_purchased:
        query = query.filter(models.ShoppingItem.is_purchased == False)
    if category:
        query = query.filter(models.ShoppingItem.category == category)
    if store:
        query = query.filter(models.ShoppingItem.store == store)
    query = query.order_by(models.ShoppingItem.priority.desc(), models.ShoppingItem.created_at)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=schemas.ShoppingItem)
async def add_item(item: schemas.ShoppingItemCreate, db: AsyncSession = Depends(get_db)):
    # Check for duplicate (same name, not purchased)
    existing = await db.execute(
        select(models.ShoppingItem).filter(
            models.ShoppingItem.name == item.name,
            models.ShoppingItem.is_purchased == False,
        )
    )
    existing_item = existing.scalars().first()
    if existing_item:
        existing_item.quantity += item.quantity
        if item.notes:
            existing_item.notes = item.notes
        if item.priority > existing_item.priority:
            existing_item.priority = item.priority
        await db.commit()
        await db.refresh(existing_item)
        _publish_shopping_event("updated", {"id": existing_item.id, "name": existing_item.name})
        return existing_item

    new_item = models.ShoppingItem(
        name=item.name,
        category=item.category,
        quantity=item.quantity,
        unit=item.unit,
        store=item.store,
        store_category=item.store_category,
        price=item.price,
        is_recurring=item.is_recurring,
        recurrence_days=item.recurrence_days,
        notes=item.notes,
        priority=item.priority,
        created_by=item.created_by,
    )
    if item.is_recurring and item.recurrence_days:
        new_item.next_purchase_at = datetime.now(UTC) + timedelta(days=item.recurrence_days)

    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    _publish_shopping_event(
        "added",
        {
            "id": new_item.id,
            "name": new_item.name,
            "category": new_item.category,
        },
    )
    return new_item


@router.put("/{item_id}", response_model=schemas.ShoppingItem)
async def update_item(
    item_id: int,
    body: schemas.ShoppingItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.id == item_id))
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)

    await db.commit()
    await db.refresh(item)
    _publish_shopping_event(
        "updated",
        {
            "id": item.id,
            "name": item.name,
            "store_category": item.store_category,
        },
    )
    return item


@router.patch("/{item_id}", response_model=schemas.ShoppingItem)
async def patch_item(
    item_id: int,
    body: schemas.ShoppingItemPatch,
    db: AsyncSession = Depends(get_db),
):
    """Partial update — used by brain's shopping classifier to write back store_category."""
    result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.id == item_id))
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return item

    for field_name, value in changes.items():
        setattr(item, field_name, value)

    await db.commit()
    await db.refresh(item)
    _publish_shopping_event(
        "updated",
        {
            "id": item.id,
            "name": item.name,
            "fields": list(changes.keys()),
        },
    )
    return item


@router.put("/{item_id}/purchase", response_model=schemas.ShoppingItem)
async def purchase_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.id == item_id))
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    now = datetime.now(UTC)
    item.is_purchased = True
    item.purchased_at = now
    item.last_purchased_at = now

    # Record purchase history
    history = models.PurchaseHistory(
        item_name=item.name,
        category=item.category,
        store=item.store,
        price=item.price,
        quantity=item.quantity,
    )
    db.add(history)

    # Handle recurring items: create next instance
    if item.is_recurring and item.recurrence_days:
        next_item = models.ShoppingItem(
            name=item.name,
            category=item.category,
            quantity=item.quantity,
            unit=item.unit,
            store=item.store,
            price=item.price,
            is_recurring=True,
            recurrence_days=item.recurrence_days,
            next_purchase_at=now + timedelta(days=item.recurrence_days),
            notes=item.notes,
            priority=item.priority,
            created_by="recurring",
        )
        db.add(next_item)

    await db.commit()
    await db.refresh(item)
    _publish_shopping_event(
        "purchased",
        {
            "id": item.id,
            "name": item.name,
            "price": item.price,
        },
    )
    return item


@router.delete("/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.id == item_id))
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    return {"success": True}


@router.get("/stats", response_model=schemas.ShoppingStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count()).select_from(models.ShoppingItem))).scalar() or 0
    purchased = (
        await db.execute(
            select(func.count()).select_from(models.ShoppingItem).filter(models.ShoppingItem.is_purchased == True)
        )
    ).scalar() or 0
    pending = total - purchased

    # Monthly spend from purchase history
    month_start = datetime.now(UTC).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    monthly_spent = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(models.PurchaseHistory.price * models.PurchaseHistory.quantity),
                    0,
                )
            ).filter(models.PurchaseHistory.purchased_at >= month_start)
        )
    ).scalar() or 0

    # Category breakdown for pending items
    cat_result = await db.execute(
        select(models.ShoppingItem.category, func.count())
        .filter(models.ShoppingItem.is_purchased == False)
        .group_by(models.ShoppingItem.category)
    )
    category_breakdown = {(row[0] or "未分類"): row[1] for row in cat_result.all()}

    return schemas.ShoppingStats(
        total_items=total,
        purchased_items=purchased,
        pending_items=pending,
        total_spent_this_month=monthly_spent,
        category_breakdown=category_breakdown,
    )


@router.get("/categories", response_model=list[str])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.ShoppingItem.category).filter(models.ShoppingItem.category != None).distinct()
    )
    return [row[0] for row in result.all() if row[0]]


@router.get("/stores", response_model=list[str])
async def list_stores(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.ShoppingItem.store).filter(models.ShoppingItem.store != None).distinct())
    return [row[0] for row in result.all() if row[0]]


@router.get("/history", response_model=list[schemas.PurchaseHistory])
async def get_history(
    days: int = Query(default=30, le=365),
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(UTC) - timedelta(days=days)
    query = select(models.PurchaseHistory).filter(models.PurchaseHistory.purchased_at >= since)
    if category:
        query = query.filter(models.PurchaseHistory.category == category)
    query = query.order_by(models.PurchaseHistory.purchased_at.desc()).limit(100)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{item_id}/share", response_model=schemas.ShoppingShareResponse)
async def create_share_link(item_id: int = 0, db: AsyncSession = Depends(get_db)):
    """Generate a share token for the current shopping list.
    item_id=0 means share all pending items."""
    token = secrets.token_urlsafe(16)

    if item_id > 0:
        result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.id == item_id))
        item = result.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        item.share_token = token
        await db.commit()
        items = [item]
    else:
        result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.is_purchased == False))
        items = list(result.scalars().all())
        if not items:
            raise HTTPException(status_code=404, detail="No pending items")
        items[0].share_token = token
        await db.commit()

    base_url = os.getenv("HEMS_EXTERNAL_URL", "http://localhost:8080")
    return schemas.ShoppingShareResponse(
        share_url=f"{base_url}/shopping/shared/{token}",
        token=token,
        items=items,
    )


@router.get("/recurring", response_model=list[schemas.ShoppingItem])
async def get_recurring_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.ShoppingItem)
        .filter(
            models.ShoppingItem.is_recurring == True,
            models.ShoppingItem.is_purchased == False,
        )
        .order_by(models.ShoppingItem.next_purchase_at)
    )
    return result.scalars().all()


@router.get("/due", response_model=list[schemas.ShoppingItem])
async def get_due_items(db: AsyncSession = Depends(get_db)):
    """Get recurring items that are due for purchase."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(models.ShoppingItem)
        .filter(
            models.ShoppingItem.is_recurring == True,
            models.ShoppingItem.is_purchased == False,
            models.ShoppingItem.next_purchase_at != None,
            models.ShoppingItem.next_purchase_at <= now,
        )
        .order_by(models.ShoppingItem.next_purchase_at)
    )
    return result.scalars().all()


# --- Public endpoint (no auth) ---


@public_router.get("/shared/{token}", response_model=list[schemas.ShoppingItem])
async def get_shared_list(token: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint to view a shared shopping list."""
    result = await db.execute(select(models.ShoppingItem).filter(models.ShoppingItem.share_token == token))
    item = result.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Share link not found or expired")

    # Return all pending items
    result = await db.execute(
        select(models.ShoppingItem)
        .filter(models.ShoppingItem.is_purchased == False)
        .order_by(models.ShoppingItem.priority.desc(), models.ShoppingItem.created_at)
    )
    return result.scalars().all()
