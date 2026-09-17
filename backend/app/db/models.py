import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FunnelStage(str, enum.Enum):
    NEW = "new"
    QUALIFICATION = "qualification"
    CONSULTATION = "consultation"
    NEGOTIATION = "negotiation"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    ESCROW = "escrow"
    ESCROW_DRAFT = "escrow_draft"
    COMPLETED = "completed"
    LOST = "lost"


# Re-export for convenience
from app.db.bot_extensions import FollowupMode, WorkStatus  # noqa: E402


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    OPERATOR = "operator"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"
    DRAFT = "draft"  # escrow draft awaiting admin


class PaymentMethod(str, enum.Enum):
    DIRECT_USDT = "direct_usdt"
    ESCROW = "escrow"
    ESCROW_DRAFT = "escrow_draft"


class Dialog(Base):
    __tablename__ = "dialogs"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", "business_connection_id", name="uq_dialog_user_bc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(Integer, index=True)
    # Real Telegram chat_id (for Business chats may differ from user_id)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_connection_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    is_business: Mapped[bool] = mapped_column(Boolean, default=False)
    funnel_stage: Mapped[FunnelStage] = mapped_column(Enum(FunnelStage), default=FunnelStage.NEW)
    ai_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_user_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    next_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_mode: Mapped[str] = mapped_column(String(24), default="standard")
    custom_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    work_status: Mapped[str] = mapped_column(String(24), default="lead", index=True)
    silent_until_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    quoted_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quoted_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quoted_price_max_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    tz_summary: Mapped[str] = mapped_column(Text, default="")
    admin_task_summary: Mapped[str] = mapped_column(Text, default="")
    client_offer_pitch: Mapped[str] = mapped_column(Text, default="")
    awaiting_admin_quote: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_reply_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    client_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id", ondelete="CASCADE"), index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[str] = mapped_column(Text)
    media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    media_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    telegram_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dialog: Mapped["Dialog"] = relationship(back_populates="messages")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id", ondelete="CASCADE"), index=True)
    amount_usdt: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    wallet_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    wallet_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    escrow_deal_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    escrow_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    escrow_draft_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    qr_code_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dialog: Mapped["Dialog"] = relationship(back_populates="orders")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_type: Mapped[str] = mapped_column(String(32))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentSettings(Base):
    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    orchestrator_prompt: Mapped[str] = mapped_column(Text, default="")
    sales_prompt: Mapped[str] = mapped_column(Text, default="")
    followup_prompt: Mapped[str] = mapped_column(Text, default="")
    payment_prompt: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(64), default="professional_friendly")
    autonomy_level: Mapped[int] = mapped_column(Integer, default=8)
    max_followups: Mapped[int] = mapped_column(Integer, default=3)
    followup_delays: Mapped[str] = mapped_column(String(64), default="2,24,72")
    discount_max_percent: Mapped[int] = mapped_column(Integer, default=10)
    reply_delay_min_sec: Mapped[float] = mapped_column(Float, default=3.0)
    reply_delay_max_sec: Mapped[float] = mapped_column(Float, default=8.0)
    force_business_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    global_ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    dialog_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BusinessConnection(Base):
    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    user_chat_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    can_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
