from app.agents.prompts import DEFAULT_SALES_PROMPT
from app.services.llm import generate_text
from app.services.message_intel import MsgKind, classify_message, has_reply_context, has_task_substance
from app.services.quick_replies import is_deal_process_question


def _deal_facts_block(orchestrator_hint: dict) -> str:
    hint = orchestrator_hint or {}
    approved = bool(hint.get("price_approved"))
    price = hint.get("quoted_price_usd")
    price_max = hint.get("quoted_price_max_usd")
    days = hint.get("quoted_days")
    pitch = (hint.get("client_offer_pitch") or "").strip()
    lines = ["ФАКТЫ СДЕЛКИ (источник истины, не выдумывай против них):"]
    if approved or price:
        if price_max and price and float(price_max) > float(price):
            lines.append(f"- цена уже названа клиенту: ${float(price):g} - ${float(price_max):g}")
        elif price:
            lines.append(f"- цена уже названа клиенту: ${float(price):g}")
        else:
            lines.append("- цена уже утверждена админом")
        if days:
            lines.append(f"- сроки: ~{days} дней (или 5-8 если так писали)")
        lines.append(
            "- ЗАПРЕЩЕНО: «цену скажу когда соберу оценку», повторный питч «делаем … под ключ» "
            "как будто оценки ещё не было"
        )
        lines.append("- на вопросы про процесс сделки отвечай по этапам, опираясь на уже данную цену")
    else:
        lines.append("- цены клиенту ещё не было — суммы сам не называй, можно сказать что оценишь")
    if pitch:
        lines.append(f"- уже использованный pitch (не копируй дословно снова): {pitch[:240]}")
    return "\n".join(lines)


async def generate_sales_response(
    user_message: str,
    conversation_history: str,
    rag_context: str,
    settings: dict,
    orchestrator_hint: dict,
) -> str:
    tone = settings.get("tone", "professional_friendly")
    system = settings.get("sales_prompt") or DEFAULT_SALES_PROMPT
    kind = classify_message(user_message)
    hint = orchestrator_hint or {}
    price_already = bool(hint.get("price_approved") or hint.get("quoted_price_usd"))

    extra = [
        f"\n\nТон: {tone}. Макс. скидка: {settings.get('discount_max_percent', 10)}%.",
        "Пиши живо, как в мессенджере. Без эмодзи-спама.",
        _deal_facts_block(hint),
    ]
    if price_already:
        extra.append(
            "Цена УЖЕ в сделке. Отвечай по делу текущего вопроса. "
            "Не начинай ответ с «делаем …» и не обещай новую оценку."
        )
    if is_deal_process_question(user_message):
        extra.append(
            "Клиент спросил про процесс сделки. Ответь этапами: тз/цена → оплата → работа → сдача+дока → 30 дней. "
            "Без повторного коммерческого питча."
        )
    if (kind == MsgKind.LONG_TZ or has_task_substance(user_message)) and not price_already:
        extra.append(
            "СЕЙЧАС у клиента уже есть ТЗ в сообщении. "
            "Запрещены ответы: «привет», «привет, слушаю», «напишите что нужно», «чем могу помочь». "
            "Подтверди задачу по сути (1 фраза) + максимум один уточняющий вопрос ИЛИ скажи что оценишь и вернёшься с ценой."
        )
    if kind == MsgKind.SHORT_POINTER or has_reply_context(user_message):
        extra.append(
            "Клиент указал на предыдущее ТЗ коротко («вот» / reply). "
            "ТЗ уже в контексте выше - отвечай по нему, не проси описать задачу заново."
        )
    if hint.get("tz_summary"):
        extra.append(f"Уже зафиксированное ТЗ в системе: {(hint.get('tz_summary') or '')[:500]}")

    system += "\n".join(extra)

    prompt = f"""База знаний:
{rag_context or "База знаний пуста — опирайся на общие условия и уточняй детали."}

Профиль решения оркестратора: {orchestrator_hint}

История:
{conversation_history}

Клиент: {user_message}

Ответ менеджера:"""

    # Lower temp → more consistent TZ acks, fewer greeting-template slips
    return await generate_text(prompt, system_instruction=system, temperature=0.55, prefer="gemini")
