"""Live reply check against the configured LLM (Gemini, else bardborn).

Does not embed API keys. Requires GOOGLE_API_KEY and/or BARDBORN_API_KEY
in the environment before import.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/arix-reply-eval.db")
os.environ["LLM_PRIMARY"] = "gemini"
# This harness must not spend the official Gemini/OpenAI balance.
os.environ["GOOGLE_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENAI_BASE_URL"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import Base, async_session, engine  # noqa: E402
from app.db import bot_extensions as _bot_ext  # noqa: F401, E402
from app.db import models as _models  # noqa: F401, E402
from app.db import platform_models as _platform  # noqa: F401, E402
from app.db.models import Dialog  # noqa: E402
from app.services.dialog_service import process_incoming_message  # noqa: E402
from app.services.message_intel import is_stock_reply  # noqa: E402
from sqlalchemy import select  # noqa: E402

WB_TZ = """Привет, нашел твой контакт у скруджа
Подскажи, такая задача:
Нужен парсер вб.
Условия:
~5к запросов за 15-20 минут. Времени между тиками нет, закончил прогон за 15 мин, сразу начал новый. UPtime максимальный.
Максимум 6-7 прокси на 5к запросов.
После разработки нужна документация.
Сколько будет стоить?"""


def _fail(msg: str) -> None:
    raise SystemExit(msg)


def _check(name: str, reply: str, must_have: tuple[str, ...], must_not: tuple[str, ...] = ()) -> None:
    text = (reply or "").strip()
    print(f"\n== {name}\n{text}\n")
    if not text:
        _fail(f"{name}: empty reply")
    if is_stock_reply(text):
        _fail(f"{name}: stock reply: {text}")
    low = text.lower()
    for banned in ("тз вижу", "тз принял", "ок, учел", "ок, учёл", "ок, докинул"):
        if low.startswith(banned):
            _fail(f"{name}: banned opener: {text}")
    if must_have and not any(token in low for token in must_have):
        _fail(f"{name}: missing any of {must_have}: {text}")
    for token in must_not:
        if token in low:
            _fail(f"{name}: unexpected {token!r}: {text}")


async def _summary(uid: int) -> str:
    async with async_session() as db:
        dialog = await db.scalar(select(Dialog).where(Dialog.telegram_user_id == uid))
        return ((dialog.tz_summary if dialog else "") or "").strip()


async def _turn(uid: int, text: str, mid: int) -> str:
    async with async_session() as db:
        outcome = await process_incoming_message(
            db,
            telegram_user_id=uid,
            content=text,
            username="eval",
            first_name="Eval",
            telegram_message_id=mid,
            ai_reply=True,
        )
        await db.commit()
        return outcome.text or ""


async def main() -> None:
    settings = get_settings()
    if not settings.bardborn_api_key and not settings.google_api_key:
        _fail("Set BARDBORN_API_KEY (Gemini key is intentionally blank in this harness)")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    first = await _turn(91001, WB_TZ, 1)
    _check("first TZ", first, ("парсер",))
    hits = sum(1 for token in ("прокси", "5", "док", "15", "uptime", "20") if token in first.lower())
    if hits < 2:
        _fail(f"first TZ did not reflect the brief ({hits} details): {first}")

    clarify = await _turn(91001, "токены сами греем, это не в объёме", 2)
    _check("token clarification", clarify, ("токен",), ("тз вижу",))
    if clarify.strip() == first.strip():
        _fail("clarification repeated the first TZ reply")

    price = await _turn(91001, "что по цене и срокам?", 3)
    _check("price ask while waiting", price, ("цен", "срок", "оцен", "цифр"), ("$", "тз вижу"))

    bot = await _turn(91002, "нужен простой телеграм бот рассылки по базе, без парсера", 1)
    _check("mailing bot", bot, ("бот", "рассыл"), ("тз вижу",))

    sources = await _turn(91003, "а исходники отдаёте после сдачи?", 1)
    _check("sources question", sources, ("исход", "код", "репозитор", "git"), ("тз вижу", "оценю и вернусь"))

    edits = await _turn(91001, "там не про новое тз, можно ли правки после сдачи?", 4)
    _check("edits question", edits, ("правк", "сдач", "поддерж"), ("тз вижу", "ок, учёл", "ок, учел"))

    stored = (await _summary(91001)).lower()
    print(f"\n== stored brief\n{stored}\n")
    if "парсер" not in stored:
        _fail(f"brief lost the parser task: {stored}")
    if "правки" in stored or stored.startswith("токены"):
        _fail(f"side message replaced the brief: {stored}")

    print("reply quality checks passed")


if __name__ == "__main__":
    asyncio.run(main())
