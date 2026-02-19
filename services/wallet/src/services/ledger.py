"""Double-entry bookkeeping core logic.

Every transaction creates exactly 2 LedgerEntry rows with the same
transaction_id: one DEBIT (amount < 0) and one CREDIT (amount > 0).

Wallet balances are updated in the same DB transaction using
SELECT ... FOR UPDATE (ordered by wallet id to avoid deadlocks).
"""

import uuid
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Wallet, LedgerEntry, SupplyStats

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = 0  # System wallet (currency issuer)


async def ensure_system_wallet(db: AsyncSession) -> Wallet:
    """Create the system wallet (user_id=0) if it doesn't exist."""
    result = await db.execute(
        select(Wallet).filter(Wallet.user_id == SYSTEM_USER_ID)
    )
    wallet = result.scalars().first()
    if not wallet:
        wallet = Wallet(user_id=SYSTEM_USER_ID, balance=0)
        db.add(wallet)
        await db.flush()
    return wallet


async def get_or_create_wallet(db: AsyncSession, user_id: int) -> Wallet:
    """Get wallet by user_id, creating one if it doesn't exist."""
    result = await db.execute(
        select(Wallet).filter(Wallet.user_id == user_id)
    )
    wallet = result.scalars().first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.add(wallet)
        await db.flush()
    return wallet


async def transfer(
    db: AsyncSession,
    from_user_id: int,
    to_user_id: int,
    amount: int,
    transaction_type: str,
    description: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> uuid.UUID:
    """Execute a double-entry transfer between two wallets.

    Args:
        amount: positive integer in milli-units
        reference_id: idempotency key (e.g. "task:42")

    Returns:
        transaction_id (UUID)

    Raises:
        ValueError: insufficient funds, same-wallet transfer, or duplicate reference
    """
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")
    if from_user_id == to_user_id:
        raise ValueError("Cannot transfer to the same wallet")

    # Idempotency check
    if reference_id:
        existing = await db.execute(
            select(LedgerEntry).filter(LedgerEntry.reference_id == reference_id).limit(1)
        )
        if existing.scalars().first():
            raise ValueError("Already claimed")

    # Lock wallets in id order to prevent deadlocks; auto-create if missing
    user_ids = sorted([from_user_id, to_user_id])
    wallets = {}
    for uid in user_ids:
        result = await db.execute(
            select(Wallet).filter(Wallet.user_id == uid).with_for_update()
        )
        w = result.scalars().first()
        if not w:
            w = Wallet(user_id=uid, balance=0)
            db.add(w)
            await db.flush()
        wallets[uid] = w

    from_wallet = wallets[from_user_id]
    to_wallet = wallets[to_user_id]

    # System wallet (user_id=0) can go negative; others cannot
    if from_user_id != SYSTEM_USER_ID and from_wallet.balance < amount:
        raise ValueError("Insufficient funds")

    # Update balances
    from_wallet.balance -= amount
    to_wallet.balance += amount

    txn_id = uuid.uuid4()

    # Debit entry (from)
    debit = LedgerEntry(
        transaction_id=txn_id,
        wallet_id=from_wallet.id,
        amount=-amount,
        balance_after=from_wallet.balance,
        entry_type="DEBIT",
        transaction_type=transaction_type,
        description=description,
        reference_id=reference_id,
        counterparty_wallet_id=to_wallet.id,
    )

    # Credit entry (to)
    credit = LedgerEntry(
        transaction_id=txn_id,
        wallet_id=to_wallet.id,
        amount=amount,
        balance_after=to_wallet.balance,
        entry_type="CREDIT",
        transaction_type=transaction_type,
        description=description,
        reference_id=reference_id,
        counterparty_wallet_id=from_wallet.id,
    )

    db.add(debit)
    db.add(credit)

    # Update supply stats for issuance (system → user)
    if from_user_id == SYSTEM_USER_ID:
        await _update_supply(db, issued=amount)

    await db.flush()
    logger.info(
        "Transfer %s: %s -> %s, amount=%d, type=%s, ref=%s",
        txn_id, from_user_id, to_user_id, amount, transaction_type, reference_id,
    )
    return txn_id


async def burn(
    db: AsyncSession,
    user_id: int,
    amount: int,
    transaction_type: str,
    description: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> uuid.UUID:
    """Burn (destroy) currency from a user wallet.

    Creates a single DEBIT entry with no counterparty and increments
    SupplyStats.total_burned so that circulating supply shrinks.

    Raises:
        ValueError: insufficient funds or invalid amount
    """
    if amount <= 0:
        raise ValueError("Burn amount must be positive")

    result = await db.execute(
        select(Wallet).filter(Wallet.user_id == user_id).with_for_update()
    )
    wallet = result.scalars().first()
    if not wallet:
        raise ValueError(f"Wallet not found for user {user_id}")
    if wallet.balance < amount:
        raise ValueError("Insufficient funds for burn")

    wallet.balance -= amount

    txn_id = uuid.uuid4()

    entry = LedgerEntry(
        transaction_id=txn_id,
        wallet_id=wallet.id,
        amount=-amount,
        balance_after=wallet.balance,
        entry_type="DEBIT",
        transaction_type=transaction_type,
        description=description,
        reference_id=reference_id,
        counterparty_wallet_id=None,
    )
    db.add(entry)

    await _update_supply(db, burned=amount)
    await db.flush()
    logger.info(
        "Burn %s: user=%d, amount=%d, type=%s",
        txn_id, user_id, amount, transaction_type,
    )
    return txn_id


async def _update_supply(db: AsyncSession, issued: int = 0, burned: int = 0):
    """Update the single-row supply_stats tracker."""
    result = await db.execute(
        select(SupplyStats).with_for_update()
    )
    stats = result.scalars().first()
    if not stats:
        stats = SupplyStats(total_issued=0, total_burned=0, circulating=0)
        db.add(stats)
        await db.flush()
        # Re-select with lock
        result = await db.execute(
            select(SupplyStats).with_for_update()
        )
        stats = result.scalars().first()

    stats.total_issued += issued
    stats.total_burned += burned
    stats.circulating = stats.total_issued - stats.total_burned
