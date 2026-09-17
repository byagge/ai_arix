"""Client offer package and admin task notes."""
from __future__ import annotations

import re

from app.config import get_settings

OFFER_FOOTER = (
    "все делаем под ключ, настроим, запустим + 30 дней бесплатного обслуживания, "
    "поддержки, гарантии и правок"
)


def is_ready_to_pay(text: str) -> bool:
    lower = (text or "").lower()
    return bool(
        re.search(
            r"(?i)(?:оплач|плачу|кину|кидаю|реквизит|куда\s+(?:кид|перевод|слать)|"
            r"беру\b|давай\s+опла|готов\s+(?:оплат|плат)|сейчас\s+(?:перевед|кин))",
            lower,
        )
    )


def is_escrow_pay_intent(text: str) -> bool:
    lower = (text or "").lower()
    return bool(
        re.search(
            r"(?i)(?:через\s+гарант|через\s+эскроу|через\s+escrow|"
            r"опла\w*\s+(?:через\s+)?гарант|кину\s+на\s+гарант|"
            r"на\s+гаранта|давай\s+(?:через\s+)?гарант|буду\s+через\s+гарант)",
            lower,
        )
    )


def match_escrow_guarantee_question(text: str) -> str | None:
    """Short FAQ about guarantee — not a pay-via-escrow decision."""
    if is_escrow_pay_intent(text):
        return None
    lower = text.lower().strip()
    if re.search(r"^(гарант\s*\+?\s*\??|можно\s+через\s+гарант)", lower):
        return "+, можем через гаранта"
    if re.search(r"какой\s+гарант|какого\s+гарант|через\s+кого\s+гарант", lower):
        return "любой популярный, continental, lolz, greedy, gross"
    if re.search(r"в\s+каких\s+гарант|где\s+работал|какие\s+гарант", lower):
        return "continental, lolz, greedy, gross, S&A, get и др"
    if re.search(r"отправляю\s+сделк|скидываю\s+сделк|сделку\s+отправ", lower):
        return "да, отправляйте"
    if re.search(r"гарант", lower) and ("?" in lower or re.search(r"можно|есть", lower)):
        return "+, можем через гаранта"
    return None


def is_price_request(text: str) -> bool:
    lower = (text or "").lower()
    return bool(
        re.search(
            r"(?i)(?:сколько\s+сто|какая\s+цен|по\s+цен[еы]|прайс|стоимост|"
            r"сколько\s+будет|сколько\s+возьм|огласи\s+цен|назови\s+цен|"
            r"скинь\s+цен|цену\s+скаж|price)",
            lower,
        )
    )


def _fmt_money(v: float | int) -> str:
    n = float(v)
    if n == int(n):
        return f"${int(n)}"
    return f"${n:g}"


def _fmt_days(days: int | None) -> str:
    if days is None:
        return "5-8 дней"
    d = int(days)
    if 5 <= d <= 8:
        return "5-8 дней"
    if d <= 4:
        return "3-5 дней"
    if d <= 12:
        return f"{d - 2}-{d} дней"
    return f"~{d} дней"


def build_client_offer_message(
    *,
    pitch: str,
    price_usd: float | int | None,
    price_max_usd: float | int | None = None,
    days: int | None = None,
) -> str:
    """
    Client-facing offer (never admin summary):
    1) what we build
    2) price + timeline
    3) turnkey + 30 days support
    """
    desc = (pitch or "").strip()
    # Strip accidental admin-summary prefixes
    desc = re.sub(
        r"(?is)^\s*(?:клиент\s+запрос|тз\s+собрано|задача\s*:|по\s+задаче\s*:).*$",
        "",
        desc,
        count=1,
    ).strip() or desc
    desc = re.sub(r"\s+", " ", desc).strip()
    if desc and not desc[0].islower():
        # keep brand names; soften only if starts with admin-ish caps
        pass
    if not desc:
        desc = "делаем софт под вашу задачу"

    if price_usd is None:
        price_line = f"по срокам {_fmt_days(days)}"
    elif price_max_usd is not None and float(price_max_usd) > float(price_usd):
        price_line = (
            f"по цене выходит {_fmt_money(price_usd)} - {_fmt_money(price_max_usd)}, "
            f"по срокам {_fmt_days(days)}"
        )
    else:
        price_line = f"по цене выходит {_fmt_money(price_usd)}, по срокам {_fmt_days(days)}"

    return f"{desc}\n\n{price_line}\n\n{OFFER_FOOTER}"


def build_task_admin_note(
    *,
    dialog_id: int,
    username: str | None,
    user_id: int,
    admin_task_summary: str,
    last_message: str = "",
    estimated_price_usd: float | None = None,
    estimated_days: int | None = None,
) -> str:
    settings = get_settings()
    admin_tag = getattr(settings, "telegram_admin_tag", "@arxixx")
    user = f"@{username}" if username else f"id{user_id}"
    summary = (admin_task_summary or last_message or "без описания")[:800]
    est = (
        f"~{estimated_price_usd:g} usdt (черновик, не финал - двигай как надо)"
        if estimated_price_usd
        else "не оценено"
    )
    days = f"{estimated_days} дн" if estimated_days else "~5-8 дн"
    return (
        f"тз обновлено, нужна цена\n"
        f"диалог #{dialog_id}\n"
        f"клиент: {user} ({user_id})\n"
        f"задача: {summary}\n"
        f"оценка ии: {est}, срок {days}\n"
        f"{admin_tag}"
    )


def build_escrow_admin_note(
    *,
    username: str | None,
    user_id: int,
    amount: float | None,
    tz_summary: str,
) -> str:
    settings = get_settings()
    admin_tag = getattr(settings, "telegram_admin_tag", "@arxixx")
    amt = f"{amount:g} USDT" if amount else "сумма уточняется"
    user = f"@{username}" if username else f"id{user_id}"
    return (
        f"сделка на гарант\n"
        f"клиент: {user} ({user_id})\n"
        f"сумма: {amt}\n"
        f"тз: {tz_summary[:500]}\n"
        f"{admin_tag}"
    )
