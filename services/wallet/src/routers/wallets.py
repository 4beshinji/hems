from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db
from models import LedgerEntry
from schemas import WalletCreate, WalletResponse, LedgerEntryResponse
from services.ledger import get_or_create_wallet

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.post("/", response_model=WalletResponse)
async def create_wallet(body: WalletCreate, db: AsyncSession = Depends(get_db)):
    wallet = await get_or_create_wallet(db, body.user_id)
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.get("/{user_id}", response_model=WalletResponse)
async def get_wallet(user_id: int, db: AsyncSession = Depends(get_db)):
    wallet = await get_or_create_wallet(db, user_id)
    await db.commit()
    return wallet


@router.get("/{user_id}/history", response_model=list[LedgerEntryResponse])
async def get_history(
    user_id: int,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    wallet = await get_or_create_wallet(db, user_id)
    await db.commit()

    entries = await db.execute(
        select(LedgerEntry)
        .filter(LedgerEntry.wallet_id == wallet.id)
        .order_by(LedgerEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return entries.scalars().all()
