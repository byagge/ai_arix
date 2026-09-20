"""Multi-provider LLM brain: Gemini + OpenAI + Anthropic with failover."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def _settings():
    return get_settings()


def _has_any_llm_key() -> bool:
    settings = _settings()
    return bool(
        settings.google_api_key
        or (settings.openai_api_key and settings.openai_api_key != "local" and not settings.openai_base_url)
        or (settings.openai_api_key and settings.openai_base_url)
        or settings.anthropic_api_key
    )


async def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.7,
    prefer: str | None = None,
) -> str:
    settings = _settings()
    order = list(settings.llm_fallback_list)
    if prefer and prefer in order:
        order = [prefer] + [x for x in order if x != prefer]
    elif settings.llm_primary in order:
        order = [settings.llm_primary] + [x for x in order if x != settings.llm_primary]

    errors: list[str] = []
    for provider in order:
        try:
            if provider == "gemini" and settings.google_api_key:
                return await _gemini(prompt, system_instruction, temperature)
            if provider == "openai" and settings.openai_api_key:
                return await _openai(prompt, system_instruction, temperature)
            if provider == "anthropic" and settings.anthropic_api_key:
                return await _anthropic(prompt, system_instruction, temperature)
        except Exception as e:
            logger.warning("LLM %s failed: %s", provider, e)
            errors.append(f"{provider}: {e}")
            continue

    if errors:
        logger.error("All LLM providers failed: %s", "; ".join(errors))
    return _heuristic_reply(prompt, system_instruction)


async def generate_json(
    prompt: str,
    system_instruction: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    text = await generate_text(
        prompt + "\n\nRespond ONLY with valid JSON, no markdown.",
        system_instruction=system_instruction,
        temperature=temperature,
    )
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}


async def _gemini(prompt: str, system: str | None, temperature: float) -> str:
    import google.generativeai as genai
    from google.generativeai.types import HarmBlockThreshold, HarmCategory

    settings = _settings()
    genai.configure(api_key=settings.google_api_key)
    models_try = [
        settings.gemini_model,
        "gemini-3.6-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-1.5-flash",
    ]
    # unique preserve order
    seen: set[str] = set()
    models: list[str] = []
    for m in models_try:
        if m and m not in seen:
            seen.add(m)
            models.append(m)

    last_err: Exception | None = None
    for model_name in models:
        try:
            kwargs: dict = {
                "model_name": model_name,
                "safety_settings": {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                },
            }
            if system:
                kwargs["system_instruction"] = system
            model = genai.GenerativeModel(**kwargs)
            response = await model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(temperature=temperature),
            )
            text = ""
            try:
                text = (response.text or "").strip()
            except Exception:
                text = ""
            if not text:
                raise RuntimeError(f"empty Gemini response ({model_name})")
            if model_name != settings.gemini_model:
                logger.info("Gemini fallback model used: %s", model_name)
            return text
        except Exception as e:
            last_err = e
            logger.warning("Gemini model %s failed: %s", model_name, e)
            continue
    raise RuntimeError(f"All Gemini models failed: {last_err}")


def _openai_client():
    from openai import AsyncOpenAI
    from app.services.providers import _openai_base_url

    settings = _settings()
    base = _openai_base_url()
    kwargs: dict = {"api_key": settings.openai_api_key, "timeout": 25.0}
    if base:
        kwargs["base_url"] = base
        if "127.0.0.1" in base or "localhost" in base:
            kwargs["timeout"] = 4.0
    return AsyncOpenAI(**kwargs)


async def _openai(prompt: str, system: str | None, temperature: float) -> str:
    settings = _settings()
    client = _openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=temperature,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("empty OpenAI response")
    return text


async def _anthropic(prompt: str, system: str | None, temperature: float) -> str:
    from anthropic import AsyncAnthropic

    settings = _settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        temperature=temperature,
        system=system or "You are a helpful sales assistant.",
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _heuristic_reply(prompt: str, system: str | None) -> str:
    """Last-resort reply when all LLMs fail. Uses ONLY the client line, not system prompt."""
    # Prefer last "Клиент:" block (may be multiline after enrichment)
    user_bits = re.findall(r"Клиент:\s*((?:.|\n)+?)(?=\n(?:Менеджер|Оператор|Клиент):|\Z)", prompt or "", flags=re.I)
    focus = (user_bits[-1] if user_bits else "").strip()
    if not focus:
        parts = [p.strip() for p in (prompt or "").split("\n") if p.strip()]
        focus = parts[-1][:2000] if parts else ""
    # If enrichment wrapper, use full focus (quoted TZ + answer)
    lower = focus.lower()
    sys_l = (system or "").lower()

    if "json" in sys_l or "respond only with valid json" in (prompt or "").lower():
        return json.dumps(
            {
                "funnel_stage": "consultation",
                "intent": "consultation",
                "target_agent": "sales",
                "should_respond": True,
                "reasoning": "local heuristic",
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
            },
            ensure_ascii=False,
        )

    from app.services.message_intel import (
        has_reply_context,
        has_task_substance,
        ideal_tz_ack,
        is_short_pointer,
    )

    if has_task_substance(focus) or has_reply_context(focus) or is_short_pointer(focus):
        return ideal_tz_ack(
            pointer=is_short_pointer(focus) or has_reply_context(focus),
            content=focus,
        )

    # Escrow only if CLIENT asked
    if any(w in lower for w in ("гарант", "escrow")):
        return "да, можно через гаранта"

    if any(w in lower for w in ("срок", "когда готов", "сколько дн", "как быстро")):
        return "по срокам ~5-8 дней, зависит от объёма"

    if any(w in lower for w in ("цен", "стоим", "сколько стоит", "прайс", "price")):
        return "уточни что именно нужно по задаче - цену скажу когда всё соберём"

    if any(w in lower for w in ("дрейнер", "drainer", "tron", "трон", "trc20", "trx")):
        return "да, под tron делаем, что по функционалу нужно - списание trx и trc20 или своя логика"

    if any(
        w in lower
        for w in ("пробив", "глаз бога", "глаз бог", "osint", "готовы", "готовое", "есть ли")
    ):
        return (
            "готового нету, сделаем telegram-бота под пробив и агрегацию данных "
            "с интеграцией нужных api-источников, утечек и парсеров, удобным поиском "
            "(по номеру, авто, соцсетям), админ-панелью и приемом платежей за пару дней"
        )

    if any(
        w in lower
        for w in (
            "софт",
            "утилита",
            "программ",
            "сделать",
            "напиши",
            "нужен",
            "редми",
            "redmi",
            "телефон",
            "android",
            "имя",
            "парсер",
            "бот",
        )
    ):
        return "да, сделаем, напиши детали задачи и модель устройства если важно"

    # Greeting ONLY when the whole focus is a short hello (task already handled above)
    if len(focus) <= 40 and any(w in lower for w in ("привет", "здравств", "hello", "hi", "ку", "хай")):
        return "привет, слушаю"

    return "напишите что нужно - сделаем под задачу"

