"""Smoke tests for message classification + quality gate (no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.humanizer import humanize_reply, is_greeting_only
from app.services.message_intel import (
    MsgKind,
    classify_message,
    enrich_short_pointer_from_history,
    brief_anchors,
    ideal_tz_ack,
    is_compact_spec,
    is_short_question,
    is_stock_reply,
    merge_task_summary,
    quality_gate_reply,
    usable_client_pitch,
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
    assert fixed == ""
    assert not is_stock_reply(fixed)

    fixed2 = quality_gate_reply(
        "напишите что нужно - сделаем под задачу",
        content=enriched,
        has_tz_on_file=True,
    )
    assert fixed2 == ""
    assert is_stock_reply("тз вижу, парсер под ваши условия сделаем")
    assert is_stock_reply("ок, учёл")
    assert is_stock_reply("ок, докинул в задачу, учту")
    assert not is_stock_reply("токены тогда не считаю, в объёме парсер и дока")

    hist = [_Msg("user", WB_TZ)]
    pointer = enrich_short_pointer_from_history("тз вот", hist)
    assert "[клиент отвечает на сообщение]" in pointer
    assert "парсер" in pointer.lower()

    ack = ideal_tz_ack(content=WB_TZ)
    assert is_stock_reply(ack), ack

    brief = "нужен парсер вб, 5к запросов за 15 минут, 6 прокси и дока. сколько будет?"
    assert is_compact_spec(brief), brief
    assert not is_short_question(brief), brief
    question = "там не про новое тз, можно ли правки после сдачи?"
    assert is_short_question(question), question
    note = "токены сами греем, это не в объёме"
    stored = "парсер вб, 5к за 15 мин, дока"
    assert merge_task_summary(stored, note, note) == stored
    assert merge_task_summary(stored, question, question) == stored
    assert "sheets" in merge_task_summary(
        stored,
        "",
        "ещё нужна выгрузка в google sheets и алерты в телеграм если упал парсер",
    )
    assert usable_client_pitch("делаем привет, нашел твой контакт у скруджа подскажи парсер") == ""
    assert usable_client_pitch("делаем нужен парсер вб 5к под ключ") == ""
    assert "прокси" in usable_client_pitch("делаем парсер вб на 5к запросов с пулом прокси и докой")

    specific = "парсер вб на 5к за 15 минут и 6 прокси с докой берём, цену позже напишу"
    kept = humanize_reply(specific, allow_prices=False)
    assert "парсер" in kept, kept
    assert "уточни что именно" not in kept, kept
    assert is_stock_reply("уточни что именно нужно по задаче - цену скажу когда всё соберём")
    anchors = brief_anchors(WB_TZ)
    assert "парсер" in anchors and "прокси" in anchors, anchors
    assert "парсер" not in brief_anchors("нужен простой телеграм бот рассылки по базе, без парсера")

    print("OK — classifier + quality gate pass on Reign-style TZ")


if __name__ == "__main__":
    main()
