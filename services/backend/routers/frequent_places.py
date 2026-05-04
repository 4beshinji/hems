"""
FrequentPlace CRUD — geofence targets for mobile reminders.

A FrequentPlace is a named location (supermarket, drugstore, …) with a radius.
The mobile app registers an Android GeofencingClient geofence per enabled row
and fires the matching shopping-reminder voice clip when the user enters it.

Categories are small, open-ended, and advisory only — matched against
``ShoppingItem.store_category`` at capsule-build time.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frequent-places", tags=["frequent-places"])


@router.get("/", response_model=list[schemas.FrequentPlace])
async def list_places(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(models.FrequentPlace)
    if enabled_only:
        query = query.filter(models.FrequentPlace.enabled == True)
    query = query.order_by(models.FrequentPlace.category, models.FrequentPlace.label)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{place_id}", response_model=schemas.FrequentPlace)
async def get_place(place_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.FrequentPlace).filter(models.FrequentPlace.id == place_id))
    place = result.scalars().first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    return place


@router.post("/", response_model=schemas.FrequentPlace)
async def create_place(
    body: schemas.FrequentPlaceCreate,
    db: AsyncSession = Depends(get_db),
):
    place = models.FrequentPlace(
        label=body.label,
        category=body.category,
        lat=body.lat,
        lon=body.lon,
        radius_m=body.radius_m,
        enabled=body.enabled,
        cooldown_min=body.cooldown_min,
    )
    db.add(place)
    await db.commit()
    await db.refresh(place)
    return place


@router.put("/{place_id}", response_model=schemas.FrequentPlace)
async def update_place(
    place_id: int,
    body: schemas.FrequentPlaceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(models.FrequentPlace).filter(models.FrequentPlace.id == place_id))
    place = result.scalars().first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(place, field_name, value)

    await db.commit()
    await db.refresh(place)
    return place


@router.delete("/{place_id}")
async def delete_place(place_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.FrequentPlace).filter(models.FrequentPlace.id == place_id))
    place = result.scalars().first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    await db.delete(place)
    await db.commit()
    return {"deleted": True, "id": place_id}
