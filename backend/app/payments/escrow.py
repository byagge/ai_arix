"""Escrow: prepare deal draft + notify admin. Never auto-create on escrow services."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Dialog, Order, PaymentMethod, PaymentStatus

settings = get_settings()


def _session() -> Session:
    engine = create_engine(settings.database_url_sync)
    return sessionmaker(bind=engine)()


async def prepare_escrow_draft(
    dialog_id: int,
    amount: float,
    description: str,
    client_summary: str = "",
) -> dict:
    """Create local draft and notify admin. Does NOT call escrow APIs."""
    draft_id = f"DRAFT-{uuid.uuid4().hex[:10].upper()}"
    notes = (
        f"Черновик гарант-сделки\n"
        f"ID: {draft_id}\n"
        f"Сумма: {amount} USDT\n"
        f"Описание: {description}\n"
        f"Контекст клиента: {client_summary}\n"
        f"Статус: ожидает создания админом\n"
        f"Время: {datetime.now(timezone.utc).isoformat()}"
    )

    db = _session()
    try:
        order = Order(
            dialog_id=dialog_id,
            amount_usdt=amount or 0.0,
            description=description,
            payment_method=PaymentMethod.ESCROW_DRAFT,
            payment_status=PaymentStatus.DRAFT,
            escrow_deal_id=draft_id,
            escrow_draft_notes=notes,
            admin_notified=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        dialog = db.get(Dialog, dialog_id)
        client_line = ""
        if dialog:
            client_line = (
                f"Клиент: {dialog.first_name or ''} "
                f"@{dialog.telegram_username or '—'} "
                f"(tg:{dialog.telegram_user_id})\n"
                f"Диалог #{dialog.id}"
            )

        notify_text = (
            "🔔 НОВЫЙ ЧЕРНОВИК ГАРАНТ-СДЕЛКИ\n\n"
            f"{client_line}\n"
            f"Draft ID: {draft_id}\n"
            f"Сумма: {amount} USDT\n"
            f"Описание: {description}\n\n"
            f"{client_summary}\n\n"
            "⚠️ Сделка НЕ создана автоматически.\n"
            "Создайте гарант-сделку вручную и отправьте ссылку клиенту "
            "или через админ-панель (Manual Override)."
        )

        notified = await _notify_admin(notify_text)
        order.admin_notified = notified
        db.commit()

        return {
            "order_id": order.id,
            "draft_id": draft_id,
            "amount_usdt": amount,
            "description": description,
            "status": "draft",
            "admin_notified": notified,
            "auto_created": False,
        }
    finally:
        db.close()


async def _notify_admin(text: str) -> bool:
    if not settings.telegram_admin_id or not settings.telegram_bot_token:
        return False
    try:
        from app.telegram.client import send_admin_notification

        await send_admin_notification(text)
        return True
    except Exception:
        return False


async def list_escrow_drafts() -> list[dict]:
    db = _session()
    try:
        rows = db.execute(
            select(Order).where(Order.payment_method == PaymentMethod.ESCROW_DRAFT).order_by(Order.created_at.desc())
        ).scalars().all()
        return [
            {
                "id": o.id,
                "dialog_id": o.dialog_id,
                "amount_usdt": o.amount_usdt,
                "description": o.description,
                "draft_id": o.escrow_deal_id,
                "notes": o.escrow_draft_notes,
                "admin_notified": o.admin_notified,
                "status": o.payment_status.value,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in rows
        ]
    finally:
        db.close()


# Kept for Celery compatibility — no-op for auto escrow
async def create_escrow_deal(dialog_id: int, amount: float, description: str) -> dict:
    return await prepare_escrow_draft(dialog_id, amount, description)


async def monitor_escrow_orders() -> int:
    return 0
