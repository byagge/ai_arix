"""Result of processing an incoming Telegram message."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReplyOutcome:
    text: str | None = None
    mark_read: bool = True

    @classmethod
    def silent(cls) -> ReplyOutcome:
        """No reply and no read receipt (e.g. task details while awaiting admin)."""
        return cls(text=None, mark_read=False)

    @classmethod
    def reply(cls, text: str, *, mark_read: bool = True) -> ReplyOutcome:
        return cls(text=text, mark_read=mark_read)

    def should_send(self) -> bool:
        return bool((self.text or "").strip())
