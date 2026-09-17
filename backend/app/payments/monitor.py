"""Unified payment order monitoring for all configured networks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Order, PaymentMethod, PaymentStatus
from app.payments.multichain import check_incoming
from app.payments.tron import _get_sync_session, _notify_payment_received

logger = logging.getLogger(__name__)


def _network_for_order(order: Order) -> str:
    notes = order.escrow_draft_notes or ""
    if notes.startswith("network:"):
        return notes.split("|")[0].replace("network:", "").strip()
    return "usdt-tron"


async def monitor_pending_orders() -> int:
    db = _get_sync_session()
    confirmed = 0
    try:
        orders = db.execute(
            select(Order).where(
                Order.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.CONFIRMING]),
            )
        ).scalars().all()

        for order in orders:
            if not order.wallet_address:
                continue
            network = _network_for_order(order)
            since = order.created_at
            if since and since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)

            result = await check_incoming(
                network,
                order.wallet_address,
                order.amount_usdt,
                since=since,
            )
            prev = order.payment_status

            if result.get("status") == "confirmed":
                order.payment_status = PaymentStatus.CONFIRMED
                order.tx_hash = result.get("tx_hash")
                order.paid_at = datetime.now(timezone.utc)
                db.commit()
                if prev != PaymentStatus.CONFIRMED:
                    confirmed += 1
                    await _notify_payment_received(order.dialog_id, order.id)
            elif result.get("status") == "error":
                logger.debug("order %s check: %s", order.id, result.get("error"))
        return confirmed
    finally:
        db.close()


async def create_payment_order_for_network(
    dialog_id: int,
    amount: float,
    description: str,
    network_key: str = "usdt-tron",
) -> dict:
    """Create order using wallet address from payment_templates."""
    from app.database import async_session
    from app.db.bot_extensions import PaymentTemplate
    from app.payments.tron import generate_qr

    async with async_session() as adb:
        tpl = (
            await adb.execute(
                select(PaymentTemplate).where(
                    PaymentTemplate.network_key == network_key,
                    PaymentTemplate.enabled.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not tpl or not tpl.wallet_address:
            raise ValueError(f"No wallet configured for {network_key}")

        address = tpl.wallet_address
        if amount <= 0:
            raise ValueError("Сумма оплаты не указана")
        amount = float(amount)

    db = _get_sync_session()
    try:
        order = Order(
            dialog_id=dialog_id,
            amount_usdt=amount,
            description=description,
            payment_method=PaymentMethod.DIRECT_USDT,
            payment_status=PaymentStatus.PENDING,
            wallet_address=address,
            qr_code_path=generate_qr(address, amount) if network_key == "usdt-tron" else None,
            expires_at=datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=24),
            escrow_draft_notes=f"network:{network_key}",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {
            "order_id": order.id,
            "wallet_address": address,
            "amount_usdt": amount,
            "network": network_key,
        }
    finally:
        db.close()
