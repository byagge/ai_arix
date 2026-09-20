"""Live multi-turn chats through real process_incoming_message + Gemini.

Usage (from backend/):
  ../venv/Scripts/python.exe tools/live_chat_drill.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Silence SQLAlchemy noise for readable transcripts
import logging

logging.basicConfig(level=logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from app.database import async_session
from app.db.models import Dialog
from app.services.dialog_service import process_incoming_message, send_approved_offer
from app.services.quick_replies import is_deal_process_question, is_price_request
from sqlalchemy import select

OUT = Path(__file__).resolve().parent / "live_chat_results.jsonl"


@dataclass
class Turn:
    client: str
    bot: str
    ok: bool
    fails: list[str] = field(default_factory=list)


@dataclass
class ChatResult:
    name: str
    turns: list[Turn]
    passed: bool


def judge(client: str, bot: str, *, price_given: bool) -> list[str]:
    """Return list of failure reasons (empty = good)."""
    fails: list[str] = []
    b = (bot or "").strip()
    bl = b.lower()
    cl = (client or "").lower()

    if not b or b == "(silent)":
        # Silent is only OK for rare admin-only escrow pay decisions
        if re.search(r"(?i)(?:оплачу через|кину на гарант|давай через гарант)", cl):
            return []
        if is_price_request(client) or is_deal_process_question(client):
            fails.append("silent_on_question")
        elif "гарант" in cl and "?" in client:
            fails.append("silent_on_escrow_faq")
        elif len(client) >= 8:
            fails.append("unexpected_silent")
        if fails:
            return fails
        return ["empty"] if not b else []

    # Robotic / template fails
    if re.search(r"(?i)^(привет|здравствуйте|добрый\s+день)[\s,!.]*(слушаю|чем могу|напишите)", bl):
        if len(client) > 60 or "парсер" in cl or "тз" in cl or "нужен" in cl:
            fails.append("greeting_on_tz")

    if price_given:
        if "соберу оценку" in bl or "ценю и вернусь" in bl or "оценю и напишу" in bl:
            fails.append("re_estimate_after_price")
        if re.search(r"(?i)^делаем\b.+(под\s+ключ|настроим)", bl) and "оплат" not in bl:
            if "как проходит" in cl or "сделк" in cl or "дальше" in cl:
                fails.append("repeat_pitch_on_deal_faq")

    if not price_given and len(client) > 120:
        if re.search(r"(?i)^(привет|слушаю)[\s!.]*$", bl):
            fails.append("ignored_tz")
        if "напишите что нужно" in bl or "чем могу помочь" in bl:
            fails.append("ask_again_with_tz")

    if "—" in b or "–" in b:
        fails.append("long_dash")

    if re.search(r"(?<![:/\w])\w+\s*/\s*\w+", b) and "http" not in bl:
        if re.search(r"(?i)\b(бот|сайт|usdt|гарант)\s*/\s*\w+", bl):
            fails.append("slash_alt")

    if price_given and ("как проходит" in cl or "сделк" in cl or "что дальше" in cl):
        if not any(w in bl for w in ("оплат", "гарант", "usdt", "срок", "отда", "переда", "правк", "дока")):
            fails.append("deal_faq_no_process")

    if "чуть подвисло" in bl:
        fails.append("llm_crash_fallback")

    return fails


async def client_say(
    uid: int,
    text: str,
    *,
    username: str = "drill_client",
) -> str:
    async with async_session() as db:
        outcome = await process_incoming_message(
            db,
            telegram_user_id=uid,
            content=text,
            username=username,
            first_name="Drill",
            telegram_chat_id=uid,
            is_business=False,
        )
        await db.commit()
        return (outcome.text or "").strip() if outcome.should_send() else "(silent)"


async def admin_approve(uid: int, price: float = 400, price_max: float = 600, days: int = 7) -> str:
    async with async_session() as db:
        dialog = (
            await db.execute(select(Dialog).where(Dialog.telegram_user_id == uid))
        ).scalar_one()
        dialog.quoted_price_usd = price
        dialog.quoted_price_max_usd = price_max
        dialog.quoted_days = days
        dialog.price_approved = True
        if not (dialog.client_offer_pitch or "").strip():
            summary = (dialog.tz_summary or dialog.admin_task_summary or "софт под задачу").strip()
            dialog.client_offer_pitch = f"делаем {summary[:120].lower()} под ключ"
        offer = await send_approved_offer(db, dialog)
        await db.commit()
        return offer


async def run_chat(name: str, uid: int, script: list) -> ChatResult:
    """script items: str client msg, or ('APPROVE',) or dict with meta."""
    turns: list[Turn] = []
    price_given = False
    print(f"\n{'='*60}\nCHAT: {name}\n{'='*60}")
    for step in script:
        if step == "APPROVE" or (isinstance(step, tuple) and step[0] == "APPROVE"):
            offer = await admin_approve(uid)
            price_given = True
            print(f"\n[ADMIN APPROVE]\n{offer}\n")
            turns.append(Turn("[admin approve]", offer, True, []))
            continue

        client = step if isinstance(step, str) else step["text"]
        print(f"\nCLIENT: {client[:200]}{'...' if len(client)>200 else ''}")
        bot = await client_say(uid, client)
        fails = judge(client, bot, price_given=price_given)
        # If offer just sent via approve, price is given
        if "$" in bot and "по цене" in bot.lower():
            price_given = True
        ok = not fails
        mark = "PASS" if ok else "FAIL " + ",".join(fails)
        print(f"BOT ({mark}): {bot[:300]}{'...' if len(bot)>300 else ''}")
        turns.append(Turn(client, bot, ok, fails))
        await asyncio.sleep(1.5)

    passed = all(t.ok for t in turns if t.client != "[admin approve]")
    return ChatResult(name=name, turns=turns, passed=passed)


WB = """Привет, нашел твой контакт у скруджа 
Подскажи, такая задача: 
Нужен парсер вб.
Условия: 
~5к запросов за 15-20 минут. Времени между тиками нет, т.е закончил прогон за 15 мин, сразу начал новый. UPtime максимальный, без падений(допустима задержка 5мин между проходами) 
Максимум 6-7 прокси на 5к запросов. (Или, возможно, ты знаешь сервис, который предоставляет платно пул прокси за вменяемые деньги, без ограничений пропускной способности и платы за трафик. Тк трафика за месяц будут терабайты, платить за трафик смысла нет).
Что известно: 
Удалось классическим методом достичь прохода 5к запросов - 1час, после 2 часа перерыв. Достаточно стабильно, но не подходит по условиям задачи. 
cURL запросы с сервера работают, но для них нужны токены авторизации вб, которые получаются только при реальном прогреве (заход на сайт+1 поиск по сайту). (Про реальный прогрев лично моя мысль, не подтверждено , что только так работает. Может есть другие варианты) 
Антидетект браузер не использовался

Точно знаю, что на рынке существуют такие решения и , достаточно много.

Подскажи, если бы ты взялся за эту задачу сколько бы стоила разработка? Еще важно, что после разработки нужна документация по решению проблемы, тк в дальнейшем буду поддерживать сам."""


CHATS: list[tuple[str, int, list]] = [
    (
        "R1_reign_wb_full",
        920001,
        [
            WB,
            "что по цене и срокам?",
            "APPROVE",
            "хорошо, как проходит сделка?",
            "можно через гаранта?",
        ],
    ),
    (
        "R2_clarify_while_waiting",
        920002,
        [
            "нужен парсер вб 5к запросов за 15 мин, дока нужна",
            "токены сами греем, это не в объёме",
            "APPROVE",
            "как работаем дальше?",
        ],
    ),
    (
        "R3_pay_after_quote",
        920003,
        [
            "нужен простой телеграм бот рассылки",
            "APPROVE",
            "готов оплатить, куда кидать usdt?",
        ],
    ),
    (
        "R4_escrow_faq",
        920004,
        [
            "привет, делаете ботов?",
            "гарант можно?",
            "можно через гаранта?",
            "какой гарант?",
        ],
    ),
    (
        "R5_deal_then_price_ask",
        920005,
        [
            "нужен дрейнер tron trc20 под сайт",
            "APPROVE",
            "ещё раз по цене",
            "как проходит сделка?",
        ],
    ),
]


async def main() -> None:
    from unittest.mock import AsyncMock, patch

    from app.services.llm import _has_any_llm_key

    if not _has_any_llm_key():
        print("ERROR: no LLM keys — abort")
        sys.exit(2)

    results: list[ChatResult] = []
    with patch("app.telegram.client.send_admin_notification", new_callable=AsyncMock):
        for name, uid, script in CHATS:
            try:
                r = await run_chat(name, uid, script)
                results.append(r)
            except Exception as e:
                print(f"\nCHAT {name} CRASHED: {e}")
                results.append(
                    ChatResult(name=name, turns=[Turn("?", str(e), False, ["crash"])], passed=False)
                )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    failed = []
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        bad = [t for t in r.turns if not t.ok]
        print(f"  {status}  {r.name}  ({len(bad)} bad turns)")
        if not r.passed:
            failed.append(r)
            for t in bad:
                print(f"      - fails={t.fails}")
                print(f"        C: {t.client[:80]}")
                print(f"        B: {t.bot[:120]}")

    # Write transcript
    with OUT.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "name": r.name,
                        "passed": r.passed,
                        "turns": [
                            {"client": t.client, "bot": t.bot, "ok": t.ok, "fails": t.fails}
                            for t in r.turns
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"\nWrote {OUT}")
    print(f"Passed {sum(1 for r in results if r.passed)}/{len(results)}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    asyncio.run(main())
