"""Business Bot MVP models: work statuses, payment templates, ledger."""
from __future__ import annotations

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WorkStatus(str, enum.Enum):
    """Client project status — controls follow-ups and auto-replies."""
    LEAD = "lead"  # new dialog
    QUOTING = "quoting"  # discussing TZ, price, timeline
    AWAITING_ADMIN = "awaiting_admin"  # TZ collected, waiting for admin price
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"  # money received, work not started yet
    IN_PROGRESS = "in_progress"  # «На работе»
    COMPLETED = "completed"  # «Выполнен» — can message again
    PAUSED = "paused"  # client asked to wait / vacation
    LOST = "lost"


class FollowupMode(str, enum.Enum):
    NONE = "none"  # no follow-ups (ordered / paid / in progress)
    STANDARD = "standard"  # every 3 days
    SAME_DAY = "same_day"  # evening reminder if no reply today
    CUSTOM = "custom"  # client gave a specific date
    VACATION = "vacation"  # 7-day interval


class PaymentNetwork(str, enum.Enum):
    USDT_TRON = "usdt-tron"
    USDT_BEP20 = "usdt-bep20"
    USDT_ERC20 = "usdt-erc20"
    USDT_SOL = "usdt-sol"
    USDT_TON = "usdt-ton"
    TON = "ton"
    USDT_POLYGON = "usdt-polygon"
    USDT_ARBITRUM = "usdt-arbitrum"
    USDT_OPTIMISM = "usdt-optimism"
    USDT_AVAX = "usdt-avax"


class PaymentTemplate(Base):
    __tablename__ = "payment_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    network_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    wallet_address: Mapped[str] = mapped_column(String(128), default="")
  # Full message with {amount} placeholder; premium emoji preserved as-is
    message_template: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntry(Base):
    """Simple bookkeeping row for admin exports."""
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    entry_type: Mapped[str] = mapped_column(String(32))  # income | expense | refund
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    network: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
