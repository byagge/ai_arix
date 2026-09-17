import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from celery_app import celery_app


@celery_app.task(name="celery_app.tasks.process_followups")
def process_followups():
    return asyncio.get_event_loop().run_until_complete(_process_followups())


@celery_app.task(name="celery_app.tasks.monitor_payments")
def monitor_payments():
    return asyncio.get_event_loop().run_until_complete(_monitor_payments())


async def _process_followups() -> dict:
    from app.database import async_session
    from app.db.models import AgentSettings, Dialog, Message, MessageRole
    from app.agents.followup import generate_followup_response
    from app.services.dialog_service import format_history, get_or_create_settings, log_event, schedule_next_followup
    from app.telegram.client import send_telegram_message

    now = datetime.now(timezone.utc)
    sent = 0

    async with async_session() as db:
        settings = await get_or_create_settings(db)
        result = await db.execute(
            select(Dialog).where(
                Dialog.ai_active.is_(True),
                Dialog.next_followup_at.isnot(None),
                Dialog.next_followup_at <= now,
                Dialog.followup_count < settings.max_followups,
            )
        )
        dialogs = result.scalars().all()

        for dialog in dialogs:
            msgs = await db.execute(
                select(Message).where(Message.dialog_id == dialog.id).order_by(Message.created_at.asc())
            )
            history = list(msgs.scalars().all())
            if not history:
                continue

            response = await generate_followup_response(
                conversation_history=format_history(history),
                settings={
                    "followup_prompt": settings.followup_prompt,
                    "max_followups": settings.max_followups,
                    "discount_max_percent": settings.discount_max_percent,
                },
                followup_number=dialog.followup_count + 1,
            )

            msg = Message(
                dialog_id=dialog.id,
                role=MessageRole.ASSISTANT,
                content=response,
                agent_name="followup",
            )
            db.add(msg)
            dialog.followup_count += 1
            dialog.last_message_at = now
            await schedule_next_followup(db, dialog, settings)
            await log_event(db, "followup_sent", "followup", dialog.id)

            try:
                await send_telegram_message(
                    dialog.telegram_user_id,
                    response,
                    business_connection_id=dialog.business_connection_id,
                )
                sent += 1
            except Exception:
                pass

        await db.commit()

    return {"sent": sent}


async def _monitor_payments() -> dict:
    from app.payments.tron import monitor_pending_orders
    from app.payments.escrow import monitor_escrow_orders

    tron = await monitor_pending_orders()
    escrow = await monitor_escrow_orders()
    return {"tron_confirmed": tron, "escrow_updated": escrow}
