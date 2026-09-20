"""Per-dialog debounced reply queue — human read → typing → send."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.config import get_settings
from app.services.reply_outcome import ReplyOutcome
from app.telegram.delivery import deliver_reply, mark_read, reply_delay_sec

logger = logging.getLogger(__name__)
settings = get_settings()

ProcessFn = Callable[[list["QueuedMessage"]], Awaitable[ReplyOutcome | str | None]]


@dataclass
class QueuedMessage:
    chat_id: int
    user_id: int
    content: str
    username: str | None
    first_name: str | None
    message_id: int
    business_connection_id: str | None
    is_business: bool
    media_type: str = "text"
    save_only: bool = False
    # Quote the user message in Telegram only when they replied to something
    use_reply: bool = False


def _normalize_outcome(raw: ReplyOutcome | str | None) -> ReplyOutcome:
    if isinstance(raw, ReplyOutcome):
        return raw
    if raw:
        return ReplyOutcome.reply(str(raw))
    return ReplyOutcome.silent()


class ReplyQueue:
    def __init__(self) -> None:
        self._buffers: dict[str, list[QueuedMessage]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def _key(self, msg: QueuedMessage) -> str:
        bc = msg.business_connection_id or "direct"
        return f"{bc}:{msg.user_id}"

    async def enqueue(self, msg: QueuedMessage, process: ProcessFn) -> None:
        key = self._key(msg)
        async with self._lock:
            self._buffers.setdefault(key, []).append(msg)
            if key in self._tasks and not self._tasks[key].done():
                self._tasks[key].cancel()
            self._tasks[key] = asyncio.create_task(self._run(key, process))

    async def _run(self, key: str, process: ProcessFn) -> None:
        try:
            from app.telegram.client import get_application

            app = get_application()
            bot = app.bot

            # Snapshot current buffer for early read (before think delay)
            async with self._lock:
                pending = list(self._buffers.get(key, []))
            # Mark as read immediately — human opens chat, then thinks/types
            for m in pending:
                if m.save_only or not m.business_connection_id:
                    continue
                await mark_read(bot, m.chat_id, m.message_id, m.business_connection_id)

            delay = reply_delay_sec()
            await asyncio.sleep(delay)
            async with self._lock:
                batch = self._buffers.pop(key, [])
            if not batch:
                return

            last = batch[-1]

            # Messages that arrived during delay — mark those too
            already = {m.message_id for m in pending}
            for m in batch:
                if m.message_id in already or m.save_only or not m.business_connection_id:
                    continue
                await mark_read(bot, m.chat_id, m.message_id, m.business_connection_id)

            combined = "\n".join(m.content for m in batch if m.content)
            # Use last message metadata; content may be burst for LLM context
            last_content = last.content
            use_reply = any(m.use_reply for m in batch)
            merged = QueuedMessage(
                chat_id=last.chat_id,
                user_id=last.user_id,
                content=combined or last_content,
                username=last.username,
                first_name=last.first_name,
                message_id=last.message_id,
                business_connection_id=last.business_connection_id,
                is_business=last.is_business,
                media_type=last.media_type,
                save_only=any(m.save_only for m in batch),
                use_reply=use_reply,
            )

            outcome = _normalize_outcome(await process([merged]))

            if last.save_only or not outcome.should_send():
                return

            # Plain send by default; quote only when client replied or outcome asks
            should_quote = (
                outcome.use_reply if outcome.use_reply is not None else use_reply
            )
            await deliver_reply(
                bot,
                last.chat_id,
                outcome.text or "",
                business_connection_id=last.business_connection_id,
                reply_to_message_id=last.message_id if should_quote else None,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("reply queue %s: %s", key, e)


reply_queue = ReplyQueue()
