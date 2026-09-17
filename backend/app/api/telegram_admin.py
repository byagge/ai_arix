"""Telegram runtime status + panel controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.db.models import AgentSettings, BusinessConnection, Dialog, Message, MessageRole
from app.services.dialog_service import get_dialog_detail, get_or_create_settings, process_incoming_message, resolve_chat_id
from app.telegram.client import is_telegram_running, send_telegram_message

router = APIRouter(prefix="/telegram", tags=["telegram"])


class RuntimeSettingsPatch(BaseModel):
    reply_delay_min_sec: float | None = Field(None, ge=0, le=600)
    reply_delay_max_sec: float | None = Field(None, ge=0, le=600)
    force_business_reply: bool | None = None
    global_ai_enabled: bool | None = None
    max_followups: int | None = Field(None, ge=0, le=50)
    followup_delays: str | None = None
    tone: str | None = None


def _runtime_dict(s: AgentSettings, cfg) -> dict:
    return {
        "reply_delay_min_sec": getattr(s, "reply_delay_min_sec", None) or cfg.reply_delay_min_sec,
        "reply_delay_max_sec": getattr(s, "reply_delay_max_sec", None) or cfg.reply_delay_max_sec,
        "force_business_reply": bool(getattr(s, "force_business_reply", False)),
        "global_ai_enabled": bool(getattr(s, "global_ai_enabled", True)),
        "max_followups": s.max_followups,
        "followup_delays": s.followup_delays,
        "tone": s.tone,
    }


@router.get("/status")
async def telegram_status(db: AsyncSession = Depends(get_db)):
    cfg = get_settings()
    settings = await get_or_create_settings(db)
    rows = (await db.execute(select(BusinessConnection).order_by(BusinessConnection.id.desc()))).scalars().all()

    connections = []
    live_errors = []
    for row in rows:
        live = {
            "connection_id": row.connection_id,
            "owner_id": row.user_id,
            "user_chat_id": row.user_chat_id,
            "is_enabled": row.is_enabled,
            "can_reply": row.can_reply,
            "live_can_reply": None,
            "live_is_enabled": None,
            "block_reason": None,
        }
        if cfg.telegram_bot_token and is_telegram_running():
            try:
                from app.telegram.client import get_application

                bc = await get_application().bot.get_business_connection(row.connection_id)
                live["live_can_reply"] = bool(bc.can_reply)
                live["live_is_enabled"] = bool(bc.is_enabled)
                # keep DB in sync
                row.can_reply = bool(bc.can_reply)
                row.is_enabled = bool(bc.is_enabled)
                if not bc.is_enabled:
                    live["block_reason"] = "connection_disabled"
                elif not bc.can_reply:
                    live["block_reason"] = "can_reply_false"
            except Exception as e:
                live_errors.append(f"{row.connection_id}: {e}")
                live["block_reason"] = "fetch_failed"
        else:
            if not row.can_reply:
                live["block_reason"] = "can_reply_false"
        connections.append(live)

    await db.commit()

    blocked = any(c.get("block_reason") == "can_reply_false" for c in connections)
    return {
        "token_set": bool(cfg.telegram_bot_token),
        "admin_id": cfg.telegram_admin_id or None,
        "running": is_telegram_running(),
        "bot_username": None,
        "connections": connections,
        "blocked_by_can_reply": blocked,
        "live_errors": live_errors,
        "runtime": _runtime_dict(settings, cfg),
        "howto_fix_reply": (
            "Telegram → Настройки → Telegram Business → Чат-боты → ваш бот → "
            "включите «Отвечать на сообщения», сохраните. Затем Обновить в панели."
        ),
    }


@router.post("/refresh")
async def refresh_connections(db: AsyncSession = Depends(get_db)):
    return await telegram_status(db)


@router.get("/runtime")
async def get_runtime(db: AsyncSession = Depends(get_db)):
    cfg = get_settings()
    settings = await get_or_create_settings(db)
    return _runtime_dict(settings, cfg)


@router.patch("/runtime")
async def patch_runtime(body: RuntimeSettingsPatch, db: AsyncSession = Depends(get_db)):
    cfg = get_settings()
    settings = await get_or_create_settings(db)
    data = body.model_dump(exclude_unset=True)
    if "reply_delay_min_sec" in data and "reply_delay_max_sec" in data:
        if data["reply_delay_min_sec"] > data["reply_delay_max_sec"]:
            raise HTTPException(400, "min delay > max delay")
    for k, v in data.items():
        if hasattr(settings, k):
            setattr(settings, k, v)
    await db.flush()
    from app.services.runtime_config import refresh_from_db

    await refresh_from_db()
    return _runtime_dict(settings, cfg)


@router.post("/dialogs/{dialog_id}/ai-reply")
async def force_ai_reply(
    dialog_id: int,
    send: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Generate AI draft for last user message.

    By default does NOT save/send — panel opens a modal to edit.
    Pass ?send=true to generate+save+deliver (legacy).
    """
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")

    last_user = None
    for m in reversed(dialog.messages or []):
        if m.role == MessageRole.USER:
            last_user = m
            break
    if not last_user:
        raise HTTPException(400, "No user message to reply to")

    from app.services.dialog_service import generate_ai_draft_for_dialog, generate_ai_reply_for_dialog

    if not send:
        try:
            draft = await generate_ai_draft_for_dialog(db, dialog, last_user.content)
        except Exception as e:
            raise HTTPException(500, f"AI failed: {e}") from e
        if not draft:
            raise HTTPException(400, "AI returned empty draft")
        return {
            "ok": True,
            "draft": True,
            "reply": draft,
            "sent": False,
            "send_error": None,
            "hint": None,
            "user_message": last_user.content,
        }

    try:
        reply = await generate_ai_reply_for_dialog(db, dialog, last_user.content)
    except Exception as e:
        raise HTTPException(500, f"AI failed: {e}") from e

    if not reply:
        raise HTTPException(400, "AI returned empty reply (ai may be off / silent mode)")

    send_error = None
    try:
        await send_telegram_message(
            resolve_chat_id(dialog),
            reply,
            business_connection_id=dialog.business_connection_id,
        )
    except Exception as e:
        send_error = str(e)

    await db.commit()
    return {
        "ok": send_error is None,
        "draft": False,
        "reply": reply,
        "sent": send_error is None,
        "send_error": send_error,
        "hint": (
            None
            if send_error is None
            else "Telegram отклонил отправку. Обычно это can_reply=false."
        ),
    }


@router.post("/test-send")
async def test_send(db: AsyncSession = Depends(get_db)):
    """Send a short test to the latest business dialog (or admin DM)."""
    cfg = get_settings()
    if not is_telegram_running():
        raise HTTPException(400, "Telegram bot is not running — restart backend")

    dialog = (
        await db.execute(
            select(Dialog)
            .where(Dialog.is_business.is_(True))
            .order_by(Dialog.last_message_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()

    text = "Тест из панели Arix: если вы это видите — бот может отвечать."
    if dialog:
        try:
            await send_telegram_message(
                resolve_chat_id(dialog),
                text,
                business_connection_id=dialog.business_connection_id,
            )
            return {"ok": True, "target": f"dialog #{dialog.id}", "business": True}
        except Exception as e:
            return {
                "ok": False,
                "target": f"dialog #{dialog.id}",
                "business": True,
                "error": str(e),
                "hint": "Включите can_reply в Telegram Business → Чат-боты",
            }

    if cfg.telegram_admin_id:
        try:
            await send_telegram_message(cfg.telegram_admin_id, text)
            return {"ok": True, "target": "admin DM", "business": False}
        except Exception as e:
            raise HTTPException(502, f"Admin DM failed: {e}") from e

    raise HTTPException(400, "No business dialog and no TELEGRAM_ADMIN_ID")
