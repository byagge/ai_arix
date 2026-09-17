"""Cached runtime knobs from AgentSettings (updated by panel)."""
from __future__ import annotations

_delays: tuple[float, float] | None = None
_force_business_reply: bool = False
_global_ai_enabled: bool = True


def get_cached_delays() -> tuple[float, float] | None:
    return _delays


def set_cached_delays(min_s: float, max_s: float) -> None:
    global _delays
    _delays = (float(min_s), float(max_s))


def get_force_business_reply() -> bool:
    return _force_business_reply


def set_force_business_reply(v: bool) -> None:
    global _force_business_reply
    _force_business_reply = bool(v)


def get_global_ai_enabled() -> bool:
    return _global_ai_enabled


def set_global_ai_enabled(v: bool) -> None:
    global _global_ai_enabled
    _global_ai_enabled = bool(v)


async def refresh_from_db() -> None:
    from app.database import async_session
    from app.services.dialog_service import get_or_create_settings
    from app.config import get_settings

    cfg = get_settings()
    async with async_session() as db:
        s = await get_or_create_settings(db)
        min_s = getattr(s, "reply_delay_min_sec", None) or cfg.reply_delay_min_sec
        max_s = getattr(s, "reply_delay_max_sec", None) or cfg.reply_delay_max_sec
        set_cached_delays(min_s, max_s)
        set_force_business_reply(bool(getattr(s, "force_business_reply", False)))
        set_global_ai_enabled(bool(getattr(s, "global_ai_enabled", True)))
