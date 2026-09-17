"""Provider adapters.

Every function here performs a real network call against the provider API.
Nothing is simulated: if a key is missing the provider is reported as
unconfigured rather than faked.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from app.config import get_settings

PROVIDERS = ("openai", "anthropic", "gemini")

# USD per 1M tokens. Used to price runs when the provider does not return cost.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
    "claude-3-5-haiku-latest": (0.80, 4.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}

CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "gpt-5": 400_000,
    "gpt-5-mini": 400_000,
    "claude-3-5-haiku-latest": 200_000,
    "claude-3-5-sonnet-latest": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "gemini-2.0-flash": 1_048_576,
    "gemini-1.5-pro": 2_097_152,
}


class ProviderError(RuntimeError):
    pass


def api_key_for(provider: str) -> str:
    s = get_settings()
    return {
        "openai": s.openai_api_key,
        "anthropic": s.anthropic_api_key,
        "gemini": s.google_api_key,
    }.get(provider, "")


def configured_providers() -> dict[str, bool]:
    return {p: bool(api_key_for(p)) for p in PROVIDERS}


def price_for(model_id: str) -> tuple[float, float]:
    if model_id in PRICING:
        return PRICING[model_id]
    for known, price in PRICING.items():
        if model_id.startswith(known.split("-latest")[0]):
            return price
    return (0.0, 0.0)


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = price_for(model_id)
    return round(input_tokens / 1_000_000 * inp + output_tokens / 1_000_000 * out, 6)


def approx_tokens(text: str) -> int:
    """Fallback counter for providers that omit usage on streamed responses."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.6))


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


async def discover_models(provider: str) -> list[dict[str, Any]]:
    key = api_key_for(provider)
    if not key:
        raise ProviderError(f"{provider}: API key is not configured")

    if provider == "openai":
        return await _discover_openai(key)
    if provider == "anthropic":
        return await _discover_anthropic(key)
    if provider == "gemini":
        return await _discover_gemini(key)
    raise ProviderError(f"unknown provider {provider}")


def _openai_base_url() -> str | None:
    """Normalize OPENAI_BASE_URL. Empty / api.openai.com → official API."""
    raw = (get_settings().openai_base_url or "").strip().rstrip("/")
    if not raw:
        return None
    # Common mistakes: "api.openai.com" without scheme / without /v1
    lowered = raw.lower().replace("https://", "").replace("http://", "")
    if lowered in ("api.openai.com", "api.openai.com/v1"):
        return None
    if not raw.startswith("http"):
        raw = "https://" + raw
    return raw


def _openai_client(key: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=key, base_url=_openai_base_url())


def _is_chat_model(model_id: str, custom_endpoint: bool) -> bool:
    if custom_endpoint:
        return True
    mid = model_id.lower()
    # Skip non-chat modalities
    skip = (
        "audio",
        "realtime",
        "transcribe",
        "tts",
        "whisper",
        "dall-e",
        "tts-",
        "embedding",
        "moderation",
        "image",
        "sora",
        "computer-use",
    )
    if any(x in mid for x in skip):
        return False
    prefixes = (
        "gpt-",
        "o1",
        "o3",
        "o4",
        "chatgpt-",
        "ft:gpt",
    )
    return mid.startswith(prefixes)


async def _discover_openai(key: str) -> list[dict[str, Any]]:
    custom = _openai_base_url() is not None
    client = _openai_client(key)
    page = await client.models.list()
    out: list[dict[str, Any]] = []
    for m in page.data:
        mid = m.id
        if not _is_chat_model(mid, custom):
            continue
        inp, outp = price_for(mid)
        out.append(
            {
                "model_id": mid,
                "display_name": mid,
                "context_window": CONTEXT_WINDOWS.get(mid),
                "input_cost_per_mtok": inp,
                "output_cost_per_mtok": outp,
                "supports_streaming": True,
            }
        )
    return sorted(out, key=lambda x: x["model_id"])


async def _discover_anthropic(key: str) -> list[dict[str, Any]]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=key)
    page = await client.models.list(limit=100)
    out = []
    for m in page.data:
        inp, outp = price_for(m.id)
        out.append(
            {
                "model_id": m.id,
                "display_name": getattr(m, "display_name", m.id),
                "context_window": CONTEXT_WINDOWS.get(m.id, 200_000),
                "input_cost_per_mtok": inp,
                "output_cost_per_mtok": outp,
                "supports_streaming": True,
            }
        )
    return out


async def _discover_gemini(key: str) -> list[dict[str, Any]]:
    import asyncio

    import google.generativeai as genai

    genai.configure(api_key=key)

    def _list():
        result = []
        for m in genai.list_models():
            if "generateContent" not in getattr(m, "supported_generation_methods", []):
                continue
            mid = m.name.replace("models/", "")
            inp, outp = price_for(mid)
            result.append(
                {
                    "model_id": mid,
                    "display_name": getattr(m, "display_name", mid),
                    "context_window": getattr(m, "input_token_limit", None),
                    "max_output_tokens": getattr(m, "output_token_limit", None),
                    "input_cost_per_mtok": inp,
                    "output_cost_per_mtok": outp,
                    "supports_streaming": True,
                }
            )
        return result

    return await asyncio.to_thread(_list)


# --------------------------------------------------------------------------
# Health check
# --------------------------------------------------------------------------


async def ping(provider: str, model_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        text = ""
        async for chunk in stream_chat(
            provider=provider,
            model_id=model_id,
            messages=[{"role": "user", "content": "ping"}],
            system="Reply with the single word: pong",
            temperature=0.0,
            max_tokens=8,
        ):
            if chunk["type"] == "delta":
                text += chunk["text"]
        return {
            "status": "ok",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "sample": text.strip()[:64],
        }
    except Exception as e:
        return {
            "status": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(e)[:300],
        }


# --------------------------------------------------------------------------
# Streaming chat
# --------------------------------------------------------------------------


async def stream_chat(
    provider: str,
    model_id: str,
    messages: list[dict[str, str]],
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncIterator[dict[str, Any]]:
    """Yield {'type': 'delta'|'usage', ...} events from a live provider stream."""
    key = api_key_for(provider)
    if not key:
        raise ProviderError(f"{provider}: API key is not configured")

    if provider == "openai":
        async for ev in _stream_openai(key, model_id, messages, system, temperature, max_tokens):
            yield ev
    elif provider == "anthropic":
        async for ev in _stream_anthropic(key, model_id, messages, system, temperature, max_tokens):
            yield ev
    elif provider == "gemini":
        async for ev in _stream_gemini(key, model_id, messages, system, temperature, max_tokens):
            yield ev
    else:
        raise ProviderError(f"unknown provider {provider}")


async def _stream_openai(key, model_id, messages, system, temperature, max_tokens):
    client = _openai_client(key)
    payload = ([{"role": "system", "content": system}] if system else []) + messages
    stream = await client.chat.completions.create(
        model=model_id,
        messages=payload,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )
    collected = ""
    usage_sent = False
    async for chunk in stream:
        if chunk.usage:
            usage_sent = True
            yield {
                "type": "usage",
                "input_tokens": chunk.usage.prompt_tokens,
                "output_tokens": chunk.usage.completion_tokens,
            }
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                collected += delta.content
                yield {"type": "delta", "text": delta.content}
    if not usage_sent:
        yield {
            "type": "usage",
            "input_tokens": approx_tokens(system + "".join(m["content"] for m in messages)),
            "output_tokens": approx_tokens(collected),
        }


async def _stream_anthropic(key, model_id, messages, system, temperature, max_tokens):
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=key)
    kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield {"type": "delta", "text": text}
        final = await stream.get_final_message()
        yield {
            "type": "usage",
            "input_tokens": final.usage.input_tokens,
            "output_tokens": final.usage.output_tokens,
        }


async def _stream_gemini(key, model_id, messages, system, temperature, max_tokens):
    import google.generativeai as genai

    genai.configure(api_key=key)
    kwargs: dict[str, Any] = {"model_name": model_id}
    if system:
        kwargs["system_instruction"] = system
    model = genai.GenerativeModel(**kwargs)

    history = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]}
        for m in messages
    ]
    response = await model.generate_content_async(
        history,
        generation_config=genai.GenerationConfig(
            temperature=temperature, max_output_tokens=max_tokens
        ),
        stream=True,
    )
    collected = ""
    usage = None
    async for chunk in response:
        if chunk.text:
            collected += chunk.text
            yield {"type": "delta", "text": chunk.text}
        if getattr(chunk, "usage_metadata", None):
            usage = chunk.usage_metadata
    if usage:
        yield {
            "type": "usage",
            "input_tokens": usage.prompt_token_count,
            "output_tokens": usage.candidates_token_count,
        }
    else:
        yield {
            "type": "usage",
            "input_tokens": approx_tokens(system + "".join(m["content"] for m in messages)),
            "output_tokens": approx_tokens(collected),
        }
