from datetime import datetime, timezone
from typing import Optional
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.graph import agent_graph
from app.agents.prompts import (
    DEFAULT_FOLLOWUP_PROMPT,
    DEFAULT_ORCHESTRATOR_PROMPT,
    DEFAULT_PAYMENT_PROMPT,
    DEFAULT_SALES_PROMPT,
)
from app.db.bot_extensions import FollowupMode, WorkStatus
from app.db.models import (
    AgentEvent,
    AgentSettings,
    Dialog,
    FunnelStage,
    Message,
    MessageRole,
)
from app.rag.retriever import retrieve_context
from app.services.event_bus import broadcast_agent_event
from app.services.followup_engine import schedule_followup_after_reply, should_suppress_followup
from app.services.humanizer import (
    expand_payment_placeholders,
    greeting_reply,
    humanize_reply,
    is_greeting_only,
    sticker_ack_reply,
    sticker_greeting_reply,
)
from app.services.message_intel import (
    MsgKind,
    classify_message,
    client_body,
    enrich_short_pointer_from_history,
    has_task_substance,
    ideal_tz_ack,
    quality_gate_reply,
)
from app.services.payment_templates import expand_placeholders_in_text
from app.services.quick_replies import (
    build_client_offer_message,
    build_escrow_admin_note,
    build_task_admin_note,
    capability_reply,
    deal_process_reply,
    is_capability_question,
    is_deal_process_question,
    is_escrow_pay_intent,
    is_price_request,
    is_ready_to_pay,
    match_escrow_guarantee_question,
)
from app.services.reply_outcome import ReplyOutcome
from app.services.sensitive_handler import VOICE_OK_REPLIES, is_voice_ok_question, match_sensitive


async def get_or_create_settings(db: AsyncSession) -> AgentSettings:
    result = await db.execute(select(AgentSettings).where(AgentSettings.id == 1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = AgentSettings(
            id=1,
            orchestrator_prompt=DEFAULT_ORCHESTRATOR_PROMPT,
            sales_prompt=DEFAULT_SALES_PROMPT,
            followup_prompt=DEFAULT_FOLLOWUP_PROMPT,
            payment_prompt=DEFAULT_PAYMENT_PROMPT,
            tone="human_coder",
        )
        db.add(settings)
        await db.flush()
        return settings

    # Refresh stale prompts when marker missing
    sales = settings.sales_prompt or ""
    outdated = "PROMPT_V10_DEAL_CONTEXT" not in sales
    if outdated:
        settings.orchestrator_prompt = DEFAULT_ORCHESTRATOR_PROMPT
        settings.sales_prompt = DEFAULT_SALES_PROMPT + "\n\n<!-- PROMPT_V10_DEAL_CONTEXT -->"
        settings.followup_prompt = DEFAULT_FOLLOWUP_PROMPT
        settings.payment_prompt = DEFAULT_PAYMENT_PROMPT
        settings.tone = "human_coder"
        await db.flush()
    return settings


def resolve_chat_id(dialog: Dialog) -> int:
    """Chat id for Telegram send (Business chats store real chat_id)."""
    return int(dialog.telegram_chat_id or dialog.telegram_user_id)


async def get_or_create_dialog(
    db: AsyncSession,
    telegram_user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    business_connection_id: Optional[str] = None,
    is_business: bool = False,
    telegram_chat_id: Optional[int] = None,
) -> Dialog:
    q = select(Dialog).where(Dialog.telegram_user_id == telegram_user_id)
    if business_connection_id:
        q = q.where(Dialog.business_connection_id == business_connection_id)
    else:
        q = q.where(Dialog.business_connection_id.is_(None))
    result = await db.execute(q)
    dialog = result.scalar_one_or_none()
    if not dialog:
        dialog = Dialog(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id or telegram_user_id,
            telegram_username=username,
            first_name=first_name,
            business_connection_id=business_connection_id,
            is_business=is_business,
            work_status=WorkStatus.LEAD.value,
        )
        db.add(dialog)
        await db.flush()
    else:
        if username:
            dialog.telegram_username = username
        if first_name:
            dialog.first_name = first_name
        if telegram_chat_id:
            dialog.telegram_chat_id = telegram_chat_id
        dialog.is_business = is_business or dialog.is_business
    return dialog


def format_history(messages: list[Message], limit: int = 40) -> str:
    lines = []
    for msg in messages[-limit:]:
        role_label = {
            "user": "Клиент",
            "assistant": "Менеджер",
            "operator": "Оператор",
        }.get(msg.role.value, msg.role.value)
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


async def log_event(
    db: AsyncSession,
    event_type: str,
    agent_name: str,
    dialog_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    event = AgentEvent(
        event_type=event_type,
        agent_name=agent_name,
        dialog_id=dialog_id,
        payload=payload or {},
    )
    db.add(event)
    await broadcast_agent_event(event_type, agent_name, {"dialog_id": dialog_id, **(payload or {})})


async def persist_incoming_now(
    *,
    telegram_user_id: int,
    content: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    telegram_message_id: Optional[int] = None,
    business_connection_id: Optional[str] = None,
    is_business: bool = False,
    media_type: str = "text",
    telegram_chat_id: Optional[int] = None,
) -> int:
    """Save user message immediately so the admin panel sees it before AI replies."""
    from app.database import async_session

    async with async_session() as db:
        dialog = await get_or_create_dialog(
            db,
            telegram_user_id,
            username,
            first_name,
            business_connection_id=business_connection_id,
            is_business=is_business,
            telegram_chat_id=telegram_chat_id,
        )
        if business_connection_id and not dialog.business_connection_id:
            dialog.business_connection_id = business_connection_id
            dialog.is_business = True

        if telegram_message_id is not None:
            exists = await db.scalar(
                select(Message.id).where(
                    Message.dialog_id == dialog.id,
                    Message.telegram_message_id == telegram_message_id,
                )
            )
            if exists:
                await db.commit()
                return dialog.id

        now = datetime.now(timezone.utc)
        db.add(
            Message(
                dialog_id=dialog.id,
                role=MessageRole.USER,
                content=content,
                telegram_message_id=telegram_message_id,
                media_type=media_type,
            )
        )
        dialog.last_message_at = now
        dialog.last_user_message_at = now
        dialog.next_followup_at = None
        dialog.followup_count = 0
        await db.flush()
        dialog_id = dialog.id
        await log_event(
            db,
            "message_received",
            "system",
            dialog_id,
            {
                "preview": (content or "")[:160],
                "media_type": media_type,
                "live": True,
            },
        )
        await db.commit()
        return dialog_id


async def process_incoming_message(
    db: AsyncSession,
    telegram_user_id: int,
    content: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    telegram_message_id: Optional[int] = None,
    business_connection_id: Optional[str] = None,
    is_business: bool = False,
    media_type: str = "text",
    telegram_chat_id: Optional[int] = None,
    ai_reply: bool = True,
    persist_user: bool = True,
) -> ReplyOutcome:
    dialog = await get_or_create_dialog(
        db,
        telegram_user_id,
        username,
        first_name,
        business_connection_id=business_connection_id,
        is_business=is_business,
        telegram_chat_id=telegram_chat_id,
    )
    if business_connection_id and not dialog.business_connection_id:
        dialog.business_connection_id = business_connection_id
        dialog.is_business = True

    now = datetime.now(timezone.utc)
    if persist_user:
        already = False
        if telegram_message_id is not None:
            already = bool(
                await db.scalar(
                    select(Message.id).where(
                        Message.dialog_id == dialog.id,
                        Message.telegram_message_id == telegram_message_id,
                    )
                )
            )
        if not already:
            db.add(
                Message(
                    dialog_id=dialog.id,
                    role=MessageRole.USER,
                    content=content,
                    telegram_message_id=telegram_message_id,
                    media_type=media_type,
                )
            )
            dialog.last_message_at = now
            dialog.last_user_message_at = now
            dialog.next_followup_at = None
            dialog.followup_count = 0
            await db.flush()

    if not ai_reply:
        await log_event(db, "message_received", "system", dialog.id, {"ai_reply": False})
        return ReplyOutcome.silent()

    if not dialog.ai_active:
        await log_event(db, "message_received", "system", dialog.id, {"manual_mode": True})
        return ReplyOutcome.silent()

    agent_settings = await get_or_create_settings(db)
    if not getattr(agent_settings, "global_ai_enabled", True):
        await log_event(db, "message_suppressed", "system", dialog.id, {"reason": "global_ai_off"})
        return ReplyOutcome.silent()

    # Silent after payment until admin marks completed
    if dialog.silent_until_completed or dialog.work_status in (
        WorkStatus.PAID.value,
        WorkStatus.IN_PROGRESS.value,
    ):
        await log_event(db, "message_suppressed", "system", dialog.id, {"reason": "silent_mode"})
        return ReplyOutcome.silent()

    # --- Rule-based fast paths (always reply, even while awaiting admin quote) ---
    if media_type == "sticker":
        prior = await db.scalar(
            select(func.count(Message.id)).where(
                Message.dialog_id == dialog.id,
                Message.role.in_([MessageRole.ASSISTANT, MessageRole.OPERATOR]),
            )
        )
        total = await db.scalar(
            select(func.count(Message.id)).where(Message.dialog_id == dialog.id)
        )
        # Early dialog → greeting; later → short ack (never silent)
        if (prior or 0) == 0 or (total or 0) <= 4:
            reply = sticker_greeting_reply()
        else:
            reply = sticker_ack_reply()
        await _save_assistant(db, dialog, reply, "rules", now)
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "rules", dialog.id, {"preview": reply[:120]})
        return ReplyOutcome.reply(reply)

    # Short greeting-only — never long TZ that starts with «Привет, …»
    kind = classify_message(content)
    if kind == MsgKind.GREETING or (
        is_greeting_only(client_body(content)) and kind not in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER)
    ):
        reply = greeting_reply()
        await _save_assistant(db, dialog, reply, "rules", now)
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "rules", dialog.id, {"preview": reply[:120]})
        return ReplyOutcome.reply(reply)

    if is_voice_ok_question(content):
        import random
        reply = random.choice(VOICE_OK_REPLIES)
        await _save_assistant(db, dialog, reply, "rules", now)
        await log_event(db, "agent_response", "rules", dialog.id, {"preview": reply[:120]})
        return ReplyOutcome.reply(reply)

    # Guarantee FAQ first — «можно через гаранта?» is NOT silent pay-intent
    escrow_quick = match_escrow_guarantee_question(content)
    if escrow_quick:
        await _save_assistant(db, dialog, escrow_quick, "rules", now)
        if "отправляйте" in escrow_quick.lower():
            from app.telegram.client import send_admin_notification

            await send_admin_notification(
                build_escrow_admin_note(
                    username=username,
                    user_id=telegram_user_id,
                    amount=dialog.quoted_price_usd,
                    tz_summary=dialog.tz_summary or content[:300],
                )
            )
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "rules", dialog.id, {"preview": escrow_quick[:120]})
        return ReplyOutcome.reply(escrow_quick)

    # Pay via guarantee (decision) → admin only, no client reply
    if is_escrow_pay_intent(content):
        from app.telegram.client import send_admin_notification

        await send_admin_notification(
            build_escrow_admin_note(
                username=username,
                user_id=telegram_user_id,
                amount=dialog.quoted_price_usd,
                tz_summary=dialog.tz_summary or dialog.admin_task_summary or content[:300],
            )
        )
        await log_event(db, "escrow_pay_wait", "system", dialog.id, {"silent": True})
        return ReplyOutcome.silent()

    # Sensitive templates must NOT swallow long TZ / task briefs
    if kind not in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER):
        sensitive = match_sensitive(content)
        if sensitive:
            reply = humanize_reply(sensitive, agent_settings.tone)
            await _save_assistant(db, dialog, reply, "sensitive", now)
            await schedule_followup_after_reply(db, dialog, user_message=content)
            await log_event(db, "agent_response", "sensitive", dialog.id, {"preview": reply[:120]})
            return ReplyOutcome.reply(reply)

    if is_capability_question(content) and kind not in (MsgKind.LONG_TZ, MsgKind.SHORT_POINTER):
        reply = capability_reply()
        await _save_assistant(db, dialog, reply, "rules", now)
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "capability", dialog.id, {"preview": reply[:120]})
        return ReplyOutcome.reply(reply)

    # Price approved by admin → client asks price → send full offer
    if (
        getattr(dialog, "price_approved", False)
        and dialog.quoted_price_usd
        and is_price_request(content)
    ):
        offer = await _build_offer_for_dialog(db, dialog)
        await _save_assistant(db, dialog, offer, "offer", now)
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "offer", dialog.id, {"preview": offer[:120]})
        return ReplyOutcome.reply(offer)

    # After quote (or even before): deal-process FAQ — never re-pitch / re-estimate
    if is_deal_process_question(content):
        has_quote = bool(
            getattr(dialog, "price_approved", False) or dialog.quoted_price_usd
        )
        reply = deal_process_reply(has_quote=has_quote)
        await _save_assistant(db, dialog, reply, "rules", now)
        await schedule_followup_after_reply(db, dialog, user_message=content)
        await log_event(db, "agent_response", "deal_faq", dialog.id, {"preview": reply[:120]})
        return ReplyOutcome.reply(reply)

    return await _run_llm_pipeline(
        db,
        dialog=dialog,
        content=content,
        agent_settings=agent_settings,
        media_type=media_type,
        is_business=is_business,
        now=now,
        username=username,
        telegram_user_id=telegram_user_id,
    )


async def generate_ai_draft_for_dialog(
    db: AsyncSession,
    dialog: Dialog,
    content: str,
) -> Optional[str]:
    """Generate reply text for panel modal — does NOT save to DB."""
    now = datetime.now(timezone.utc)
    agent_settings = await get_or_create_settings(db)
    if is_greeting_only(content):
        return greeting_reply()

    # Reuse pipeline but capture response without relying on side effects only —
    # temporarily save then we need a pure path. Call sales/LLM directly.
    result = await db.execute(
        select(Message).where(Message.dialog_id == dialog.id).order_by(Message.created_at.asc())
    )
    history = list(result.scalars().all())
    try:
        rag_context = await retrieve_context(content)
    except Exception:
        rag_context = ""

    try:
        state = await agent_graph.ainvoke(
            {
                "dialog_id": dialog.id,
                "user_message": content,
                "conversation_history": format_history(history),
                "funnel_stage": dialog.funnel_stage.value,
                "rag_context": rag_context,
                "agent_settings": {
                    "orchestrator_prompt": agent_settings.orchestrator_prompt,
                    "sales_prompt": agent_settings.sales_prompt,
                    "followup_prompt": agent_settings.followup_prompt,
                    "payment_prompt": agent_settings.payment_prompt,
                    "tone": agent_settings.tone,
                    "autonomy_level": agent_settings.autonomy_level,
                    "max_followups": agent_settings.max_followups,
                    "discount_max_percent": agent_settings.discount_max_percent,
                },
                "orchestrator_decision": {},
                "sales_response": "",
                "followup_response": "",
                "payment_response": "",
                "final_response": "",
                "active_agent": "",
                "should_respond": True,
                "metadata": {},
            }
        )
    except Exception as e:
        await log_event(db, "agent_error", "orchestrator", dialog.id, {"error": str(e)[:300]})
        # Prefer sales-style heuristic without escrow leak
        from app.services.llm import generate_text

        return await generate_text(
            f"История:\n{format_history(history)}\n\nКлиент: {content}\n\nОтвет менеджера:",
            system_instruction=agent_settings.sales_prompt or DEFAULT_SALES_PROMPT,
            temperature=0.7,
            prefer="gemini",
        )

    response = (state.get("final_response") or "").strip()
    if not response:
        response = (
            "готового нету, сделаем под задачу, "
            "напишите что именно нужно по источникам и поиску"
        )
    response = humanize_reply(response, agent_settings.tone)
    amount = dialog.quoted_price_usd or 0
    response = await expand_placeholders_in_text(response, amount=amount)
    # Roll back any accidental payment side-effects from graph? Orders are created in payment
    # agent with separate sessions — drafts may still be created. Acceptable for draft preview.
    _ = now
    return response


async def generate_ai_reply_for_dialog(
    db: AsyncSession,
    dialog: Dialog,
    content: str,
) -> Optional[str]:
    """Generate + save an assistant reply for an existing dialog (panel force-reply)."""
    now = datetime.now(timezone.utc)
    agent_settings = await get_or_create_settings(db)
    if is_greeting_only(content):
        reply = greeting_reply()
        await _save_assistant(db, dialog, reply, "rules", now)
        return reply
    outcome = await _run_llm_pipeline(
        db,
        dialog=dialog,
        content=content,
        agent_settings=agent_settings,
        media_type="text",
        is_business=bool(dialog.is_business),
        now=now,
        username=dialog.telegram_username,
        telegram_user_id=dialog.telegram_user_id,
    )
    return outcome.text if outcome.should_send() else None


async def _run_llm_pipeline(
    db: AsyncSession,
    *,
    dialog: Dialog,
    content: str,
    agent_settings: AgentSettings,
    media_type: str,
    is_business: bool,
    now: datetime,
    username: str | None = None,
    telegram_user_id: int | None = None,
) -> ReplyOutcome:
    from app.agents.orchestrator import analyze_dialog

    result = await db.execute(
        select(Message).where(Message.dialog_id == dialog.id).order_by(Message.created_at.asc())
    )
    history = list(result.scalars().all())

    # «тз вот» without reply-to → attach last long client TZ from history
    content = enrich_short_pointer_from_history(content, history)
    kind = classify_message(content)

    # Persist TZ early so fallbacks / suppress / admin see it even on silent paths
    body = client_body(content)
    if kind in (MsgKind.LONG_TZ, MsgKind.TASK) or len(body) > 80 or media_type in (
        "voice",
        "photo",
        "document",
    ):
        dialog.tz_summary = (content if kind != MsgKind.SHORT_POINTER else body)[:2000]
        if not dialog.tz_summary and body:
            dialog.tz_summary = body[:2000]
        if dialog.work_status == WorkStatus.LEAD.value:
            dialog.work_status = WorkStatus.QUOTING.value

    history_text = format_history(history)
    try:
        rag_context = await retrieve_context(content)
    except Exception:
        rag_context = ""

    await log_event(db, "agent_thinking", "orchestrator", dialog.id)

    orch = await analyze_dialog(
        user_message=content,
        conversation_history=history_text,
        funnel_stage=dialog.funnel_stage.value,
        settings={
            "orchestrator_prompt": agent_settings.orchestrator_prompt,
        },
    )
    orch["quoted_price_usd"] = dialog.quoted_price_usd
    orch["quoted_price_max_usd"] = getattr(dialog, "quoted_price_max_usd", None)
    orch["quoted_days"] = getattr(dialog, "quoted_days", None)
    orch["price_approved"] = bool(getattr(dialog, "price_approved", False))
    orch["client_offer_pitch"] = (getattr(dialog, "client_offer_pitch", None) or "")[:300] or orch.get(
        "client_offer_pitch"
    )
    orch["tz_summary"] = dialog.tz_summary or dialog.admin_task_summary or ""
    orch["username"] = username or dialog.telegram_username
    orch["telegram_user_id"] = telegram_user_id or dialog.telegram_user_id

    # Force sales + complete flags for clear long TZ / pointer with context
    # Never re-open "estimate" path once price was already given
    price_already = bool(getattr(dialog, "price_approved", False) or dialog.quoted_price_usd)
    if kind in (MsgKind.LONG_TZ, MsgKind.SHORT_POINTER, MsgKind.TASK) and has_task_substance(content) and not price_already:
        orch["target_agent"] = "sales"
        orch["is_side_question"] = False
        if kind == MsgKind.LONG_TZ and len(body) >= 120:
            orch["requirements_complete"] = True
            if not orch.get("admin_task_summary"):
                orch["admin_task_summary"] = body[:1500]
        elif kind in (MsgKind.TASK, MsgKind.SHORT_POINTER) and len(body) >= 28:
            orch["requirements_complete"] = True
            if not orch.get("admin_task_summary"):
                orch["admin_task_summary"] = body[:1500]

    # Deal/process FAQ must never look like a fresh TZ handoff
    if is_deal_process_question(content) or orch.get("is_side_question"):
        orch["requirements_complete"] = False
        if is_deal_process_question(content):
            orch["is_side_question"] = True
            orch["client_offer_pitch"] = None

    # Payment intent overrides "awaiting admin quote" silence
    pay_intent = is_ready_to_pay(content) or is_escrow_pay_intent(content)
    if pay_intent:
        orch["target_agent"] = "payment"
        orch["ready_for_payment"] = True
        orch["is_side_question"] = True

    # While waiting for admin quote: handle nudges even if orch marks side_question
    if dialog.awaiting_admin_quote and not pay_intent:
        await _refresh_admin_summary(
            db,
            dialog,
            orch,
            username=username,
            telegram_user_id=telegram_user_id or dialog.telegram_user_id,
            last_message=content,
            notify=True,
        )
        # Client nudges about price/timeline while we wait for admin
        if is_price_request(content):
            ack = "уже собираю оценку, скоро напишу по цене и срокам"
            await _save_assistant(db, dialog, ack, "awaiting_price", now)
            await log_event(db, "agent_response", "awaiting_price", dialog.id, {"preview": ack})
            await db.flush()
            return ReplyOutcome.reply(ack)
        # Client added more TZ / clarification while waiting for price
        if has_task_substance(content) or kind in (MsgKind.LONG_TZ, MsgKind.SHORT_POINTER, MsgKind.TASK):
            ack = "ок, докинул в задачу, учту"
            await _save_assistant(db, dialog, ack, "tz_update", now)
            await log_event(db, "agent_response", "tz_update", dialog.id, {"preview": ack})
            await db.flush()
            return ReplyOutcome.reply(ack)
        body = client_body(content)
        if len(body) >= 6:
            ack = "ок, учёл"
            await _save_assistant(db, dialog, ack, "tz_update", now)
            await log_event(db, "agent_response", "tz_update", dialog.id, {"preview": ack})
            await db.flush()
            return ReplyOutcome.reply(ack)
        await log_event(
            db,
            "message_suppressed",
            "system",
            dialog.id,
            {"reason": "awaiting_admin_task_update"},
        )
        return ReplyOutcome.silent()

    # Fresh TZ handoff → admin. NEVER after price already given, NEVER on FAQ/side questions.
    if should_tz_ack_handoff(
        price_already=price_already,
        requirements_complete=bool(orch.get("requirements_complete")),
        admin_task_summary=orch.get("admin_task_summary"),
        pay_intent=pay_intent,
        is_side_question=bool(orch.get("is_side_question")),
        kind=kind,
        content=content,
        awaiting_admin=bool(dialog.awaiting_admin_quote),
    ):
        # Never silently ignore TZ — always ack client, then hand off to admin
        ack = ideal_tz_ack(
            pointer=kind == MsgKind.SHORT_POINTER,
            content=content,
        )
        # Prefer client_offer_pitch style opener if orch gave a pitch
        pitch = (orch.get("client_offer_pitch") or "").strip()
        if pitch and not pitch.lower().startswith(("клиент", "тз собрано")):
            ack = f"{pitch.rstrip(' .,')}, цену скажу когда соберу оценку"

        await _activate_awaiting_admin(
            db,
            dialog,
            str(orch["admin_task_summary"]),
            username=username,
            telegram_user_id=telegram_user_id or dialog.telegram_user_id,
            last_message=content,
            estimated_price_usd=_as_float(orch.get("estimated_price_usd")),
            estimated_days=_as_int(orch.get("estimated_days")),
            client_offer_pitch=(orch.get("client_offer_pitch") or None),
        )
        await _save_assistant(db, dialog, ack, "tz_ack", now)
        await log_event(db, "agent_response", "tz_ack", dialog.id, {"preview": ack[:120]})
        await db.flush()
        return ReplyOutcome.reply(ack)

    # Keep admin summary warm even before full complete (if LLM gave one)
    if orch.get("admin_task_summary") and not dialog.awaiting_admin_quote and not pay_intent:
        await _refresh_admin_summary(
            db,
            dialog,
            orch,
            username=username,
            telegram_user_id=telegram_user_id or dialog.telegram_user_id,
            last_message=content,
            notify=False,
        )

    try:
        state = await agent_graph.ainvoke(
            {
                "dialog_id": dialog.id,
                "user_message": content,
                "conversation_history": history_text,
                "funnel_stage": dialog.funnel_stage.value,
                "rag_context": rag_context,
                "agent_settings": {
                    "orchestrator_prompt": agent_settings.orchestrator_prompt,
                    "sales_prompt": agent_settings.sales_prompt,
                    "followup_prompt": agent_settings.followup_prompt,
                    "payment_prompt": agent_settings.payment_prompt,
                    "tone": agent_settings.tone,
                    "autonomy_level": agent_settings.autonomy_level,
                    "max_followups": agent_settings.max_followups,
                    "discount_max_percent": agent_settings.discount_max_percent,
                },
                "orchestrator_decision": orch,
                "sales_response": "",
                "followup_response": "",
                "payment_response": "",
                "final_response": "",
                "active_agent": "",
                "should_respond": True,
                "metadata": {},
            }
        )
    except Exception as e:
        await log_event(
            db,
            "agent_error",
            "orchestrator",
            dialog.id,
            {"error": str(e)[:300]},
        )
        if pay_intent and (dialog.quoted_price_usd or getattr(dialog, "price_approved", False)):
            reply = "секунду, менеджер скинет реквизиты usdt вручную, либо можем через гаранта"
        else:
            reply = quality_gate_reply(
                "секунду, чуть подвисло, напишите ещё раз или уточните задачу",
                content=content,
                has_tz_on_file=bool((dialog.tz_summary or "").strip()),
                kind=kind,
                price_already=bool(getattr(dialog, "price_approved", False) or dialog.quoted_price_usd),
            )
        await _save_assistant(db, dialog, reply, "error", now)
        try:
            from app.telegram.client import send_admin_notification

            await send_admin_notification(f"Agent error dialog #{dialog.id}: {e}")
        except Exception:
            pass
        return ReplyOutcome.reply(reply)

    response = state.get("final_response", "")
    active_agent = state.get("active_agent", "sales")
    meta = state.get("metadata", {}) or {}
    payment_data = meta.get("payment_data") or {}
    orch = state.get("orchestrator_decision", {}) or {}

    if payment_data.get("silent") or payment_data.get("escrow_pay"):
        note = payment_data.get("admin_note")
        if note:
            try:
                from app.telegram.client import send_admin_notification

                await send_admin_notification(note)
            except Exception:
                pass
        await log_event(db, "escrow_pay_wait", "payment", dialog.id, {"silent": True})
        await db.flush()
        return ReplyOutcome.silent()

    if len(content) > 80 or media_type in ("voice", "photo", "document"):
        dialog.tz_summary = content[:2000]
        if dialog.work_status == WorkStatus.LEAD.value:
            dialog.work_status = WorkStatus.QUOTING.value

    if orch.get("extracted_amount"):
        try:
            dialog.quoted_price_usd = float(orch["extracted_amount"])
        except (TypeError, ValueError):
            pass
    if payment_data.get("amount_usdt"):
        try:
            dialog.quoted_price_usd = float(payment_data["amount_usdt"])
        except (TypeError, ValueError):
            pass

    new_stage = meta.get("new_funnel_stage")
    if payment_data.get("status") == "draft" or payment_data.get("draft_id"):
        new_stage = "escrow_draft"
    if new_stage:
        try:
            dialog.funnel_stage = FunnelStage(new_stage)
        except ValueError:
            pass

    if payment_data.get("wallet_address") or payment_data.get("order_id"):
        dialog.work_status = WorkStatus.PAYMENT_PENDING.value
        dialog.followup_mode = FollowupMode.NONE.value

    if payment_data.get("error"):
        if not response:
            response = (
                "По оплате чуть не хватает данных на нашей стороне. "
                "Менеджер уточнит реквизиты и напишет вам."
            )

    if not response:
        response = _empty_sales_fallback(dialog, history, content)

    # Don't humanize payment templates (HTML + address/amount)
    is_payment_tpl = active_agent == "payment" and (
        "<code>" in (response or "")
        or "{usdt-" in (response or "")
        or "TRC-20" in (response or "")
        or "txid" in (response or "").lower()
    )
    if not is_payment_tpl:
        allow_prices = bool(getattr(dialog, "price_approved", False) or dialog.quoted_price_usd)
        response = humanize_reply(
            response,
            agent_settings.tone,
            allow_prices=allow_prices,
        )
        has_tz = bool(
            (dialog.tz_summary or "").strip()
            or (dialog.admin_task_summary or "").strip()
            or kind in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER)
        )
        response = quality_gate_reply(
            response,
            content=content,
            has_tz_on_file=has_tz,
            kind=kind,
            price_already=allow_prices,
        )
    amount = dialog.quoted_price_usd or float(payment_data.get("amount_usdt") or 0)
    response = await expand_placeholders_in_text(response, amount=amount)

    await _save_assistant(db, dialog, response, active_agent, now)
    await schedule_followup_after_reply(
        db,
        dialog,
        user_message=content,
        delays_hours=_parse_delays(agent_settings.followup_delays),
    )
    await log_event(
        db,
        "agent_response",
        active_agent,
        dialog.id,
        {"preview": response[:120], "is_business": is_business},
    )
    try:
        from app.config import get_settings as _gs
        from app.services.inference import record_agent_run

        cfg = _gs()
        await record_agent_run(
            db,
            dialog_id=dialog.id,
            title=f"TG #{dialog.id} {active_agent}",
            provider=cfg.llm_primary,
            model_id=cfg.openai_model if cfg.llm_primary == "openai" else cfg.gemini_model,
            prompt=content,
            output=response,
            latency_ms=0,
            spans=[{"name": active_agent, "kind": "router"}],
        )
    except Exception:
        pass
    await db.flush()
    return ReplyOutcome.reply(response)


def _as_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def should_tz_ack_handoff(
    *,
    price_already: bool,
    requirements_complete: bool,
    admin_task_summary,
    pay_intent: bool,
    is_side_question: bool,
    kind: MsgKind,
    content: str,
    awaiting_admin: bool = False,
) -> bool:
    """True only for first handoff of a real TZ — never after quote / FAQ."""
    if pay_intent or price_already or is_side_question or awaiting_admin:
        return False
    if not requirements_complete or not admin_task_summary:
        return False
    if is_deal_process_question(content) or is_price_request(content):
        return False
    # Only on real TZ briefs — short «делаете ботов?» must NOT hand off
    if kind == MsgKind.LONG_TZ:
        return True
    if kind == MsgKind.SHORT_POINTER:
        return True
    if kind == MsgKind.TASK and len(client_body(content)) >= 28 and has_task_substance(content):
        return True
    return has_task_substance(content) and len(client_body(content)) >= 80


def _empty_sales_fallback(
    dialog: Dialog,
    history: list[Message],
    content: str,
) -> str:
    """Fallback when LLM returns empty — acknowledge TZ if already in context."""
    kind = classify_message(content)
    price_already = bool(getattr(dialog, "price_approved", False) or dialog.quoted_price_usd)
    has_tz = bool(
        (dialog.tz_summary or "").strip()
        or (dialog.admin_task_summary or "").strip()
        or kind in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER)
    )
    if not has_tz:
        for msg in history:
            if msg.role == MessageRole.USER and len(client_body(msg.content or "")) > 80:
                has_tz = True
                break
    if price_already:
        return deal_process_reply(has_quote=True)
    if has_tz:
        return ideal_tz_ack(
            pointer=kind == MsgKind.SHORT_POINTER,
            content=content or (dialog.tz_summary or ""),
        )
    return "напишите что нужно - сделаем под задачу"


def _as_int(v) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


async def _refresh_admin_summary(
    db: AsyncSession,
    dialog: Dialog,
    orch: dict,
    *,
    username: str | None,
    telegram_user_id: int,
    last_message: str,
    notify: bool,
) -> None:
    summary = (orch.get("admin_task_summary") or "").strip()
    if not summary:
        snippet = (last_message or "").strip()[:500]
        if snippet:
            base = (dialog.admin_task_summary or dialog.tz_summary or "").strip()
            summary = f"{base}\n{snippet}".strip() if base and snippet not in base else (base or snippet)
    if not summary:
        return

    dialog.admin_task_summary = summary[:2000]
    dialog.tz_summary = summary[:2000]
    pitch = (orch.get("client_offer_pitch") or "").strip()
    if pitch:
        dialog.client_offer_pitch = pitch[:1000]
    est = _as_float(orch.get("estimated_price_usd"))
    days = _as_int(orch.get("estimated_days"))
    if est is not None:
        dialog.estimated_price_usd = est
    if days is not None and not dialog.quoted_days:
        dialog.quoted_days = days
    if dialog.work_status == WorkStatus.LEAD.value:
        dialog.work_status = WorkStatus.QUOTING.value

    await log_event(
        db,
        "admin_summary_updated",
        "orchestrator",
        dialog.id,
        {"summary": summary[:300], "estimated_price_usd": est, "pitch": (pitch or "")[:160]},
    )
    if notify:
        try:
            from app.telegram.client import send_admin_notification

            await send_admin_notification(
                build_task_admin_note(
                    dialog_id=dialog.id,
                    username=username or dialog.telegram_username,
                    user_id=telegram_user_id,
                    admin_task_summary=summary,
                    last_message=last_message,
                    estimated_price_usd=est or dialog.estimated_price_usd,
                    estimated_days=days or dialog.quoted_days,
                )
            )
        except Exception:
            pass
    await db.flush()


async def _activate_awaiting_admin(
    db: AsyncSession,
    dialog: Dialog,
    summary: str,
    *,
    username: str | None,
    telegram_user_id: int,
    last_message: str,
    estimated_price_usd: float | None = None,
    estimated_days: int | None = None,
    client_offer_pitch: str | None = None,
) -> None:
    summary = (summary or last_message or "").strip()[:2000]
    dialog.awaiting_admin_quote = True
    dialog.work_status = WorkStatus.AWAITING_ADMIN.value
    dialog.admin_task_summary = summary
    dialog.tz_summary = summary
    if client_offer_pitch:
        dialog.client_offer_pitch = client_offer_pitch.strip()[:1000]
    dialog.followup_mode = FollowupMode.NONE.value
    dialog.next_followup_at = None
    if estimated_price_usd is not None:
        dialog.estimated_price_usd = estimated_price_usd
    if estimated_days is not None:
        dialog.quoted_days = estimated_days
    await log_event(
        db,
        "requirements_complete",
        "orchestrator",
        dialog.id,
        {
            "summary": summary[:300],
            "estimated_price_usd": estimated_price_usd,
            "estimated_days": estimated_days,
        },
    )
    try:
        from app.telegram.client import send_admin_notification

        await send_admin_notification(
            build_task_admin_note(
                dialog_id=dialog.id,
                username=username or dialog.telegram_username,
                user_id=telegram_user_id,
                admin_task_summary=summary,
                last_message=last_message,
                estimated_price_usd=estimated_price_usd,
                estimated_days=estimated_days,
            )
        )
    except Exception:
        pass
    await db.flush()


async def _ensure_client_pitch(db: AsyncSession, dialog: Dialog) -> str:
    pitch = (getattr(dialog, "client_offer_pitch", None) or "").strip()
    if pitch and not re.search(r"(?i)клиент\s+запрос|тз\s+собрано|нужна\s+точн", pitch):
        return pitch

    from app.services.llm import generate_text

    src = (dialog.admin_task_summary or dialog.tz_summary or "").strip()[:800]
    try:
        pitch = await generate_text(
            f"Сделай одно предложение-описание продукта для клиента по этому ТЗ.\n"
            f"Начни с «делаем …». Без цен, без слов клиент/тз/нужна модель, без админ-заметок.\n"
            f"ТЗ:\n{src}",
            system_instruction=(
                "Ты менеджер продаж. Пиши коротко как в telegram, нижний регистр, "
                "без длинного тире и без слешей."
            ),
            temperature=0.4,
            prefer="gemini",
        )
        pitch = (pitch or "").strip().strip('"')
    except Exception:
        pitch = ""
    if not pitch:
        pitch = "делаем софт под вашу задачу с настройкой и запуском под ключ"
    dialog.client_offer_pitch = pitch[:1000]
    await db.flush()
    return dialog.client_offer_pitch


async def _build_offer_for_dialog(db: AsyncSession, dialog: Dialog) -> str:
    pitch = await _ensure_client_pitch(db, dialog)
    return build_client_offer_message(
        pitch=pitch,
        price_usd=dialog.quoted_price_usd,
        price_max_usd=getattr(dialog, "quoted_price_max_usd", None),
        days=dialog.quoted_days,
    )


async def send_approved_offer(
    db: AsyncSession,
    dialog: Dialog,
) -> str:
    """Build + save + return offer text for Telegram send (admin button / auto)."""
    if not dialog.quoted_price_usd:
        raise ValueError("quoted_price_usd is required")
    offer = await _build_offer_for_dialog(db, dialog)
    now = datetime.now(timezone.utc)
    dialog.price_approved = True
    dialog.awaiting_admin_quote = False
    if dialog.work_status == WorkStatus.AWAITING_ADMIN.value:
        dialog.work_status = WorkStatus.QUOTING.value
    await _save_assistant(db, dialog, offer, "offer", now)
    await db.flush()
    return offer


def _parse_delays(raw: str | None) -> list[int]:
    if not raw:
        from app.config import get_settings

        return get_settings().followup_delays_list
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out or [2, 24, 72]


async def _save_assistant(
    db: AsyncSession,
    dialog: Dialog,
    response: str,
    agent_name: str,
    now: datetime,
) -> None:
    db.add(
        Message(
            dialog_id=dialog.id,
            role=MessageRole.ASSISTANT,
            content=response,
            agent_name=agent_name,
        )
    )
    dialog.last_message_at = now


async def on_payment_confirmed(db: AsyncSession, dialog_id: int) -> None:
    dialog = await db.get(Dialog, dialog_id)
    if not dialog:
        return
    dialog.work_status = WorkStatus.IN_PROGRESS.value
    dialog.funnel_stage = FunnelStage.PAID
    dialog.silent_until_completed = True
    dialog.followup_mode = FollowupMode.NONE.value
    dialog.next_followup_at = None
    from app.db.bot_extensions import LedgerEntry

    db.add(
        LedgerEntry(
            dialog_id=dialog_id,
            entry_type="income",
            amount_usd=dialog.quoted_price_usd or 0,
            description="Оплата подтверждена",
        )
    )


async def get_dialogs(db: AsyncSession, limit: int = 50, offset: int = 0) -> list[dict]:
    subq = (
        select(Message.dialog_id, func.count(Message.id).label("cnt"))
        .group_by(Message.dialog_id)
        .subquery()
    )
    result = await db.execute(
        select(Dialog, subq.c.cnt)
        .outerjoin(subq, Dialog.id == subq.c.dialog_id)
        .order_by(Dialog.last_message_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    dialogs = []
    for dialog, cnt in result.all():
        last_msg = await db.execute(
            select(Message)
            .where(Message.dialog_id == dialog.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last = last_msg.scalar_one_or_none()
        dialogs.append(
            {
                "dialog": dialog,
                "message_count": cnt or 0,
                "last_message_preview": last.content[:80] if last else None,
            }
        )
    return dialogs


async def get_dialog_detail(db: AsyncSession, dialog_id: int) -> Optional[Dialog]:
    result = await db.execute(
        select(Dialog).options(selectinload(Dialog.messages)).where(Dialog.id == dialog_id)
    )
    return result.scalar_one_or_none()
