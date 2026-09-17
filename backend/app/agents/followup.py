from app.agents.prompts import DEFAULT_FOLLOWUP_PROMPT
from app.services.llm import generate_text


async def generate_followup_response(
    conversation_history: str,
    settings: dict,
    followup_number: int = 1,
) -> str:
    system = settings.get("followup_prompt") or DEFAULT_FOLLOWUP_PROMPT
    prompt = f"""Follow-up #{followup_number} из {settings.get('max_followups', 3)}.
Макс. скидка: {settings.get('discount_max_percent', 10)}%.

История (клиент замолчал):
{conversation_history}

Одно короткое сообщение:"""
    return await generate_text(prompt, system_instruction=system, temperature=0.8)
