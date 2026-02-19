from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, Boolean, DateTime, Text,
    CheckConstraint, UniqueConstraint, ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from database import Base
import uuid


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        CheckConstraint("balance >= 0 OR user_id = 0", name="ck_wallets_balance_non_negative"),
        {"schema": "wallet"},
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    balance = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_transaction_id", "transaction_id"),
        Index("ix_ledger_wallet_created", "wallet_id", "created_at"),
        Index("ix_ledger_reference", "reference_id"),
        {"schema": "wallet"},
    )

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    transaction_id = Column(PG_UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    wallet_id = Column(Integer, ForeignKey("wallet.wallets.id"), nullable=False)
    amount = Column(BigInteger, nullable=False)  # positive=credit, negative=debit
    balance_after = Column(BigInteger, nullable=False)
    entry_type = Column(String(50), nullable=False)  # DEBIT / CREDIT
    transaction_type = Column(String(50), nullable=False)  # INFRASTRUCTURE_REWARD / TASK_REWARD / P2P_TRANSFER
    description = Column(Text, nullable=True)
    reference_id = Column(String(200), nullable=True)  # idempotency key
    counterparty_wallet_id = Column(Integer, ForeignKey("wallet.wallets.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "wallet"}

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(200), unique=True, nullable=False, index=True)
    owner_id = Column(Integer, nullable=False)
    device_type = Column(String(50), nullable=False)  # llm_node / sensor_node / hub
    display_name = Column(String(200), nullable=True)
    topic_prefix = Column(String(500), nullable=True)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    xp = Column(BigInteger, default=0, nullable=False)  # device experience points

    # Stake funding model
    total_shares = Column(BigInteger, default=100, nullable=False)
    available_shares = Column(BigInteger, default=0, nullable=False)
    share_price = Column(BigInteger, default=100, nullable=False)  # 1 share = 100 milli-units
    funding_open = Column(Boolean, default=False, nullable=False)

    # Device metrics (updated from Brain heartbeat)
    power_mode = Column(String(20), default="ALWAYS_ON")
    hops_to_mqtt = Column(Integer, default=0)
    battery_pct = Column(Integer, nullable=True)

    # Utility score (dynamic, updated from Brain)
    utility_score = Column(Float, default=1.0, nullable=False)


class RewardRate(Base):
    __tablename__ = "reward_rates"
    __table_args__ = {"schema": "wallet"}

    id = Column(Integer, primary_key=True, index=True)
    device_type = Column(String(50), unique=True, nullable=False)
    rate_per_hour = Column(BigInteger, nullable=False)  # milli-units per hour
    min_uptime_for_reward = Column(Integer, default=300)  # seconds


class SupplyStats(Base):
    __tablename__ = "supply_stats"
    __table_args__ = {"schema": "wallet"}

    id = Column(Integer, primary_key=True, index=True)
    total_issued = Column(BigInteger, default=0)
    total_burned = Column(BigInteger, default=0)
    circulating = Column(BigInteger, default=0)


class DeviceStake(Base):
    __tablename__ = "device_stakes"
    __table_args__ = (
        UniqueConstraint("device_id", "user_id", name="uq_device_stake"),
        Index("ix_device_stakes_device", "device_id"),
        Index("ix_device_stakes_user", "user_id"),
        CheckConstraint("shares > 0", name="ck_device_stakes_positive"),
        {"schema": "wallet"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey("wallet.devices.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    shares = Column(BigInteger, nullable=False)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FundingPool(Base):
    __tablename__ = "funding_pools"
    __table_args__ = {"schema": "wallet"}

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    goal_jpy = Column(Integer, nullable=False)
    raised_jpy = Column(Integer, default=0, nullable=False)
    share_price = Column(BigInteger, default=100)
    total_shares = Column(BigInteger, default=100)
    status = Column(String(20), default="open")  # open → funded → active → closed
    device_id = Column(Integer, ForeignKey("wallet.devices.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PoolContribution(Base):
    __tablename__ = "pool_contributions"
    __table_args__ = (
        Index("ix_pool_contrib_pool", "pool_id"),
        {"schema": "wallet"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pool_id = Column(Integer, ForeignKey("wallet.funding_pools.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    amount_jpy = Column(Integer, nullable=False)
    shares_allocated = Column(BigInteger, default=0)
    contributed_at = Column(DateTime(timezone=True), server_default=func.now())
