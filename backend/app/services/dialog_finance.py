"""Shared helpers for dialog finance / serialization."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bot_extensions import LedgerEntry
from app.db.models import Dialog, Message, MessageRole, Order, PaymentStatus


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def serialize_dialog_card(d: Dialog, *, message_count: int = 0, preview: Optional[str] = None) -> dict[str, Any]:
    username = d.telegram_username
    return {
        "id": d.id,
        "telegram_user_id": d.telegram_user_id,
        "telegram_username": username,
        "username": username,
        "first_name": d.first_name,
        "funnel_stage": d.funnel_stage.value if hasattr(d.funnel_stage, "value") else d.funnel_stage,
        "work_status": d.work_status or "lead",
        "ai_active": d.ai_active,
        "quoted_price_usd": d.quoted_price_usd,
        "quoted_days": d.quoted_days,
        "estimated_price_usd": getattr(d, "estimated_price_usd", None),
        "quoted_price_max_usd": getattr(d, "quoted_price_max_usd", None),
        "price_approved": bool(getattr(d, "price_approved", False)),
        "tz_summary": d.tz_summary or "",
        "admin_task_summary": getattr(d, "admin_task_summary", None) or "",
        "client_offer_pitch": getattr(d, "client_offer_pitch", None) or "",
        "awaiting_admin_quote": bool(getattr(d, "awaiting_admin_quote", False)),
        "followup_count": d.followup_count,
        "followup_mode": d.followup_mode or "standard",
        "next_followup_at": _iso(d.next_followup_at),
        "custom_followup_at": _iso(d.custom_followup_at),
        "silent_until_completed": bool(d.silent_until_completed),
        "last_message_at": _iso(d.last_message_at),
        "last_user_message_at": _iso(d.last_user_message_at),
        "created_at": _iso(d.created_at),
        "is_business": bool(d.is_business),
        "business_connection_id": d.business_connection_id,
        "telegram_link": f"https://t.me/{username}" if username else f"tg://user?id={d.telegram_user_id}",
        "account_label": "Business Bot" if d.is_business else "Direct Bot",
        "message_count": message_count,
        "last_message_preview": preview,
        "client_profile": d.client_profile or {},
    }


async def dialog_ai_cost(db: AsyncSession, dialog_id: int) -> dict[str, float | int]:
    """Sum platform thread costs linked to this dialog (if any)."""
    try:
        from app.db.platform_models import Thread

        row = await db.execute(
            select(
                func.coalesce(func.sum(Thread.total_cost_usd), 0.0),
                func.coalesce(func.sum(Thread.total_tokens), 0),
            ).where(Thread.dialog_id == dialog_id)
        )
        cost, tokens = row.one()
        return {"ai_cost_usd": float(cost or 0), "ai_tokens": int(tokens or 0)}
    except Exception:
        return {"ai_cost_usd": 0.0, "ai_tokens": 0}


async def dialog_ledger_totals(db: AsyncSession, dialog_id: int) -> dict[str, float]:
    rows = (
        await db.execute(select(LedgerEntry).where(LedgerEntry.dialog_id == dialog_id))
    ).scalars().all()
    income = 0.0
    expense = 0.0
    for e in rows:
        if e.entry_type == "income":
            income += float(e.amount_usd or 0)
        elif e.entry_type in ("expense", "refund"):
            expense += float(e.amount_usd or 0)
    return {"income_usd": income, "expense_usd": expense}


async def dialog_finance(db: AsyncSession, dialog_id: int) -> dict[str, Any]:
    ai = await dialog_ai_cost(db, dialog_id)
    led = await dialog_ledger_totals(db, dialog_id)
    # AI tokens count as expense for profit
    total_expense = led["expense_usd"] + float(ai["ai_cost_usd"])
    income = led["income_usd"]
    return {
        **ai,
        "income_usd": income,
        "manual_expense_usd": led["expense_usd"],
        "expense_usd": total_expense,
        "profit_usd": income - total_expense,
    }


async def last_followup_at(db: AsyncSession, dialog_id: int) -> Optional[str]:
    row = await db.execute(
        select(Message.created_at)
        .where(Message.dialog_id == dialog_id, Message.agent_name == "followup")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    dt = row.scalar_one_or_none()
    return _iso(dt)


async def list_dialog_orders(db: AsyncSession, dialog_id: int) -> list[Order]:
    result = await db.execute(
        select(Order).where(Order.dialog_id == dialog_id).order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def list_dialog_ledger(db: AsyncSession, dialog_id: int, limit: int = 100) -> list[LedgerEntry]:
    result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.dialog_id == dialog_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def serialize_order(o: Order) -> dict[str, Any]:
    return {
        "id": o.id,
        "dialog_id": o.dialog_id,
        "amount_usdt": o.amount_usdt,
        "description": o.description,
        "payment_method": o.payment_method.value if hasattr(o.payment_method, "value") else o.payment_method,
        "payment_status": o.payment_status.value if hasattr(o.payment_status, "value") else o.payment_status,
        "wallet_address": o.wallet_address,
        "tx_hash": o.tx_hash,
        "escrow_url": o.escrow_url,
        "created_at": _iso(o.created_at),
        "paid_at": _iso(o.paid_at),
    }


def serialize_ledger(e: LedgerEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "dialog_id": e.dialog_id,
        "order_id": e.order_id,
        "type": e.entry_type,
        "amount_usd": e.amount_usd,
        "currency": e.currency,
        "network": e.network,
        "tx_hash": e.tx_hash,
        "description": e.description,
        "created_at": _iso(e.created_at),
    }


def serialize_message(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role.value if hasattr(m.role, "value") else m.role,
        "content": m.content,
        "agent_name": m.agent_name,
        "created_at": _iso(m.created_at),
    }
