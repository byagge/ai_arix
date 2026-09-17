from app.agents.prompts import DEFAULT_SALES_PROMPT
from app.services.llm import generate_text


async def generate_sales_response(
    user_message: str,
    conversation_history: str,
    rag_context: str,
    settings: dict,
    orchestrator_hint: dict,
) -> str:
    tone = settings.get("tone", "professional_friendly")
    system = settings.get("sales_prompt") or DEFAULT_SALES_PROMPT
    system += (
        f"\n\nТон: {tone}. Макс. скидка: {settings.get('discount_max_percent', 10)}%."
        "\nПиши живо, как в мессенджере. Без эмодзи-спама."
    )

    prompt = f"""База знаний:
{rag_context or "База знаний пуста — опирайся на общие условия и уточняй детали."}

Профиль решения оркестратора: {orchestrator_hint}

История:
{conversation_history}

Клиент: {user_message}

Ответ менеджера:"""

    return await generate_text(prompt, system_instruction=system, temperature=0.75, prefer="gemini")
