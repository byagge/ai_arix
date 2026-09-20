"""Result of processing an incoming Telegram message."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplyOutcome:
    text: str | None = None
    mark_read: bool = True
    # When True, Telegram send should quote the user's message (reply_to).
    # None = leave decision to QueuedMessage.use_reply.
    use_reply: bool | None = None

    @classmethod
    def silent(cls) -> ReplyOutcome:
        """No reply and no read receipt (e.g. task details while awaiting admin)."""
        return cls(text=None, mark_read=False)

    @classmethod
    def reply(
        cls,
        text: str,
        *,
        mark_read: bool = True,
        use_reply: bool | None = None,
    ) -> ReplyOutcome:
        return cls(text=text, mark_read=mark_read, use_reply=use_reply)

    def should_send(self) -> bool:
        return bool((self.text or "").strip())
