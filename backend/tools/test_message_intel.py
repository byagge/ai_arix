"""Smoke tests for message classification + quality gate (no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.humanizer import is_greeting_only
from app.services.message_intel import (
    MsgKind,
    classify_message,
    enrich_short_pointer_from_history,
    ideal_tz_ack,
    quality_gate_reply,
)


WB_TZ = """Привет, нашел твой контакт у скруджа 
Подскажи, такая задача: 
Нужен парсер вб.
Условия: 
~5к запросов за 15-20 минут. Времени между тиками нет, т.е закончил прогон за 15 мин, сразу начал новый. UPtime максимальный, без падений(допустима задержка 5мин между проходами) 
Максимум 6-7 прокси на 5к запросов.
Подскажи, если бы ты взялся за эту задачу сколько бы стоила разработка? Еще важно, что после разработки нужна документация."""


class _Msg:
    def __init__(self, role, content):
        from app.db.models import MessageRole

        self.role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
        self.content = content


def main() -> None:
    assert is_greeting_only("Привет")
    assert is_greeting_only("добрый день")
    assert not is_greeting_only(WB_TZ), "long TZ must not be greeting"
    assert not is_greeting_only("Привет, нужна утилита под редми"), "greeting+task"

    assert classify_message("Привет") == MsgKind.GREETING
    assert classify_message(WB_TZ) == MsgKind.LONG_TZ
    assert classify_message("тз вот") == MsgKind.SHORT_POINTER

    enriched = (
        "[клиент отвечает на сообщение]:\n" + WB_TZ + "\n\n[его ответ]:\nтз вот"
    )
    assert classify_message(enriched) == MsgKind.SHORT_POINTER

    fixed = quality_gate_reply(
        "привет, слушаю",
        content=WB_TZ,
        has_tz_on_file=False,
    )
    assert "привет, слушаю" not in fixed.lower() or "парсер" in fixed.lower()
    assert "слушаю" not in fixed or "тз" in fixed.lower() or "парсер" in fixed.lower()
    assert fixed != "привет, слушаю"

    fixed2 = quality_gate_reply(
        "напишите что нужно - сделаем под задачу",
        content=enriched,
        has_tz_on_file=True,
    )
    assert "напишите что нужно" not in fixed2.lower()

    hist = [_Msg("user", WB_TZ)]
    pointer = enrich_short_pointer_from_history("тз вот", hist)
    assert "[клиент отвечает на сообщение]" in pointer
    assert "парсер" in pointer.lower()

    ack = ideal_tz_ack(content=WB_TZ)
    assert "парсер" in ack.lower() or "тз" in ack.lower()

    print("OK — classifier + quality gate pass on Reign-style TZ")


if __name__ == "__main__":
    main()
