from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# Wallet
class WalletCreate(BaseModel):
    user_id: int

class WalletResponse(BaseModel):
    id: int
    user_id: int
    balance: int  # milli-units
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Ledger
class LedgerEntryResponse(BaseModel):
    id: int
    transaction_id: UUID
    wallet_id: int
    amount: int
    balance_after: int
    entry_type: str
    transaction_type: str
    description: Optional[str] = None
    reference_id: Optional[str] = None
    counterparty_wallet_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    transaction_id: UUID
    entries: List[LedgerEntryResponse]


# Transfer fee info
class TransferFeeInfo(BaseModel):
    fee_rate: float
    fee_amount: int
    net_amount: int      # amount actually received by recipient
    min_transfer: int
    below_minimum: bool  # True when amount < min_transfer

class P2PTransferResponse(BaseModel):
    transaction_id: UUID
    entries: List[LedgerEntryResponse]
    fee: TransferFeeInfo


# Task Reward
class TaskRewardRequest(BaseModel):
    user_id: int
    amount: int  # milli-units
    task_id: int
    description: Optional[str] = None


# P2P Transfer
class P2PTransferRequest(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: int  # milli-units (must be > 0)
    description: Optional[str] = None


# Device
class DeviceCreate(BaseModel):
    device_id: str
    owner_id: int
    device_type: str  # llm_node / sensor_node / hub
    display_name: Optional[str] = None
    topic_prefix: Optional[str] = None

class DeviceUpdate(BaseModel):
    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    topic_prefix: Optional[str] = None

class DeviceResponse(BaseModel):
    id: int
    device_id: str
    owner_id: int
    device_type: str
    display_name: Optional[str] = None
    topic_prefix: Optional[str] = None
    registered_at: datetime
    is_active: bool
    last_heartbeat_at: Optional[datetime] = None
    xp: int = 0
    total_shares: int = 100
    available_shares: int = 0
    share_price: int = 100
    funding_open: bool = False
    power_mode: str = "ALWAYS_ON"
    hops_to_mqtt: int = 0
    battery_pct: Optional[int] = None
    utility_score: float = 1.0

    class Config:
        from_attributes = True


# Device XP
class DeviceXpGrantRequest(BaseModel):
    zone: str
    task_id: int
    xp_amount: int = 10  # XP per device
    event_type: str = "task_created"  # task_created / task_completed


class DeviceXpResponse(BaseModel):
    devices_awarded: int
    total_xp_granted: int
    device_ids: List[str]


# Reward Rate
class RewardRateResponse(BaseModel):
    id: int
    device_type: str
    rate_per_hour: int
    min_uptime_for_reward: int

    class Config:
        from_attributes = True

class RewardRateUpdate(BaseModel):
    rate_per_hour: int
    min_uptime_for_reward: Optional[int] = None


# Device Heartbeat
class HeartbeatResponse(BaseModel):
    device_id: str
    last_heartbeat_at: datetime
    reward_granted: int  # milli-units (0 if not eligible)
    uptime_seconds: int


# Device XP Stats
class DeviceXpStatsResponse(BaseModel):
    total_device_xp: int
    active_devices: int
    top_devices: List[DeviceResponse]


# Supply
class SupplyResponse(BaseModel):
    total_issued: int
    total_burned: int
    circulating: int

    class Config:
        from_attributes = True


# History pagination
class HistoryParams(BaseModel):
    limit: int = 50
    offset: int = 0


# Stake funding (Model A)
class FundingOpenRequest(BaseModel):
    owner_id: int
    shares_to_list: int
    share_price: int  # milli-units per share


class StakeBuyRequest(BaseModel):
    user_id: int
    shares: int  # >= 1


class StakeReturnRequest(BaseModel):
    user_id: int
    shares: int


class StakeResponse(BaseModel):
    id: int
    device_id: int
    user_id: int
    shares: int
    percentage: float  # shares / total_shares * 100
    acquired_at: datetime

    class Config:
        from_attributes = True


class DeviceFundingResponse(BaseModel):
    device_id: str
    total_shares: int
    available_shares: int
    share_price: int
    funding_open: bool
    stakeholders: List[StakeResponse]
    estimated_reward_per_hour: int


class FundingCloseRequest(BaseModel):
    owner_id: int


# Heartbeat with optional metrics
class HeartbeatRequest(BaseModel):
    power_mode: Optional[str] = None
    battery_pct: Optional[int] = None
    hops_to_mqtt: Optional[int] = None
    utility_score: Optional[float] = None


# Utility score update
class UtilityScoreUpdate(BaseModel):
    score: float


# Portfolio
class PortfolioEntry(BaseModel):
    device_id: str
    device_type: str
    shares: int
    total_shares: int
    percentage: float
    estimated_reward_per_hour: int


class PortfolioResponse(BaseModel):
    user_id: int
    stakes: List[PortfolioEntry]
    total_estimated_reward_per_hour: int


# Pool funding (Model B)
class PoolCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    goal_jpy: int
    share_price: int = 100
    total_shares: int = 100


class PoolContributeRequest(BaseModel):
    user_id: int
    amount_jpy: int


class PoolActivateRequest(BaseModel):
    device_id: str  # device_id string to link


class PoolContributionResponse(BaseModel):
    id: int
    pool_id: int
    user_id: int
    amount_jpy: int
    shares_allocated: int
    contributed_at: datetime

    class Config:
        from_attributes = True


class PoolResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    goal_jpy: int
    raised_jpy: int
    share_price: int
    total_shares: int
    status: str
    device_id: Optional[int] = None
    created_at: datetime
    contributions: List[PoolContributionResponse] = []

    class Config:
        from_attributes = True


class PoolListResponse(BaseModel):
    id: int
    title: str
    goal_jpy: int
    raised_jpy: int
    status: str
    progress_pct: float
    created_at: datetime

    class Config:
        from_attributes = True
