"""Event bus with Redis pub/sub or in-memory fallback."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from app.config import get_settings

settings = get_settings()
_redis = None
_subscribers: list[Callable] = []
_recent_events: list[dict] = []


def subscribe(callback: Callable) -> None:
    if callback not in _subscribers:
        _subscribers.append(callback)


def unsubscribe(callback: Callable) -> None:
    try:
        _subscribers.remove(callback)
    except ValueError:
        pass


async def get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        _redis = r
        return _redis
    except Exception:
        _redis = False
        return None


async def publish_event(channel: str, data: dict[str, Any]) -> None:
    _recent_events.insert(0, data)
    del _recent_events[200:]
    for cb in list(_subscribers):
        try:
            result = cb(data)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass
    r = await get_redis()
    if r:
        await r.publish(channel, json.dumps(data, default=str))


async def broadcast_agent_event(event_type: str, agent_name: str, payload: dict[str, Any]) -> None:
    await publish_event(
        "agent_events",
        {"event_type": event_type, "agent_name": agent_name, **payload},
    )


def get_recent_events(limit: int = 50) -> list[dict]:
    return _recent_events[:limit]
