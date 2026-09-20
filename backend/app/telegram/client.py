"""Telegram Bot API: Business Bot + human delivery queue."""
from __future__ import annotations

import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    BusinessConnectionHandler,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.config import get_settings
from app.database import async_session
from app.db.models import BusinessConnection
from app.services.media_processor import process_incoming_media
from app.services.reply_queue import QueuedMessage, reply_queue
from app.services.dialog_service import process_incoming_message
from app.telegram.admin_menu import on_admin_callback, send_admin_home
from sqlalchemy import select

logger = logging.getLogger(__name__)

_app: Optional[Application] = None
_bot_running = False
_handlers_registered = False


def _settings():
    return get_settings()


def is_telegram_running() -> bool:
    return _bot_running


def get_application() -> Application:
    global _app
    s = _settings()
    if _app is None:
        if not s.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
        _app = (
            Application.builder()
            .token(s.telegram_bot_token)
            .concurrent_updates(s.max_concurrent_dialogs)
            .build()
        )
    return _app


async def send_admin_notification(text: str) -> None:
    s = _settings()
    if not s.telegram_admin_id:
        return
    app = get_application()
    await app.bot.send_message(chat_id=s.telegram_admin_id, text=text)


async def send_telegram_message(
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
) -> None:
    from app.telegram.delivery import deliver_reply

    app = get_application()
    await deliver_reply(app.bot, chat_id, text, business_connection_id=business_connection_id)


async def _upsert_business_connection(bc) -> BusinessConnection | None:
    """Persist / refresh a BusinessConnection from Telegram object or API."""
    if not bc:
        return None
    async with async_session() as db:
        result = await db.execute(
            select(BusinessConnection).where(BusinessConnection.connection_id == bc.id)
        )
        row = result.scalar_one_or_none()
        can_reply = bool(getattr(bc, "can_reply", True))
        rights = getattr(bc, "rights", None)
        can_read = True
        if rights is not None:
            can_read = bool(getattr(rights, "can_read_messages", False))
            # Newer API: can_reply may live only under rights
            if hasattr(rights, "can_reply"):
                can_reply = bool(rights.can_reply)
        payload = {
            "user": {
                "id": bc.user.id,
                "username": bc.user.username,
                "first_name": bc.user.first_name,
            },
            "is_enabled": bc.is_enabled,
            "can_reply": can_reply,
            "can_read_messages": can_read,
            "user_chat_id": getattr(bc, "user_chat_id", None),
        }
        if not can_read:
            logger.warning(
                "Business connection %s: can_read_messages=False — "
                "client will not see blue double-check. Enable «Read messages» "
                "in Telegram → Settings → Business → Chatbots",
                bc.id,
            )
        if row:
            row.is_enabled = bc.is_enabled
            row.can_reply = can_reply
            row.user_id = bc.user.id
            row.user_chat_id = getattr(bc, "user_chat_id", None)
            row.raw = payload
        else:
            row = BusinessConnection(
                connection_id=bc.id,
                user_id=bc.user.id,
                user_chat_id=getattr(bc, "user_chat_id", None),
                is_enabled=bc.is_enabled,
                can_reply=can_reply,
                raw=payload,
            )
            db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def _ensure_business_connection(bc_id: str) -> BusinessConnection | None:
    """Always refresh from Telegram so can_reply/is_enabled stay current."""
    try:
        app = get_application()
        bc = await app.bot.get_business_connection(bc_id)
        return await _upsert_business_connection(bc)
    except Exception as e:
        logger.warning("get_business_connection(%s): %s — fallback to DB", bc_id, e)
        async with async_session() as db:
            return (
                await db.execute(
                    select(BusinessConnection).where(BusinessConnection.connection_id == bc_id)
                )
            ).scalar_one_or_none()


async def _warn_no_reply_rights(bc_id: str, row: BusinessConnection) -> None:
    text = (
        "⚠️ Business Bot НЕ МОЖЕТ отвечать (can_reply=false).\n\n"
        "Откройте Telegram → Настройки → Telegram Business → Чат-боты → "
        "ваш бот → включите право «Отвечать на сообщения» / Reply to messages, "
        "затем переподключите бота.\n\n"
        f"connection: {bc_id}\n"
        f"owner_id: {row.user_id}"
    )
    logger.error(text.replace("\n", " | "))
    print("ERROR: Business bot can_reply=False — enable Reply permission in Telegram Business settings")
    try:
        await send_admin_notification(text)
    except Exception:
        pass


async def _process_batch(messages: list[QueuedMessage]) -> str | None:
    m = messages[-1]
    # Prefer last user burst text; earlier msgs already saved live in DB
    content = m.content
    if len(messages) > 1:
        content = "\n".join(x.content for x in messages if x.content).strip() or m.content

    if getattr(m, "save_only", False):
        # Already persisted on enqueue
        return None

    from app.services.reply_outcome import ReplyOutcome

    async with async_session() as db:
        outcome = await process_incoming_message(
            db,
            telegram_user_id=m.user_id,
            content=content,
            username=m.username,
            first_name=m.first_name,
            telegram_message_id=m.message_id,
            business_connection_id=m.business_connection_id,
            is_business=m.is_business,
            media_type=m.media_type,
            telegram_chat_id=m.chat_id,
            persist_user=False,
        )
        await db.commit()
    if isinstance(outcome, ReplyOutcome):
        return outcome
    return ReplyOutcome.reply(outcome) if outcome else ReplyOutcome.silent()


async def _enqueue_message(
    message,
    user,
    *,
    is_business: bool,
    content: str,
    media_type: str = "text",
    save_only: bool = False,
    use_reply: bool = False,
) -> None:
    if not message or not user:
        return
    bc_id = getattr(message, "business_connection_id", None)

    # Persist immediately so admin chat updates before AI delay/reply
    try:
        from app.services.dialog_service import persist_incoming_now

        await persist_incoming_now(
            telegram_user_id=user.id,
            content=content,
            username=user.username,
            first_name=user.first_name,
            telegram_message_id=message.message_id,
            business_connection_id=bc_id,
            is_business=is_business,
            media_type=media_type,
            telegram_chat_id=message.chat_id,
        )
    except Exception as e:
        logger.exception("live persist failed: %s", e)

    qm = QueuedMessage(
        chat_id=message.chat_id,
        user_id=user.id,
        content=content,
        username=user.username,
        first_name=user.first_name,
        message_id=message.message_id,
        business_connection_id=bc_id,
        is_business=is_business,
        media_type=media_type,
        save_only=save_only,
        use_reply=use_reply,
    )
    logger.info(
        "enqueue tg user=%s chat=%s biz=%s save_only=%s reply=%s text=%r",
        user.id,
        message.chat_id,
        bool(bc_id),
        save_only,
        use_reply,
        (content or "")[:80],
    )
    await reply_queue.enqueue(qm, _process_batch)


def _extract_reply_to_text(message) -> str | None:
    """Text/caption (or sticker label) of the message the client replied to."""
    reply = getattr(message, "reply_to_message", None)
    if not reply:
        return None
    quoted = (reply.text or reply.caption or "").strip()
    if quoted:
        return quoted[:4000]
    if getattr(reply, "sticker", None):
        emoji = getattr(reply.sticker, "emoji", None) or ""
        return f"[стикер] {emoji}".strip() or "[стикер]"
    if getattr(reply, "photo", None):
        return "[фото]" + (f" {reply.caption}" if reply.caption else "")
    if getattr(reply, "document", None):
        name = getattr(reply.document, "file_name", None) or "файл"
        return f"[документ {name}]"
    if getattr(reply, "voice", None) or getattr(reply, "audio", None):
        return "[голосовое]"
    return None


def _enrich_content_with_reply(content: str, message) -> tuple[str, bool]:
    """
    If client replied to a prior message, prepend quoted context for LLM/history.
    Returns (enriched_content, use_reply_flag).
    """
    quoted = _extract_reply_to_text(message)
    if not quoted:
        return content, False
    body = (content or "").strip()
    enriched = (
        f"[клиент отвечает на сообщение]:\n{quoted}\n\n"
        f"[его ответ]:\n{body}"
    )
    return enriched, True


async def _handle_incoming(
    message,
    user,
    *,
    is_business: bool,
    save_only: bool = False,
) -> None:
    if not message or not user:
        return

    app = get_application()
    content = message.text or message.caption or ""
    media_type = "text"

    if message.sticker or message.voice or message.audio or message.photo or message.document or message.video_note:
        content, media_type = await process_incoming_media(app.bot, message)
        if not content.strip():
            content = message.caption or "[медиа]"

    if not content.strip():
        logger.info("skip empty message chat=%s", getattr(message, "chat_id", None))
        return

    # Keep reply-quote context for LLM + DB history (short «тз вот» etc.)
    content, use_reply = _enrich_content_with_reply(content, message)

    await _enqueue_message(
        message,
        user,
        is_business=is_business,
        content=content,
        media_type=media_type,
        save_only=save_only,
        use_reply=use_reply,
    )


async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.business_message:
        return
    msg = update.effective_message
    user = update.effective_user
    if msg and getattr(msg, "business_connection_id", None):
        return
    logger.info("private message from %s", user.id if user else None)
    await _handle_incoming(msg, user, is_business=False)


async def on_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.business_message or update.edited_business_message
    user = msg.from_user if msg else None
    if not msg or not user:
        logger.warning("business update without message/user")
        return

    bc_id = getattr(msg, "business_connection_id", None)
    logger.info(
        "business_message from=%s chat=%s bc=%s text=%r",
        user.id,
        msg.chat_id,
        bc_id,
        (msg.text or msg.caption or "")[:80],
    )

    save_only = False
    if bc_id:
        row = await _ensure_business_connection(bc_id)
        force = False
        try:
            from app.services.runtime_config import get_force_business_reply

            force = get_force_business_reply()
        except Exception:
            pass
        if not force:
            try:
                async with async_session() as db:
                    from app.services.dialog_service import get_or_create_settings

                    st = await get_or_create_settings(db)
                    force = bool(getattr(st, "force_business_reply", False))
            except Exception:
                pass

        if row:
            if not row.is_enabled:
                logger.warning("Business connection %s disabled — save only", bc_id)
                save_only = True
            elif not row.can_reply and not force:
                logger.warning("Business connection %s can_reply=False — save only", bc_id)
                await _warn_no_reply_rights(bc_id, row)
                save_only = True
            elif not row.can_reply and force:
                logger.warning(
                    "can_reply=False but force_business_reply=ON — trying AI reply anyway"
                )
            elif row.user_id and user.id == row.user_id:
                logger.info("Owner message on %s — save only (AI replies to clients)", bc_id)
                save_only = True
        else:
            logger.warning("No BusinessConnection for %s — still trying to reply", bc_id)

    await _handle_incoming(msg, user, is_business=True, save_only=save_only)


async def on_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = _settings()
    user = update.effective_user
    if not user or not s.telegram_admin_id or user.id != s.telegram_admin_id:
        if update.effective_message:
            await update.effective_message.reply_text("Нет доступа.")
        return
    await send_admin_home(update, context)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = _settings()
    user = update.effective_user
    if not user:
        return
    if s.telegram_admin_id and user.id == s.telegram_admin_id:
        await send_admin_home(update, context)
        return
    msg = update.effective_message
    if msg:
        await _enqueue_message(
            msg,
            user,
            is_business=False,
            content="Привет",
            media_type="text",
        )


async def on_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bc = update.business_connection
    if not bc:
        return
    await _upsert_business_connection(bc)
    status = "подключён" if bc.is_enabled else "отключён"
    rights = getattr(bc, "rights", None)
    can_reply = bool(getattr(bc, "can_reply", True))
    can_read = bool(getattr(rights, "can_read_messages", False)) if rights else True
    if rights is not None and hasattr(rights, "can_reply"):
        can_reply = bool(rights.can_reply)
    logger.info(
        "Business connection %s: %s can_reply=%s can_read=%s owner=%s",
        bc.id,
        status,
        can_reply,
        can_read,
        bc.user.id,
    )
    print(f"Business Bot {status}: {bc.id} can_reply={can_reply} owner={bc.user.id}")
    try:
        await send_admin_notification(
            f"Business Bot {status}\n"
            f"connection_id: {bc.id}\n"
            f"can_reply: {can_reply}\n"
            f"owner: {bc.user.first_name} (@{bc.user.username}) id={bc.user.id}\n\n"
            f"AI отвечает только на сообщения КЛИЕНТОВ в ваши личные чаты."
        )
    except Exception:
        pass


async def _log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all debug: proves polling receives updates."""
    kinds = []
    for name in (
        "message",
        "business_message",
        "edited_business_message",
        "business_connection",
        "callback_query",
    ):
        if getattr(update, name, None) is not None:
            kinds.append(name)
    if kinds:
        logger.info("tg update #%s kinds=%s", update.update_id, ",".join(kinds))


def register_handlers(app: Application) -> None:
    global _handlers_registered
    if _handlers_registered:
        return
    # Log everything first (group=-1), does not block other handlers
    app.add_handler(TypeHandler(Update, _log_update), group=-1)

    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("admin", on_admin_command))
    app.add_handler(CallbackQueryHandler(on_admin_callback, pattern=r"^adm:"))
    app.add_handler(BusinessConnectionHandler(on_business_connection))

    media_filter = (
        filters.VOICE
        | filters.AUDIO
        | filters.PHOTO
        | filters.Document.ALL
        | filters.VIDEO_NOTE
        | filters.TEXT
        | filters.CAPTION
        | filters.Sticker.ALL
    )

    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGES & media_filter & ~filters.COMMAND,
            on_business_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & media_filter
            & ~filters.COMMAND
            & ~filters.UpdateType.BUSINESS_MESSAGES,
            on_private_message,
        )
    )
    _handlers_registered = True


async def start_telegram_bot() -> None:
    global _bot_running, _app, _handlers_registered
    # Always re-read .env (token may have been added after a previous import)
    get_settings.cache_clear()
    s = _settings()
    if not s.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN empty — Telegram disabled")
        print("TELEGRAM_BOT_TOKEN empty — Telegram disabled")
        _bot_running = False
        return

    _app = None
    _handlers_registered = False
    app = get_application()
    register_handlers(app)
    await app.initialize()
    me = await app.bot.get_me()
    await app.start()
    # Keep pending updates (business_connection) — do NOT drop on start
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )
    _bot_running = True
    msg = f"Telegram bot started as @{me.username} id={me.id} (Business + DM)"
    logger.info(msg)
    print(msg)


async def stop_telegram_bot() -> None:
    global _app, _bot_running, _handlers_registered
    _bot_running = False
    if _app is None:
        return
    try:
        if _app.updater and _app.updater.running:
            await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
    except Exception as e:
        logger.warning("Telegram stop: %s", e)
    _app = None
    _handlers_registered = False
