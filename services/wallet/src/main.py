import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.future import select

from database import engine, Base, AsyncSessionLocal
from models import Wallet, RewardRate, SupplyStats
from routers import wallets, transactions, devices, admin, stakes, pools
from services.ledger import SYSTEM_USER_ID
from services.demurrage import apply_demurrage
from services.monetary_policy import DEMURRAGE_INTERVAL

logger = logging.getLogger(__name__)

SEED_REWARD_RATES = [
    {"device_type": "llm_node", "rate_per_hour": 5000, "min_uptime_for_reward": 300},
    {"device_type": "sensor_node", "rate_per_hour": 500, "min_uptime_for_reward": 300},
    {"device_type": "hub", "rate_per_hour": 1000, "min_uptime_for_reward": 300},
    {"device_type": "relay_node", "rate_per_hour": 300, "min_uptime_for_reward": 300},
    {"device_type": "remote_node", "rate_per_hour": 200, "min_uptime_for_reward": 600},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables in wallet schema
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS wallet"))
        await conn.run_sync(Base.metadata.create_all)

    # Seed data
    async with AsyncSessionLocal() as db:
        # System wallet
        result = await db.execute(
            select(Wallet).filter(Wallet.user_id == SYSTEM_USER_ID)
        )
        if not result.scalars().first():
            db.add(Wallet(user_id=SYSTEM_USER_ID, balance=0))

        # Reward rates
        for rate_data in SEED_REWARD_RATES:
            result = await db.execute(
                select(RewardRate).filter(
                    RewardRate.device_type == rate_data["device_type"]
                )
            )
            if not result.scalars().first():
                db.add(RewardRate(**rate_data))

        # Supply stats (single row)
        result = await db.execute(select(SupplyStats))
        if not result.scalars().first():
            db.add(SupplyStats(total_issued=0, total_burned=0, circulating=0))

        await db.commit()

    # Background demurrage loop
    demurrage_task = asyncio.create_task(_demurrage_loop())
    yield
    demurrage_task.cancel()
    try:
        await demurrage_task
    except asyncio.CancelledError:
        pass


async def _demurrage_loop() -> None:
    """Periodically apply demurrage to all eligible wallets."""
    while True:
        await asyncio.sleep(DEMURRAGE_INTERVAL)
        try:
            await apply_demurrage()
        except Exception:
            logger.exception("Demurrage cycle failed")


app = FastAPI(title="SOMS Wallet Service", lifespan=lifespan)

app.include_router(wallets.router)
app.include_router(transactions.router)
app.include_router(devices.router)
app.include_router(admin.router)
app.include_router(stakes.router)
app.include_router(stakes.portfolio_router)
app.include_router(pools.admin_router)
app.include_router(pools.public_router)


@app.get("/")
async def root():
    return {"message": "SOMS Wallet Service Running"}
