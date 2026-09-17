"""Bot admin API — clients, payments, templates, ledger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db.bot_extensions import LedgerEntry, PaymentTemplate
from app.db.models import Dialog, Message, Order, PaymentStatus
from app.services.dialog_finance import (
    dialog_finance,
    last_followup_at,
    list_dialog_ledger,
    list_dialog_orders,
    serialize_dialog_card,
    serialize_ledger,
    serialize_order,
)
from app.services.dialog_service import get_dialog_detail

router = APIRouter(prefix="/bot", tags=["bot-admin"])


class ClientOut(BaseModel):
    id: int
    telegram_user_id: int
    username: str | None
    first_name: str | None
    work_status: str
    funnel_stage: str
    ai_active: bool
    quoted_price_usd: float | None
    quoted_days: int | None
    followup_count: int
    last_message_at: str | None
    is_business: bool
    last_message_preview: str | None = None
    followup_mode: str | None = None
    next_followup_at: str | None = None
    telegram_link: str | None = None
    account_label: str | None = None

    model_config = {"from_attributes": True}


class TemplateOut(BaseModel):
    id: int
    network_key: str
    label: str
    wallet_address: str
    message_template: str
    enabled: bool


class TemplatePatch(BaseModel):
    wallet_address: str | None = None
    message_template: str | None = None
    enabled: bool | None = None
    label: str | None = None


class LedgerCreate(BaseModel):
    dialog_id: int
    type: str  # income | expense | refund
    amount_usd: float = Field(..., gt=0)
    currency: str = "USDT"
    network: str | None = None
    tx_hash: str | None = None
    description: str = ""


@router.get("/clients")
async def list_clients(limit: int = 100, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(Dialog).order_by(Dialog.last_message_at.desc().nullslast()).limit(limit))
    ).scalars().all()

    # last message previews in one query
    previews: dict[int, str] = {}
    if rows:
        ids = [d.id for d in rows]
        msgs = (
            await db.execute(
                select(Message.dialog_id, Message.content, Message.created_at)
                .where(Message.dialog_id.in_(ids))
                .order_by(Message.created_at.desc())
            )
        ).all()
        for dialog_id, content, _ in msgs:
            if dialog_id not in previews:
                previews[dialog_id] = (content or "")[:120]

    return [
        {
            **serialize_dialog_card(d, preview=previews.get(d.id)),
            "username": d.telegram_username,
        }
        for d in rows
    ]


@router.get("/clients/{dialog_id}")
async def get_client(dialog_id: int, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "not found")
    card = serialize_dialog_card(dialog, message_count=len(dialog.messages))
    return {
        **card,
        "username": dialog.telegram_username,
        "last_followup_at": await last_followup_at(db, dialog_id),
        "finance": await dialog_finance(db, dialog_id),
        "orders": [serialize_order(o) for o in await list_dialog_orders(db, dialog_id)],
        "ledger": [serialize_ledger(e) for e in await list_dialog_ledger(db, dialog_id)],
    }


@router.get("/stats")
async def bot_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Dialog.id))) or 0
    in_progress = await db.scalar(
        select(func.count(Dialog.id)).where(Dialog.work_status == "in_progress")
    ) or 0
    pending_pay = await db.scalar(
        select(func.count(Dialog.id)).where(Dialog.work_status == "payment_pending")
    ) or 0
    revenue = (
        await db.scalar(
            select(func.coalesce(func.sum(Order.amount_usdt), 0.0)).where(
                Order.payment_status == PaymentStatus.CONFIRMED
            )
        )
        or 0.0
    )
    income = (
        await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0.0)).where(
                LedgerEntry.entry_type == "income"
            )
        )
        or 0.0
    )
    expense = (
        await db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0.0)).where(
                LedgerEntry.entry_type.in_(["expense", "refund"])
            )
        )
        or 0.0
    )
    return {
        "dialogs": total,
        "in_progress": in_progress,
        "payment_pending": pending_pay,
        "revenue_usdt": float(revenue),
        "ledger_usd": float(income) - float(expense),
        "income_usd": float(income),
        "expense_usd": float(expense),
    }


@router.get("/payment-templates", response_model=list[TemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db)):
    from app.services.payment_templates import seed_templates

    await seed_templates()
    return (await db.execute(select(PaymentTemplate).order_by(PaymentTemplate.network_key))).scalars().all()


@router.patch("/payment-templates/{tpl_id}", response_model=TemplateOut)
async def patch_template(tpl_id: int, body: TemplatePatch, db: AsyncSession = Depends(get_db)):
    tpl = await db.get(PaymentTemplate, tpl_id)
    if not tpl:
        raise HTTPException(404, "not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(tpl, k, v)
    await db.flush()
    return tpl


@router.get("/ledger")
async def list_ledger(limit: int = 100, dialog_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(LedgerEntry).order_by(LedgerEntry.created_at.desc()).limit(limit)
    if dialog_id is not None:
        q = (
            select(LedgerEntry)
            .where(LedgerEntry.dialog_id == dialog_id)
            .order_by(LedgerEntry.created_at.desc())
            .limit(limit)
        )
    rows = (await db.execute(q)).scalars().all()
    return [serialize_ledger(e) for e in rows]


@router.post("/ledger")
async def create_ledger(body: LedgerCreate, db: AsyncSession = Depends(get_db)):
    if body.type not in ("income", "expense", "refund"):
        raise HTTPException(400, "type must be income|expense|refund")
    dialog = await db.get(Dialog, body.dialog_id)
    if not dialog:
        raise HTTPException(404, "dialog not found")
    entry = LedgerEntry(
        dialog_id=body.dialog_id,
        entry_type=body.type,
        amount_usd=float(body.amount_usd),
        currency=body.currency or "USDT",
        network=body.network,
        tx_hash=body.tx_hash,
        description=body.description or "",
    )
    db.add(entry)
    await db.flush()
    return serialize_ledger(entry)
