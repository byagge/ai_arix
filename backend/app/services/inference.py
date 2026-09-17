"""Execution engine.

A run is created when a caller actually asks a model for a completion. Spans
record how long each step really took; token counts come from the provider
response whenever the provider reports them.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.db.platform_models import (
    ModelRecord,
    Run,
    RunStatus,
    Span,
    SpanKind,
    Thread,
    ThreadSource,
    Turn,
)
from app.services import providers
from app.services.event_bus import publish_event


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


async def resolve_default_model(db: AsyncSession) -> Optional[ModelRecord]:
    result = await db.execute(
        select(ModelRecord).where(ModelRecord.is_default.is_(True), ModelRecord.enabled.is_(True))
    )
    record = result.scalar_one_or_none()
    if record:
        return record
    result = await db.execute(
        select(ModelRecord).where(ModelRecord.enabled.is_(True)).order_by(ModelRecord.id)
    )
    return result.scalars().first()


async def create_thread(
    db: AsyncSession,
    *,
    title: str = "",
    source: ThreadSource = ThreadSource.PLAYGROUND,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    use_retrieval: bool = False,
    dialog_id: Optional[int] = None,
    initial_turns: Optional[list[dict[str, str]]] = None,
) -> Thread:
    if not provider or not model_id:
        default = await resolve_default_model(db)
        if default:
            provider = provider or default.provider
            model_id = model_id or default.model_id

    thread = Thread(
        external_id=new_id("thread"),
        title=title or "Untitled thread",
        source=source,
        provider=provider,
        model_id=model_id,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        use_retrieval=use_retrieval,
        dialog_id=dialog_id,
    )
    db.add(thread)
    await db.flush()

    for turn in initial_turns or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant", "system") and content:
            db.add(Turn(thread_id=thread.id, role=role, content=content))
    await db.flush()

    await publish_event(
        "platform",
        {"event": "thread.created", "thread_id": thread.external_id, "source": source.value},
    )
    return thread


async def add_turns(
    db: AsyncSession,
    thread_external_id: str,
    turns: list[dict[str, str]],
) -> list[Turn]:
    thread = await get_thread(db, thread_external_id)
    if thread is None:
        raise ValueError("thread not found")
    created: list[Turn] = []
    for turn in turns:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant", "system") or not content:
            continue
        row = Turn(thread_id=thread.id, role=role, content=content)
        db.add(row)
        created.append(row)
    await db.flush()
    return created


async def get_thread(db: AsyncSession, external_id: str) -> Optional[Thread]:
    result = await db.execute(select(Thread).where(Thread.external_id == external_id))
    return result.scalar_one_or_none()


async def _history(db: AsyncSession, thread_id: int, limit: int = 40) -> list[dict[str, str]]:
    result = await db.execute(
        select(Turn).where(Turn.thread_id == thread_id).order_by(Turn.id.asc())
    )
    turns = list(result.scalars().all())[-limit:]
    return [{"role": t.role, "content": t.content} for t in turns if t.role in ("user", "assistant")]


class RunRecorder:
    """Collects span timings for a single run."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []

    def span(self, name: str, kind: SpanKind):
        return _SpanCtx(self, name, kind)

    def add(self, name: str, kind: SpanKind, duration_ms: int, status: str, attributes: dict) -> None:
        self.spans.append(
            {
                "name": name,
                "kind": kind,
                "duration_ms": duration_ms,
                "status": status,
                "attributes": attributes,
            }
        )


class _SpanCtx:
    def __init__(self, recorder: RunRecorder, name: str, kind: SpanKind):
        self.recorder = recorder
        self.name = name
        self.kind = kind
        self.attributes: dict[str, Any] = {}
        self.status = "ok"
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        duration = int((time.perf_counter() - self._t0) * 1000)
        if exc is not None:
            self.status = "error"
            self.attributes["error"] = str(exc)[:300]
        self.recorder.add(self.name, self.kind, duration, self.status, self.attributes)
        return False


async def stream_run(
    thread_external_id: str,
    user_message: str,
    *,
    provider_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> AsyncIterator[str]:
    """Execute a run and yield server-sent events as the provider streams."""
    run_external_id = new_id("run")
    started = time.perf_counter()
    recorder = RunRecorder()
    collected = ""
    ttft_ms: Optional[int] = None
    usage = {"input_tokens": 0, "output_tokens": 0}
    error: Optional[str] = None

    async with async_session() as db:
        thread = await get_thread(db, thread_external_id)
        if thread is None:
            yield _sse("error", {"message": "thread not found"})
            return

        provider = provider_override or thread.provider
        model_id = model_override or thread.model_id
        if not provider or not model_id:
            yield _sse("error", {"message": "no model selected for this thread"})
            return

        # Read history before the new turn is stored, otherwise the prompt
        # would be sent twice.
        history = await _history(db, thread.id)

        db.add(Turn(thread_id=thread.id, role="user", content=user_message))
        if thread.title in ("", "Untitled thread"):
            thread.title = user_message.strip()[:80]

        run = Run(
            external_id=run_external_id,
            thread_id=thread.id,
            provider=provider,
            model_id=model_id,
            status=RunStatus.RUNNING,
            prompt_preview=user_message[:400],
        )
        db.add(run)
        await db.flush()
        run_db_id = run.id
        thread_db_id = thread.id
        system_prompt = thread.system_prompt
        temperature = thread.temperature
        max_tokens = thread.max_tokens
        use_retrieval = thread.use_retrieval
        await db.commit()

    await publish_event(
        "platform",
        {
            "event": "run.started",
            "run_id": run_external_id,
            "thread_id": thread_external_id,
            "provider": provider,
            "model": model_id,
        },
    )
    yield _sse("run.started", {"run_id": run_external_id, "provider": provider, "model": model_id})

    retrieved = ""
    if use_retrieval:
        with recorder.span("retrieval", SpanKind.RETRIEVAL) as sp:
            from app.rag.retriever import retrieve_context

            retrieved = await retrieve_context(user_message)
            sp.attributes["chars"] = len(retrieved)
        yield _sse("span", {"name": "retrieval", "chars": len(retrieved)})

    system = system_prompt
    if retrieved:
        system = (system + "\n\nContext:\n" + retrieved).strip()

    messages = history + [{"role": "user", "content": user_message}]

    llm_t0 = time.perf_counter()
    try:
        async for chunk in providers.stream_chat(
            provider=provider,
            model_id=model_id,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk["type"] == "delta":
                if ttft_ms is None:
                    ttft_ms = int((time.perf_counter() - llm_t0) * 1000)
                    yield _sse("ttft", {"ms": ttft_ms})
                collected += chunk["text"]
                yield _sse("delta", {"text": chunk["text"]})
            elif chunk["type"] == "usage":
                usage["input_tokens"] = chunk.get("input_tokens", 0)
                usage["output_tokens"] = chunk.get("output_tokens", 0)
    except Exception as e:
        error = str(e)[:500]

    llm_ms = int((time.perf_counter() - llm_t0) * 1000)
    recorder.add(
        f"{provider}.chat",
        SpanKind.LLM,
        llm_ms,
        "error" if error else "ok",
        {
            "model": model_id,
            "ttft_ms": ttft_ms,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            **({"error": error} if error else {}),
        },
    )

    total_ms = int((time.perf_counter() - started) * 1000)
    cost = providers.estimate_cost(model_id, usage["input_tokens"], usage["output_tokens"])

    async with async_session() as db:
        run = await db.get(Run, run_db_id)
        thread = await db.get(Thread, thread_db_id)
        if run:
            run.status = RunStatus.FAILED if error else RunStatus.COMPLETED
            run.error = error
            run.input_tokens = usage["input_tokens"]
            run.output_tokens = usage["output_tokens"]
            run.cost_usd = cost
            run.latency_ms = total_ms
            run.ttft_ms = ttft_ms
            run.output_preview = collected[:400]
            run.finished_at = datetime.now(timezone.utc)
            for s in recorder.spans:
                db.add(
                    Span(
                        run_id=run.id,
                        name=s["name"],
                        kind=s["kind"],
                        status=s["status"],
                        duration_ms=s["duration_ms"],
                        attributes=s["attributes"],
                    )
                )
        if thread:
            if collected:
                db.add(
                    Turn(
                        thread_id=thread.id,
                        run_id=run_db_id,
                        role="assistant",
                        content=collected,
                    )
                )
            thread.total_runs += 1
            thread.total_tokens += usage["input_tokens"] + usage["output_tokens"]
            thread.total_cost_usd = round(thread.total_cost_usd + cost, 6)
        await db.commit()

    await publish_event(
        "platform",
        {
            "event": "run.failed" if error else "run.completed",
            "run_id": run_external_id,
            "thread_id": thread_external_id,
            "provider": provider,
            "model": model_id,
            "latency_ms": total_ms,
            "tokens": usage["input_tokens"] + usage["output_tokens"],
        },
    )

    if error:
        yield _sse("error", {"message": error})
    yield _sse(
        "run.completed",
        {
            "run_id": run_external_id,
            "status": "failed" if error else "completed",
            "latency_ms": total_ms,
            "ttft_ms": ttft_ms,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "cost_usd": cost,
            "spans": [
                {"name": s["name"], "kind": s["kind"].value, "duration_ms": s["duration_ms"]}
                for s in recorder.spans
            ],
        },
    )
    yield "data: [DONE]\n\n"


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"data: {json.dumps({'event': event, **payload}, ensure_ascii=False)}\n\n"


async def thread_for_dialog(
    db: AsyncSession,
    dialog_id: int,
    title: str,
    provider: Optional[str],
    model_id: Optional[str],
) -> Thread:
    result = await db.execute(select(Thread).where(Thread.dialog_id == dialog_id))
    thread = result.scalar_one_or_none()
    if thread:
        return thread
    return await create_thread(
        db,
        title=title,
        source=ThreadSource.TELEGRAM,
        provider=provider,
        model_id=model_id,
        dialog_id=dialog_id,
    )


async def record_agent_run(
    db: AsyncSession,
    *,
    dialog_id: int,
    title: str,
    provider: str,
    model_id: str,
    prompt: str,
    output: str,
    latency_ms: int,
    spans: list[dict[str, Any]],
    error: Optional[str] = None,
) -> None:
    """Persist a run produced by the Telegram agent pipeline."""
    thread = await thread_for_dialog(db, dialog_id, title, provider, model_id)

    input_tokens = providers.approx_tokens(prompt)
    output_tokens = providers.approx_tokens(output)
    cost = providers.estimate_cost(model_id, input_tokens, output_tokens)

    run = Run(
        external_id=new_id("run"),
        thread_id=thread.id,
        provider=provider,
        model_id=model_id,
        status=RunStatus.FAILED if error else RunStatus.COMPLETED,
        streamed=False,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        error=error,
        prompt_preview=prompt[:400],
        output_preview=output[:400],
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    for s in spans:
        db.add(
            Span(
                run_id=run.id,
                name=s["name"],
                kind=s.get("kind", SpanKind.ROUTER),
                status=s.get("status", "ok"),
                duration_ms=s.get("duration_ms", 0),
                attributes=s.get("attributes", {}),
            )
        )

    db.add(Turn(thread_id=thread.id, role="user", content=prompt))
    if output:
        db.add(Turn(thread_id=thread.id, run_id=run.id, role="assistant", content=output))

    thread.total_runs += 1
    thread.total_tokens += input_tokens + output_tokens
    thread.total_cost_usd = round(thread.total_cost_usd + cost, 6)
    await db.flush()

    await publish_event(
        "platform",
        {
            "event": "run.completed",
            "run_id": run.external_id,
            "thread_id": thread.external_id,
            "provider": provider,
            "model": model_id,
            "latency_ms": latency_ms,
        },
    )
