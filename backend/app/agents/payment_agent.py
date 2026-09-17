from app.agents.prompts import DEFAULT_PAYMENT_PROMPT
from app.services.llm import generate_json, generate_text


_READY_WORDS = (
    "оплат",
    "оплач",
    "плачу",
    "кину",
    "кидаю",
    "реквизит",
    "куда кид",
    "куда перевод",
    "куда слать",
    "беру",
    "давай опла",
    "готов оплат",
    "готов платит",
    "сейчас перевед",
    "сейчас кин",
)

_ESCROW_PAY = (
    "через гарант",
    "через эскроу",
    "через escrow",
    "оплачу гарант",
    "оплата гарант",
    "кину на гарант",
    "на гаранта",
    "давай через гарант",
    "буду через гарант",
    "давай гарант",
)


def _is_ready(msg: str) -> bool:
    low = msg.lower()
    return any(w in low for w in _READY_WORDS)


def _wants_escrow_pay(msg: str) -> bool:
    low = msg.lower()
    return any(w in low for w in _ESCROW_PAY)


async def generate_payment_response(
    user_message: str,
    conversation_history: str,
    dialog_id: int,
    settings: dict,
    orchestrator_hint: dict,
) -> tuple[str, dict]:
    from app.payments.monitor import create_payment_order_for_network
    from app.services.payment_templates import render_payment_message
    from app.services.quick_replies import build_escrow_admin_note

    def _detect_network(msg: str) -> str:
        low = msg.lower()
        if any(w in low for w in ("bep20", "bep-20", "bsc", "binance")):
            return "usdt-bep20"
        if any(w in low for w in ("solana", " sol ", "spl")):
            return "usdt-sol"
        if any(w in low for w in ("polygon", "matic")):
            return "usdt-polygon"
        if any(w in low for w in ("arbitrum", "arb ")):
            return "usdt-arbitrum"
        if any(w in low for w in ("optimism", "op ")):
            return "usdt-optimism"
        if any(w in low for w in ("avalanche", "avax")):
            return "usdt-avax"
        if "usdt" in low and "ton" in low:
            return "usdt-ton"
        if any(w in low for w in ("toncoin",)) or ("ton" in low and "usdt" not in low):
            return "ton"
        if any(w in low for w in ("erc20", "erc-20", "ethereum", "eth ")):
            return "usdt-erc20"
        return "usdt-tron"

    low = (user_message or "").lower()
    payment_data: dict = {}

    extract = await generate_json(
        f"""Извлеки из диалога сумму и описание заказа.
История:
{conversation_history}

Сообщение: {user_message}

Хинт оркестратора: {orchestrator_hint}

JSON:
{{"amount_usdt": 0, "description": "краткое описание товара/услуги", "wants_escrow": false, "wants_direct": false, "ready": false}}""",
        "Ты финансовый экстрактор. Только JSON.",
    )

    amount = float(
        extract.get("amount_usdt")
        or orchestrator_hint.get("extracted_amount")
        or orchestrator_hint.get("quoted_price_usd")
        or 0
    )
    description = (
        extract.get("description")
        or orchestrator_hint.get("extracted_product")
        or orchestrator_hint.get("tz_summary")
        or "Заказ"
    )

    wants_escrow = bool(extract.get("wants_escrow")) or _wants_escrow_pay(user_message)
    wants_direct = bool(extract.get("wants_direct")) or any(
        w in low for w in ("usdt", "trc-20", "trc20", "напрямую", "прямой", "реквизит")
    )
    ready = bool(
        extract.get("ready")
        or orchestrator_hint.get("ready_for_payment")
        or wants_direct
        or _is_ready(user_message)
    )

    # Pay via guarantee → notify admin, no client reply
    if wants_escrow and (ready or _wants_escrow_pay(user_message)):
        payment_data = {
            "silent": True,
            "escrow_pay": True,
            "amount_usdt": amount or None,
            "description": description,
            "admin_note": build_escrow_admin_note(
                username=orchestrator_hint.get("username"),
                user_id=int(orchestrator_hint.get("telegram_user_id") or 0),
                amount=amount or None,
                tz_summary=str(description)[:500],
            ),
        }
        return "", payment_data

    # Ready to pay → send USDT TRC-20 details immediately (default network)
    if ready or wants_direct:
        network = _detect_network(user_message) if wants_direct else "usdt-tron"
        if amount <= 0:
            return (
                "напиши сумму к оплате или дождись цены от менеджера, сразу скину реквизиты",
                {"awaiting_amount": True},
            )
        try:
            order = await create_payment_order_for_network(
                dialog_id=dialog_id,
                amount=amount,
                description=str(description)[:300],
                network_key=network,
            )
            payment_data = order
            rendered = await render_payment_message(network, float(order.get("amount_usdt") or amount))
            if rendered:
                return rendered, payment_data
            placeholder = f"{{{network}}}"
            return (
                f"ок, вот реквизиты {placeholder}\nсумма {order.get('amount_usdt')} usdt, после перевода кинь txid",
                payment_data,
            )
        except ValueError as e:
            payment_data = {"error": str(e), "network": network, "amount_usdt": amount}
            return (
                "секунду, менеджер скинет реквизиты вручную",
                payment_data,
            )

    system = settings.get("payment_prompt") or DEFAULT_PAYMENT_PROMPT
    prompt = f"""История:
{conversation_history}

Клиент: {user_message}

Клиент ещё не подтвердил оплату. Коротко уточни готов ли платить. Без гаранта, без давления, без длинного тире.

Ответ менеджера:"""
    response = await generate_text(prompt, system_instruction=system, temperature=0.55, prefer="gemini")
    return response, payment_data
