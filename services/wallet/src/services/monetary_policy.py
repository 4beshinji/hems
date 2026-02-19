"""Monetary policy logic — fee calculation, minimum transfer, demurrage.

Centralises all deflationary parameters so they can be tuned in one place.
"""

import math
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import SupplyStats

logger = logging.getLogger(__name__)

# ── Fee parameters ──────────────────────────────────────────────
FEE_RATE = 0.05        # 5 % of P2P transfer amount
MIN_FEE = 1            # floor: at least 1 SOMS burned per transfer

# ── Minimum transfer ────────────────────────────────────────────
BASE_MIN_TRANSFER = 10  # absolute floor

# ── Demurrage (idle-balance tax) ────────────────────────────────
DEMURRAGE_RATE = 0.02       # 2 % per interval
DEMURRAGE_INTERVAL = 86400  # seconds (24 h)
DEMURRAGE_EXEMPT = 100      # balances <= this are not taxed


def calc_fee(amount: int) -> int:
    """Return the burn fee for a P2P transfer (rounded up)."""
    return max(MIN_FEE, math.ceil(amount * FEE_RATE))


def calc_min_transfer(circulating: int) -> int:
    """Dynamic minimum transfer amount: max(10, circulating // 10_000)."""
    return max(BASE_MIN_TRANSFER, circulating // 10_000)


def calc_demurrage(balance: int) -> int:
    """Demurrage amount for a single wallet (truncated, exempt-aware)."""
    if balance <= DEMURRAGE_EXEMPT:
        return 0
    return int(balance * DEMURRAGE_RATE)  # floor


async def get_circulating(db: AsyncSession) -> int:
    """Read current circulating supply from SupplyStats."""
    result = await db.execute(select(SupplyStats))
    stats = result.scalars().first()
    return stats.circulating if stats else 0
