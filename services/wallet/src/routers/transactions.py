from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID

from database import get_db
from models import LedgerEntry
from schemas import (
    TaskRewardRequest,
    P2PTransferRequest,
    TransactionResponse,
    LedgerEntryResponse,
    TransferFeeInfo,
    P2PTransferResponse,
)
from services.ledger import transfer, burn, get_or_create_wallet, SYSTEM_USER_ID
from services.monetary_policy import (
    FEE_RATE,
    calc_fee,
    calc_min_transfer,
    get_circulating,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/task-reward", response_model=TransactionResponse)
async def task_reward(body: TaskRewardRequest, db: AsyncSession = Depends(get_db)):
    """Pay task bounty from system wallet to user wallet."""
    reference = f"task:{body.task_id}"
    description = body.description or f"Task #{body.task_id} reward"

    try:
        txn_id = await transfer(
            db,
            from_user_id=SYSTEM_USER_ID,
            to_user_id=body.user_id,
            amount=body.amount,
            transaction_type="TASK_REWARD",
            description=description,
            reference_id=reference,
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return await _get_transaction(db, txn_id)


@router.post("/p2p-transfer", response_model=P2PTransferResponse)
async def p2p_transfer(body: P2PTransferRequest, db: AsyncSession = Depends(get_db)):
    """Transfer funds between two user wallets (fee is burned)."""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    # Minimum transfer check
    circulating = await get_circulating(db)
    min_transfer = calc_min_transfer(circulating)
    if body.amount < min_transfer:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum transfer is {min_transfer} SOMS",
        )

    fee = calc_fee(body.amount)
    total_cost = body.amount + fee

    # Pre-check balance so the error message is clear
    sender = await get_or_create_wallet(db, body.from_user_id)
    if sender.balance < total_cost:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance (required: {total_cost} SOMS = transfer {body.amount} + fee {fee})",
        )

    try:
        # 1) Transfer the principal
        txn_id = await transfer(
            db,
            from_user_id=body.from_user_id,
            to_user_id=body.to_user_id,
            amount=body.amount,
            transaction_type="P2P_TRANSFER",
            description=body.description,
        )
        # 2) Burn the fee from sender
        await burn(
            db,
            user_id=body.from_user_id,
            amount=fee,
            transaction_type="FEE_BURN",
            description=f"送金手数料 {FEE_RATE*100:.0f}%",
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    # Build response with fee info
    result = await db.execute(
        select(LedgerEntry)
        .filter(LedgerEntry.transaction_id == txn_id)
        .order_by(LedgerEntry.id)
    )
    entries = result.scalars().all()

    return P2PTransferResponse(
        transaction_id=txn_id,
        entries=entries,
        fee=TransferFeeInfo(
            fee_rate=FEE_RATE,
            fee_amount=fee,
            net_amount=body.amount,
            min_transfer=min_transfer,
            below_minimum=False,
        ),
    )


@router.get("/transfer-fee", response_model=TransferFeeInfo)
async def transfer_fee_preview(
    amount: int = Query(..., gt=0, description="Transfer amount"),
    db: AsyncSession = Depends(get_db),
):
    """Preview the fee and minimum transfer for a given amount."""
    circulating = await get_circulating(db)
    min_transfer = calc_min_transfer(circulating)
    fee = calc_fee(amount)
    return TransferFeeInfo(
        fee_rate=FEE_RATE,
        fee_amount=fee,
        net_amount=amount,
        min_transfer=min_transfer,
        below_minimum=amount < min_transfer,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _get_transaction(db, transaction_id)


async def _get_transaction(db: AsyncSession, txn_id: UUID) -> TransactionResponse:
    result = await db.execute(
        select(LedgerEntry)
        .filter(LedgerEntry.transaction_id == txn_id)
        .order_by(LedgerEntry.id)
    )
    entries = result.scalars().all()
    if not entries:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponse(transaction_id=txn_id, entries=entries)
