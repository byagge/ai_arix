from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.db.models import FunnelStage, MessageRole, PaymentMethod, PaymentStatus


class MessageOut(BaseModel):
    id: int
    role: MessageRole
    content: str
    agent_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DialogOut(BaseModel):
    id: int
    telegram_user_id: int
    telegram_username: Optional[str] = None
    first_name: Optional[str] = None
    funnel_stage: FunnelStage
    ai_active: bool
    last_message_at: Optional[datetime] = None
    followup_count: int
    message_count: int = 0
    last_message_preview: Optional[str] = None

    model_config = {"from_attributes": True}


class DialogDetail(DialogOut):
    messages: list[MessageOut] = []


class DialogToggleAI(BaseModel):
    ai_active: bool


class SendMessageRequest(BaseModel):
    content: str


class OrderOut(BaseModel):
    id: int
    dialog_id: int
    amount_usdt: float
    description: str
    payment_method: PaymentMethod
    payment_status: PaymentStatus
    wallet_address: Optional[str] = None
    tx_hash: Optional[str] = None
    escrow_url: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class KnowledgeDocOut(BaseModel):
    id: int
    filename: str
    file_type: str
    chunk_count: int
    indexed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentSettingsOut(BaseModel):
    orchestrator_prompt: str
    sales_prompt: str
    followup_prompt: str
    payment_prompt: str
    tone: str
    autonomy_level: int
    max_followups: int
    followup_delays: str
    discount_max_percent: int
    reply_delay_min_sec: float = 3.0
    reply_delay_max_sec: float = 8.0
    force_business_reply: bool = False
    global_ai_enabled: bool = True

    model_config = {"from_attributes": True}


class AgentSettingsUpdate(BaseModel):
    orchestrator_prompt: Optional[str] = None
    sales_prompt: Optional[str] = None
    followup_prompt: Optional[str] = None
    payment_prompt: Optional[str] = None
    tone: Optional[str] = None
    autonomy_level: Optional[int] = Field(None, ge=1, le=10)
    max_followups: Optional[int] = Field(None, ge=0, le=10)
    followup_delays: Optional[str] = None
    discount_max_percent: Optional[int] = Field(None, ge=0, le=50)
    reply_delay_min_sec: Optional[float] = Field(None, ge=0, le=600)
    reply_delay_max_sec: Optional[float] = Field(None, ge=0, le=600)
    force_business_reply: Optional[bool] = None
    global_ai_enabled: Optional[bool] = None


class AgentEventOut(BaseModel):
    id: int
    event_type: str
    agent_name: str
    dialog_id: Optional[int] = None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    status: str = "idle"
    x: float = 0
    y: float = 0


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    active: bool = False


class AgentGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    active_agents: list[str] = []


class DashboardStats(BaseModel):
    total_dialogs: int
    active_dialogs: int
    paid_orders: int
    pending_payments: float
    total_revenue: float
    ai_active_dialogs: int
    manual_dialogs: int
    knowledge_docs: int
