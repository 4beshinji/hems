from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


# --- Task ---

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: int = 2
    zone: Optional[str] = None
    estimated_duration: int = 10
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None


class Task(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    is_completed: bool = False
    is_queued: bool = False
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: int = 2
    zone: Optional[str] = None
    estimated_duration: int = 10
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None
    assigned_to: Optional[int] = None
    accepted_at: Optional[datetime] = None
    last_reminded_at: Optional[datetime] = None
    report_status: Optional[str] = None
    completion_note: Optional[str] = None

    class Config:
        from_attributes = True


class TaskComplete(BaseModel):
    report_status: Optional[str] = None
    completion_note: Optional[str] = None


class TaskAccept(BaseModel):
    user_id: Optional[int] = None


# --- SystemStats ---

class SystemStatsResponse(BaseModel):
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_active: int = 0
    tasks_queued: int = 0
    tasks_completed_last_hour: int = 0


# --- VoiceEvent ---

class VoiceEventCreate(BaseModel):
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"
    motion_id: Optional[str] = None


class VoiceEvent(BaseModel):
    id: int
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"
    motion_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- User ---

class UserCreate(BaseModel):
    username: str
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None


class User(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Zone / Sensor ---

class EnvironmentData(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    co2: Optional[float] = None
    pressure: Optional[float] = None
    light: Optional[float] = None
    voc: Optional[float] = None
    last_update: Optional[float] = None


class OccupancyData(BaseModel):
    count: int = 0
    last_update: Optional[float] = None


class ZoneSnapshot(BaseModel):
    zone_id: str
    environment: EnvironmentData = EnvironmentData()
    occupancy: OccupancyData = OccupancyData()
    events: List[dict] = []


class ZonesUpdate(BaseModel):
    zones: List[ZoneSnapshot]


# --- Shopping List ---

class ShoppingItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: int = 1
    created_by: str = "user"


class ShoppingItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: Optional[int] = None


class ShoppingItem(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_purchased: bool = False
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    last_purchased_at: Optional[datetime] = None
    next_purchase_at: Optional[datetime] = None
    notes: Optional[str] = None
    priority: int = 1
    created_at: Optional[datetime] = None
    purchased_at: Optional[datetime] = None
    created_by: str = "user"
    share_token: Optional[str] = None

    class Config:
        from_attributes = True


class PurchaseHistory(BaseModel):
    id: int
    item_name: str
    category: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    quantity: int = 1
    purchased_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ShoppingStats(BaseModel):
    total_items: int = 0
    purchased_items: int = 0
    pending_items: int = 0
    total_spent_this_month: int = 0
    category_breakdown: dict = {}


class ShoppingShareResponse(BaseModel):
    share_url: str
    token: str
    items: List[ShoppingItem] = []


# --- Chat ---

class ChatMessageSend(BaseModel):
    content: str
    conversation_id: Optional[int] = None


class ChatMessage(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    audio_url: Optional[str] = None
    tool_calls_json: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    user_message: ChatMessage
    assistant_message: ChatMessage
    conversation_id: int


class ConversationSummary(BaseModel):
    id: int
    title: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_message: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    id: int
    title: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: List[ChatMessage] = []

    class Config:
        from_attributes = True
