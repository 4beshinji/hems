"""Demurrage — periodic idle-balance tax.

Iterates over all non-system wallets whose balance exceeds the
exemption threshold and burns a percentage, shrinking circulating supply.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal
from models import Wallet
from services.ledger import burn, SYSTEM_USER_ID
from services.monetary_policy import DEMURRAGE_RATE, DEMURRAGE_EXEMPT, calc_demurrage

logger = logging.getLogger(__name__)


async def apply_demurrage() -> None:
    """Apply demurrage to every eligible wallet in a single DB session."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Wallet).filter(
                Wallet.user_id != SYSTEM_USER_ID,
                Wallet.balance > DEMURRAGE_EXEMPT,
            )
        )
        wallets = result.scalars().all()

        if not wallets:
            logger.debug("Demurrage: no eligible wallets")
            return

        total_burned = 0
        count = 0

        for w in wallets:
            decay = calc_demurrage(w.balance)
            if decay <= 0:
                continue
            try:
                await burn(
                    db,
                    user_id=w.user_id,
                    amount=decay,
                    transaction_type="DEMURRAGE",
                    description=f"滞留税 {DEMURRAGE_RATE*100:.0f}%",
                )
                total_burned += decay
                count += 1
            except ValueError as e:
                logger.warning("Demurrage skip user=%d: %s", w.user_id, e)

        await db.commit()
        logger.info(
            "Demurrage applied: %d wallets, %d SOMS burned",
            count, total_burned,
        )
