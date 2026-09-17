"""Human-like delivery: read receipts, typing, proportional delays."""
from __future__ import annotations

import asyncio
import logging
import random
import re

from telegram import Bot
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_HTML_TAG_RE = re.compile(r"</?(?:b|i|u|s|code|pre|blockquote|tg-spoiler|a)(?:\s[^>]*)?>", re.I)


def looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(text or ""))


async def mark_read(
    bot: Bot,
    chat_id: int,
    message_id: int,
    business_connection_id: str | None = None,
) -> None:
    try:
        if business_connection_id:
            await bot.read_business_message(
                business_connection_id=business_connection_id,
                chat_id=chat_id,
                message_id=message_id,
            )
    except Exception as e:
        logger.debug("read receipt: %s", e)


async def typing_loop(
    bot: Bot,
    chat_id: int,
    duration_sec: float,
    business_connection_id: str | None = None,
) -> None:
    """Keep sending typing action until duration elapses."""
    end = asyncio.get_event_loop().time() + duration_sec
    while asyncio.get_event_loop().time() < end:
        try:
            await bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING,
                business_connection_id=business_connection_id,
            )
        except Exception:
            pass
        await asyncio.sleep(min(4.5, max(0.5, end - asyncio.get_event_loop().time())))


def reply_delay_sec() -> float:
    """Prefer delays from AgentSettings (panel), fallback to .env."""
    min_s = settings.reply_delay_min_sec
    max_s = settings.reply_delay_max_sec
    try:
        from app.services.runtime_config import get_cached_delays

        cached = get_cached_delays()
        if cached:
            min_s, max_s = cached
    except Exception:
        pass
    if max_s < min_s:
        max_s = min_s
    return random.uniform(min_s, max_s)


def typing_duration_for_text(text: str) -> float:
    """Longer answers = longer typing, capped."""
    chars = len(text or "")
    base = settings.typing_chars_per_second or 12.0
    duration = chars / base
    return max(settings.typing_delay_min, min(settings.typing_delay_max, duration))


async def deliver_reply(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    business_connection_id: str | None = None,
    reply_to_message_id: int | None = None,
) -> None:
    if not (text or "").strip():
        return
    typing_sec = typing_duration_for_text(text)
    await typing_loop(bot, chat_id, typing_sec, business_connection_id)

    kwargs: dict = {
        "chat_id": chat_id,
        "text": text,
        "business_connection_id": business_connection_id,
        "reply_to_message_id": reply_to_message_id,
        "disable_web_page_preview": True,
    }
    if looks_like_html(text):
        kwargs["parse_mode"] = ParseMode.HTML

    try:
        await bot.send_message(**kwargs)
    except BadRequest as e:
        # Fallback: strip HTML if Telegram rejects entities
        logger.warning("send_message HTML failed (%s), retrying plain", e)
        kwargs.pop("parse_mode", None)
        plain = re.sub(r"<[^>]+>", "", text)
        kwargs["text"] = plain
        await bot.send_message(**kwargs)
