"""A minimal OpenAI-compatible server for local development.

Not a real LLM: returns deterministic sales-style replies so Telegram + panel
can be exercised end-to-end without paid keys.

    python tools/local_provider.py            # listens on 127.0.0.1:8800

Then in .env:
    OPENAI_API_KEY=local
    OPENAI_BASE_URL=http://127.0.0.1:8800/v1
    LLM_PRIMARY=openai
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI(title="Local OpenAI-compatible provider")

MODELS = [
    {"id": "local-echo-small", "object": "model", "owned_by": "local"},
    {"id": "local-echo-large", "object": "model", "owned_by": "local"},
    {"id": "gpt-4o-mini", "object": "model", "owned_by": "local"},
]


def _craft_reply(prompt: str, system: str) -> str:
    lower = (prompt or "").lower()
    sys_l = (system or "").lower()
    if "json" in sys_l or "respond only with valid json" in lower or "только json" in lower:
        # Orchestrator / extractor shapes
        if "amount_usdt" in lower or "wants_escrow" in lower:
            return json.dumps(
                {
                    "amount_usdt": 0,
                    "description": "Заказ",
                    "wants_escrow": "гарант" in lower or "escrow" in lower,
                    "wants_direct": "usdt" in lower or "trc" in lower,
                    "ready": any(w in lower for w in ("оплат", "беру", "купить", "готов")),
                },
                ensure_ascii=False,
            )
        target = "sales"
        if any(w in lower for w in ("оплат", "usdt", "гарант", "купить", "цен")):
            target = "payment"
        return json.dumps(
            {
                "funnel_stage": "consultation",
                "intent": "payment" if target == "payment" else "consultation",
                "target_agent": target,
                "should_respond": True,
                "reasoning": "local provider",
                "urgency": "medium",
                "ready_for_payment": target == "payment",
                "extracted_amount": None,
                "extracted_product": None,
            },
            ensure_ascii=False,
        )
    if any(w in lower for w in ("гарант", "escrow", "безопасн")):
        return "да, можно через гаранта, напишите что по задаче"
    if any(w in lower for w in ("оплат", "usdt", "цен", "сколько", "купить", "trc")):
        return "уточни что именно нужно по задаче - цену скажу когда всё соберём"
    if any(w in lower for w in ("привет", "здравств", "hello", "hi")):
        return "привет, слушаю"
    # Prefer last "Клиент:" line if present
    m = re.search(r"Клиент:\s*(.+)$", prompt or "", re.M)
    hint = (m.group(1).strip()[:80] if m else "").strip()
    if hint:
        return "да, сделаем, напиши детали задачи"
    return "напишите что нужно - сделаем под задачу"


@app.get("/v1/models")
async def list_models():
    return {"object": "list", "data": MODELS}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "local-echo-small")
    messages = body.get("messages", [])
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    prompt = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")

    reply = _craft_reply(prompt, system)
    words = reply.split(" ")
    created = int(time.time())
    cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    if not body.get("stream"):
        return {
            "id": cid,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(words),
                "total_tokens": len(prompt.split()) + len(words),
            },
        }

    async def gen():
        for i, word in enumerate(words):
            chunk = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "delta": {"content": (" " if i else "") + word}, "finish_reason": None}
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.03)

        yield f"data: {json.dumps({'id': cid, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
        yield (
            "data: "
            + json.dumps(
                {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": len(words),
                        "total_tokens": len(prompt.split()) + len(words),
                    },
                }
            )
            + "\n\n"
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8800, log_level="warning")
