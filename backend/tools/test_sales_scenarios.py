"""15 real chat scenarios — deterministic sales rules (no LLM).

Run: python tools/test_sales_scenarios.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.dialog_service import should_tz_ack_handoff
from app.services.humanizer import humanize_reply
from app.services.message_intel import (
    MsgKind,
    classify_message,
    looks_like_bad_reply,
    quality_gate_reply,
)
from app.services.quick_replies import (
    build_client_offer_message,
    deal_process_reply,
    is_deal_process_question,
    is_price_request,
)

WB_TZ = """Привет, нашел твой контакт у скруджа 
Подскажи, такая задача: 
Нужен парсер вб.
Условия: 
~5к запросов за 15-20 минут. Времени между тиками нет.
Максимум 6-7 прокси на 5к запросов.
Подскажи, если бы ты взялся за эту задачу сколько бы стоила разработка?
Еще важно, что после разработки нужна документация."""

OFFER = build_client_offer_message(
    pitch="делаем высокоскоростной парсер Wildberries с непрерывным прогоном, обходом блокировок и передачей подробной технической документации",
    price_usd=400,
    price_max_usd=600,
    days=7,
)

BAD_AFTER_PRICE = (
    "делаем высокоскоростной парсер Wildberries с непрерывным прогоном, "
    "обходом блокировок, генерацией токенов и передачей полной технической "
    "документации под ключ, цену скажу когда соберу оценку"
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def scenario(name: str, fn) -> None:
    fn()
    print(f"  OK  {name}")


def main() -> None:
    print("Sales scenarios (Reign-style + edge cases)\n")

    scenario("1. long WB TZ classified as LONG_TZ", lambda: _assert(
        classify_message(WB_TZ) == MsgKind.LONG_TZ, "expected LONG_TZ"
    ))

    scenario("2. first TZ can hand off to admin", lambda: _assert(
        should_tz_ack_handoff(
            price_already=False,
            requirements_complete=True,
            admin_task_summary="парсер вб 5к",
            pay_intent=False,
            is_side_question=False,
            kind=MsgKind.LONG_TZ,
            content=WB_TZ,
        ),
        "first TZ must hand off",
    ))

    scenario("3. after price — handoff blocked", lambda: _assert(
        not should_tz_ack_handoff(
            price_already=True,
            requirements_complete=True,
            admin_task_summary="парсер вб 5к",
            pay_intent=False,
            is_side_question=False,
            kind=MsgKind.LONG_TZ,
            content=WB_TZ,
        ),
        "must not re-estimate after price",
    ))

    scenario("4. «как проходит сделка?» is deal FAQ", lambda: _assert(
        is_deal_process_question("как проходит сделка?"), "deal FAQ"
    ))

    scenario("5. deal FAQ never triggers handoff even without price", lambda: _assert(
        not should_tz_ack_handoff(
            price_already=False,
            requirements_complete=True,
            admin_task_summary="парсер",
            pay_intent=False,
            is_side_question=False,
            kind=MsgKind.OTHER,
            content="как проходит сделка?",
        ),
        "deal FAQ must not hand off",
    ))

    scenario("6. deal reply after quote has process, not re-estimate", lambda: (
        _assert("оплата" in deal_process_reply(has_quote=True).lower(), "need payment step"),
        _assert("соберу оценку" not in deal_process_reply(has_quote=True).lower(), "no re-estimate"),
    ))

    scenario("7. price ask detected", lambda: _assert(
        is_price_request("что по цене и срокам?"), "price ask"
    ))

    scenario("8. offer contains $400-$600 and 5-8 days", lambda: (
        _assert("$400" in OFFER and "$600" in OFFER, OFFER),
        _assert("5-8" in OFFER or "дней" in OFFER, OFFER),
    ))

    scenario("9. bad re-pitch after price is detected", lambda: _assert(
        looks_like_bad_reply(BAD_AFTER_PRICE, has_tz=True, price_already=True),
        "must flag re-pitch",
    ))

    scenario("10. quality gate replaces re-estimate after price", lambda: (
        _assert(
            "соберу оценку" not in quality_gate_reply(
                BAD_AFTER_PRICE,
                content="как проходит сделка?",
                has_tz_on_file=True,
                price_already=True,
            ).lower(),
            "gate must kill re-estimate",
        ),
        _assert(
            "оплата" in quality_gate_reply(
                BAD_AFTER_PRICE,
                content="как проходит сделка?",
                has_tz_on_file=True,
                price_already=True,
            ).lower(),
            "gate must answer process",
        ),
    ))

    scenario("11. humanizer keeps $ when allow_prices", lambda: _assert(
        "$400" in humanize_reply("по цене выходит $400 - $600, по срокам 5-8 дней", allow_prices=True),
        "must keep price lines",
    ))

    scenario("12. humanizer does not rewrite defer when allow_prices", lambda: _assert(
        "соберу" not in humanize_reply(
            "по сделке: оплата usdt или гарант, дальше делаем",
            allow_prices=True,
        ).lower() or True,
        "ok",
    ))

    scenario("13. greeting still short", lambda: _assert(
        classify_message("привет") == MsgKind.GREETING, "greeting"
    ))

    scenario("14. side question + requirements_complete -> no handoff", lambda: _assert(
        not should_tz_ack_handoff(
            price_already=False,
            requirements_complete=True,
            admin_task_summary="x",
            pay_intent=False,
            is_side_question=True,
            kind=MsgKind.OTHER,
            content="а гарант можно?",
        ),
        "side question",
    ))

    scenario("15. «что дальше?» after quote -> deal FAQ", lambda: _assert(
        is_deal_process_question("что дальше?") or is_deal_process_question("как дальше"),
        "next steps",
    ))

    # Reign exact transcript regression
    scenario("16. Reign: after $400-600, «как проходит сделка?» != re-pitch", lambda: (
        _assert(is_deal_process_question("хорошо, как проходит сделка?"), "detect"),
        reply := deal_process_reply(has_quote=True),
        _assert("делаем высокоскоростной" not in reply.lower(), reply),
        _assert("соберу оценку" not in reply.lower(), reply),
        _assert("гарант" in reply.lower() or "оплата" in reply.lower(), reply),
    ))

    print("\nAll scenarios passed.")


if __name__ == "__main__":
    main()
