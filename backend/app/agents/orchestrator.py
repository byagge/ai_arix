from app.agents.prompts import DEFAULT_ORCHESTRATOR_PROMPT
from app.services.llm import generate_json


async def analyze_dialog(
    user_message: str,
    conversation_history: str,
    funnel_stage: str,
    settings: dict,
) -> dict:
    system = settings.get("orchestrator_prompt") or DEFAULT_ORCHESTRATOR_PROMPT
    prompt = f"""Стадия воронки: {funnel_stage}

История диалога:
{conversation_history}

Новое сообщение клиента:
{user_message}

Верни JSON:
{{
  "funnel_stage": "new|qualification|consultation|negotiation|payment_pending|paid|escrow|escrow_draft|completed|lost",
  "intent": "consultation|purchase|payment|objection|complaint|idle|greeting|escrow_request",
  "target_agent": "sales|followup|payment|none",
  "should_respond": true,
  "reasoning": "краткое обоснование",
  "urgency": "low|medium|high",
  "ready_for_payment": false,
  "extracted_amount": null,
  "extracted_product": null,
  "requirements_complete": false,
  "admin_task_summary": null,
  "client_offer_pitch": null,
  "estimated_price_usd": null,
  "estimated_days": null,
  "is_side_question": false
}}

Поля requirements_complete / admin_task_summary / client_offer_pitch / estimated_*:
- requirements_complete=true только если из истории уже ясно ЧТО делать (задача, платформа, функционал, объём) и осталось только назвать цену менеджеру
- admin_task_summary: для АДМИНА - 2-5 предложений что делать (можно техдетали, чипсет, открытые вопросы). НЕ для клиента
- client_offer_pitch: для КЛИЕНТА - одно предложение-описание продукта в тоне продаж, начинай с «делаем …», без слов клиент/тз/нужна модель, без цен. Пример: «делаем утилиту под смену imei на redmi с учётом чипсета, настройкой и запуском под ключ»
- estimated_price_usd: примерная цена в USD ТОЛЬКО для админа (черновик, не финал), целое число
- estimated_days: ориентир дней (обычно 5-8)

Поле is_side_question:
- true если сообщение НЕ про текущую задачу (гарант, посторонний вопрос, small talk без продолжения тз)
- false если клиент дополняет тз, уточняет задачу, модель, функции, сроки по проекту"""
    try:
        data = await generate_json(prompt, system)
        data.setdefault("requirements_complete", False)
        data.setdefault("admin_task_summary", None)
        data.setdefault("client_offer_pitch", None)
        data.setdefault("estimated_price_usd", None)
        data.setdefault("estimated_days", None)
        data.setdefault("is_side_question", False)
        lower = user_message.lower()
        # Product questions stay on sales — never auto-push escrow
        if data.get("intent") == "escrow_request" or any(
            w in lower for w in ("гарант", "escrow")
        ):
            data["intent"] = "escrow_request"
            data["target_agent"] = "sales"
            data["ready_for_payment"] = False
        # Only payment agent when client clearly wants to pay / needs wallets
        elif data.get("target_agent") == "payment" and not any(
            w in lower
            for w in (
                "оплат",
                "оплач",
                "usdt",
                "реквизит",
                "кошел",
                "перевод",
                "кинуть",
                "кидать",
                "плачу",
                "беру",
            )
        ):
            data["target_agent"] = "sales"
            data["ready_for_payment"] = False
        # Explicit pay intent
        if any(w in lower for w in ("оплач", "плачу", "давай опла", "реквизит", "куда кид")):
            data["target_agent"] = "payment"
            data["ready_for_payment"] = True
            data["intent"] = "payment"
        return data
    except Exception:
        lower = user_message.lower()
        if any(w in lower for w in ("гарант", "escrow")):
            return {
                "funnel_stage": funnel_stage,
                "intent": "escrow_request",
                "target_agent": "sales",
                "should_respond": True,
                "reasoning": "escrow ask",
                "urgency": "medium",
                "ready_for_payment": False,
                "extracted_amount": None,
                "extracted_product": None,
                "requirements_complete": False,
                "admin_task_summary": None,
                "client_offer_pitch": None,
                "estimated_price_usd": None,
                "estimated_days": None,
                "is_side_question": False,
            }
        if any(
            w in lower
            for w in ("оплат", "оплач", "usdt", "реквизит", "кошел", "плачу", "давай опла")
        ):
            return {
                "funnel_stage": "payment_pending",
                "intent": "payment",
                "target_agent": "payment",
                "should_respond": True,
                "reasoning": "payment keywords",
                "urgency": "high",
                "ready_for_payment": True,
                "extracted_amount": None,
                "extracted_product": None,
                "requirements_complete": False,
                "admin_task_summary": None,
                "client_offer_pitch": None,
                "estimated_price_usd": None,
                "estimated_days": None,
                "is_side_question": False,
            }
        side = any(w in lower for w in ("гарант", "escrow", "привет", "здравств", "hello", "hi"))
        return {
            "funnel_stage": funnel_stage,
            "intent": "consultation",
            "target_agent": "sales",
            "should_respond": True,
            "reasoning": "fallback",
            "urgency": "medium",
            "ready_for_payment": False,
            "extracted_amount": None,
            "extracted_product": None,
            "requirements_complete": False,
            "admin_task_summary": None,
            "client_offer_pitch": None,
            "estimated_price_usd": None,
            "estimated_days": None,
            "is_side_question": side,
        }
