"""Smart follow-up scheduling per MVP spec."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bot_extensions import FollowupMode
from app.db.models import Dialog, WorkStatus

VACATION_PATTERNS = re.compile(
    r"командировк|отпуск|отдых|не\s+работа|каникул|позже\s+напиш|через\s+\d+|"
    r"вернусь|занят|потом\s+свяж",
    re.I,
)

LATER_DATE_PATTERNS = [
    (re.compile(r"через\s+(\d+)\s+дн", re.I), "days"),
    (re.compile(r"через\s+(\d+)\s+нед", re.I), "weeks"),
    (re.compile(r"(\d{1,2})[./](\d{1,2})", re.I), "date"),
]


def detect_followup_mode(user_message: str) -> tuple[str, datetime | None]:
    lower = user_message.lower()
    if VACATION_PATTERNS.search(lower):
        return FollowupMode.VACATION.value, datetime.now(timezone.utc) + timedelta(days=7)

    m = re.search(r"через\s+(\d+)\s+дн", lower)
    if m:
        days = int(m.group(1))
        return FollowupMode.CUSTOM.value, datetime.now(timezone.utc) + timedelta(days=days)

    m = re.search(r"через\s+(\d+)\s+нед", lower)
    if m:
        weeks = int(m.group(1))
        return FollowupMode.CUSTOM.value, datetime.now(timezone.utc) + timedelta(weeks=weeks)

    return FollowupMode.STANDARD.value, None


def should_suppress_followup(dialog: Dialog) -> bool:
    if dialog.silent_until_completed:
        return True
    if dialog.work_status in (
        WorkStatus.PAYMENT_PENDING.value,
        WorkStatus.PAID.value,
        WorkStatus.IN_PROGRESS.value,
    ):
        return True
    if dialog.followup_mode == FollowupMode.NONE.value:
        return True
    return False


async def schedule_followup_after_reply(
    db: AsyncSession,
    dialog: Dialog,
    *,
    user_message: str | None = None,
    delays_hours: list[int] | None = None,
) -> None:
    if should_suppress_followup(dialog):
        dialog.next_followup_at = None
        dialog.followup_mode = FollowupMode.NONE.value
        return

    now = datetime.now(timezone.utc)
    delays = delays_hours or _default_delays()

    if user_message:
        mode, custom_at = detect_followup_mode(user_message)
        if custom_at:
            dialog.followup_mode = mode
            dialog.custom_followup_at = custom_at
            dialog.next_followup_at = custom_at
            return
        dialog.followup_mode = mode

    if dialog.followup_mode == FollowupMode.VACATION.value:
        dialog.next_followup_at = now + timedelta(days=7)
        return

    if dialog.followup_mode == FollowupMode.CUSTOM.value and dialog.custom_followup_at:
        dialog.next_followup_at = dialog.custom_followup_at
        return

    # Use configured delay ladder: 2h, 24h, 72h (or AgentSettings.followup_delays)
    dialog.followup_mode = FollowupMode.STANDARD.value
    dialog.next_followup_at = next_followup_at(now, dialog.followup_count, delays)


def _default_delays() -> list[int]:
    from app.config import get_settings

    return get_settings().followup_delays_list or [2, 24, 72]


def next_followup_at(now: datetime, followup_count: int, delays_hours: list[int]) -> datetime:
    delays = delays_hours or [2, 24, 72]
    idx = min(max(followup_count, 0), len(delays) - 1)
    return now + timedelta(hours=delays[idx])


FOLLOWUP_TEMPLATES = [
    "Привет, нужно будет?",
    "Здравствуйте, актуально?",
    "Добрый день, как вы?",
    "Привет, готовы сделать в лучшем виде, если ещё нужно",
    "Здравствуйте, на связи если вопрос остался",
]

PAYMENT_REMINDER = "Начинаем?"


def pick_followup_message(dialog: Dialog, *, payment_reminder: bool = False) -> str:
    import random
    if payment_reminder:
        return PAYMENT_REMINDER
    return random.choice(FOLLOWUP_TEMPLATES)
