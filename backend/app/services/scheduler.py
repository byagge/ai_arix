"""In-process scheduler: follow-ups, payment monitoring, payment reminders."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)
_tasks: list[asyncio.Task] = []


async def _followup_loop() -> None:
    while True:
        try:
            await _run_followups()
        except Exception as e:
            logger.exception("followup loop: %s", e)
        await asyncio.sleep(120)


async def _payments_loop() -> None:
    while True:
        try:
            from app.payments.monitor import monitor_pending_orders

            await monitor_pending_orders()
        except Exception as e:
            logger.exception("payments loop: %s", e)
        await asyncio.sleep(60)


async def _payment_reminder_loop() -> None:
    while True:
        try:
            await _run_payment_reminders()
        except Exception as e:
            logger.exception("payment reminder loop: %s", e)
        await asyncio.sleep(90)


async def _run_followups() -> None:
    from app.database import async_session
    from app.db.bot_extensions import FollowupMode, WorkStatus
    from app.db.models import Dialog, Message, MessageRole
    from app.services.dialog_service import get_or_create_settings, log_event, resolve_chat_id
    from app.services.followup_engine import next_followup_at, pick_followup_message, should_suppress_followup
    from app.telegram.client import send_telegram_message

    now = datetime.now(timezone.utc)
    async with async_session() as db:
        settings = await get_or_create_settings(db)
        delays = []
        for part in (settings.followup_delays or "2,24,72").split(","):
            part = part.strip()
            if part.isdigit():
                delays.append(int(part))
        if not delays:
            delays = [2, 24, 72]
        result = await db.execute(
            select(Dialog).where(
                Dialog.ai_active.is_(True),
                Dialog.next_followup_at.isnot(None),
                Dialog.next_followup_at <= now,
            )
        )
        for dialog in result.scalars().all():
            if should_suppress_followup(dialog):
                dialog.next_followup_at = None
                continue
            if dialog.followup_count >= settings.max_followups:
                dialog.next_followup_at = None
                continue

            response = pick_followup_message(dialog)
            db.add(
                Message(
                    dialog_id=dialog.id,
                    role=MessageRole.ASSISTANT,
                    content=response,
                    agent_name="followup",
                )
            )
            dialog.followup_count += 1
            dialog.last_message_at = now

            if dialog.followup_mode == FollowupMode.VACATION.value:
                dialog.next_followup_at = now + timedelta(days=7)
            else:
                dialog.next_followup_at = next_followup_at(now, dialog.followup_count, delays)

            await log_event(db, "followup_sent", "followup", dialog.id)
            try:
                await send_telegram_message(
                    resolve_chat_id(dialog),
                    response,
                    business_connection_id=dialog.business_connection_id,
                )
            except Exception:
                logger.exception("followup send failed dialog=%s", dialog.id)
        await db.commit()


async def _run_payment_reminders() -> None:
    from app.config import get_settings
    from app.database import async_session
    from app.db.bot_extensions import WorkStatus
    from app.db.models import Message, MessageRole, Order, PaymentStatus
    from app.services.followup_engine import PAYMENT_REMINDER
    from app.telegram.client import send_telegram_message

    cfg = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cfg.payment_reminder_minutes)
    async with async_session() as db:
        orders = (
            await db.execute(
                select(Order).where(
                    Order.payment_status == PaymentStatus.PENDING,
                    Order.created_at <= cutoff,
                )
            )
        ).scalars().all()
        for order in orders:
            meta = order.escrow_draft_notes or ""
            if "reminder_sent" in meta:
                continue
            from app.db.models import Dialog
            from app.services.dialog_service import resolve_chat_id

            dialog = await db.get(Dialog, order.dialog_id)
            if not dialog or dialog.work_status != WorkStatus.PAYMENT_PENDING.value:
                continue
            dmeta = dialog.metadata_json or {}
            if dmeta.get("payment_reminder_sent"):
                continue
            dmeta["payment_reminder_sent"] = True
            dialog.metadata_json = dmeta
            db.add(
                Message(
                    dialog_id=dialog.id,
                    role=MessageRole.ASSISTANT,
                    content=PAYMENT_REMINDER,
                    agent_name="payment_reminder",
                )
            )
            order.escrow_draft_notes = (meta or "") + "|reminder_sent"
            try:
                await send_telegram_message(
                    resolve_chat_id(dialog),
                    PAYMENT_REMINDER,
                    business_connection_id=dialog.business_connection_id,
                )
            except Exception:
                logger.exception("payment reminder send failed dialog=%s", dialog.id)
        await db.commit()


async def start_scheduler() -> None:
    from app.config import get_settings

    if not get_settings().use_inprocess_scheduler:
        return
    _tasks.append(asyncio.create_task(_followup_loop()))
    _tasks.append(asyncio.create_task(_payments_loop()))
    _tasks.append(asyncio.create_task(_payment_reminder_loop()))
    logger.info("In-process scheduler started (followups + payments + reminders)")


async def stop_scheduler() -> None:
    for t in _tasks:
        t.cancel()
    _tasks.clear()
