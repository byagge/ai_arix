"""Core platform entities: models registry, threads, runs and trace spans.

Everything here is written by real traffic. A run row only exists because a
request was actually executed against a provider.
"""
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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpanKind(str, enum.Enum):
    LLM = "llm"
    RETRIEVAL = "retrieval"
    ROUTER = "router"
    TOOL = "tool"
    GUARDRAIL = "guardrail"


class ThreadSource(str, enum.Enum):
    PLAYGROUND = "playground"
    API = "api"
    TELEGRAM = "telegram"


class ModelRecord(Base):
    """A model exposed by a provider, discovered from that provider's API."""

    __tablename__ = "platform_models"
    __table_args__ = (UniqueConstraint("provider", "model_id", name="uq_provider_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(160), default="")
    context_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_cost_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    @property
    def slug(self) -> str:
        return f"{self.provider}/{self.model_id}"


class Thread(Base):
    """A conversation strand. Created only when a real request arrives."""

    __tablename__ = "platform_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[ThreadSource] = mapped_column(Enum(ThreadSource), default=ThreadSource.PLAYGROUND)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    use_retrieval: Mapped[bool] = mapped_column(Boolean, default=False)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    dialog_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Turn.id"
    )
    runs: Mapped[list["Run"]] = relationship(back_populates="thread", cascade="all, delete-orphan")


class Turn(Base):
    """A single message inside a thread."""

    __tablename__ = "platform_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("platform_threads.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    thread: Mapped["Thread"] = relationship(back_populates="turns")


class Run(Base):
    """One execution against a provider. Holds real latency and token counts."""

    __tablename__ = "platform_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("platform_threads.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.QUEUED, index=True)
    streamed: Mapped[bool] = mapped_column(Boolean, default=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ttft_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_preview: Mapped[str] = mapped_column(Text, default="")
    output_preview: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    thread: Mapped["Thread"] = relationship(back_populates="runs")
    spans: Mapped[list["Span"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Span.started_at"
    )


Index("ix_runs_created_status", Run.created_at, Run.status)


class Span(Base):
    """A timed step within a run: retrieval, routing, provider call, tool."""

    __tablename__ = "platform_spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("platform_runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[SpanKind] = mapped_column(Enum(SpanKind), default=SpanKind.LLM)
    status: Mapped[str] = mapped_column(String(24), default="ok")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["Run"] = relationship(back_populates="spans")
