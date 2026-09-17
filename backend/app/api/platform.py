"""Platform API: models, threads, runs, traces and usage metrics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.db.platform_models import (
    ModelRecord,
    Run,
    RunStatus,
    Span,
    Thread,
    ThreadSource,
    Turn,
)
from app.services import inference, providers, registry

router = APIRouter()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ModelOut(BaseModel):
    id: int
    provider: str
    model_id: str
    display_name: str
    context_window: Optional[int] = None
    input_cost_per_mtok: float
    output_cost_per_mtok: float
    enabled: bool
    is_default: bool
    last_status: str
    last_latency_ms: Optional[int] = None
    last_checked_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ModelPatch(BaseModel):
    enabled: Optional[bool] = None


class PromptTurn(BaseModel):
    role: str  # user | assistant | system
    content: str


class ThreadCreate(BaseModel):
    title: str = ""
    provider: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: str = ""
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(1024, ge=1, le=32000)
    use_retrieval: bool = False
    initial_turns: list[PromptTurn] = []

    model_config = {"protected_namespaces": ()}


class ThreadPatch(BaseModel):
    title: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    use_retrieval: Optional[bool] = None

    model_config = {"protected_namespaces": ()}


class ThreadOut(BaseModel):
    id: str
    title: str
    source: str
    provider: Optional[str]
    model_id: Optional[str]
    system_prompt: str
    temperature: float
    max_tokens: int
    use_retrieval: bool
    total_runs: int
    total_tokens: int
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime

    model_config = {"protected_namespaces": ()}


class TurnOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ThreadDetail(ThreadOut):
    turns: list[TurnOut] = []


class RunRequest(BaseModel):
    content: str
    provider: Optional[str] = None
    model_id: Optional[str] = None

    model_config = {"protected_namespaces": ()}


class SpanOut(BaseModel):
    name: str
    kind: str
    status: str
    duration_ms: int
    attributes: dict[str, Any]


class RunOut(BaseModel):
    id: str
    thread_id: str
    provider: str
    model_id: str
    status: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    ttft_ms: Optional[int]
    error: Optional[str]
    prompt_preview: str
    output_preview: str
    created_at: datetime

    model_config = {"protected_namespaces": ()}


class RunDetail(RunOut):
    spans: list[SpanOut] = []


# --------------------------------------------------------------------------
# Providers & models
# --------------------------------------------------------------------------


@router.get("/providers")
async def list_providers(db: AsyncSession = Depends(get_db)):
    from app.config import get_settings

    s = get_settings()
    configured = providers.configured_providers()
    counts = dict(
        (row[0], row[1])
        for row in (
            await db.execute(
                select(ModelRecord.provider, func.count(ModelRecord.id)).group_by(ModelRecord.provider)
            )
        ).all()
    )
    openai_endpoint = "api.openai.com"
    from app.services.providers import _openai_base_url

    base = _openai_base_url()
    if base:
        if "127.0.0.1" in base or "localhost" in base:
            openai_endpoint = "local"
        else:
            openai_endpoint = base
    return [
        {
            "id": p,
            "configured": ok,
            "models": counts.get(p, 0),
            **(
                {"endpoint": openai_endpoint, "key_hint": "local" if s.openai_api_key == "local" else ("set" if ok else "missing")}
                if p == "openai"
                else {}
            ),
        }
        for p, ok in configured.items()
    ]


@router.get("/models", response_model=list[ModelOut])
async def list_models(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(ModelRecord).order_by(ModelRecord.provider, ModelRecord.model_id)
    if enabled_only:
        q = q.where(ModelRecord.enabled.is_(True))
    return (await db.execute(q)).scalars().all()


@router.post("/models/sync")
async def sync_models(db: AsyncSession = Depends(get_db)):
    results = await registry.sync_all(db)
    if all("error" in r or "skipped" in r for r in results):
        detail = "; ".join(
            f"{r['provider']}: {r.get('error') or r.get('skipped')}" for r in results
        )
        raise HTTPException(400, f"No models synced. {detail}")
    return {"results": results}


@router.patch("/models/{record_id}", response_model=ModelOut)
async def patch_model(record_id: int, body: ModelPatch, db: AsyncSession = Depends(get_db)):
    record = await db.get(ModelRecord, record_id)
    if not record:
        raise HTTPException(404, "model not found")
    if body.enabled is not None:
        record.enabled = body.enabled
        if not body.enabled and record.is_default:
            record.is_default = False
    await db.flush()
    return record


@router.post("/models/{record_id}/default", response_model=ModelOut)
async def make_default(record_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await registry.set_default(db, record_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/models/{record_id}/check", response_model=ModelOut)
async def check_model(record_id: int, db: AsyncSession = Depends(get_db)):
    try:
        return await registry.check_model(db, record_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


# --------------------------------------------------------------------------
# Threads
# --------------------------------------------------------------------------


def _thread_out(t: Thread) -> ThreadOut:
    return ThreadOut(
        id=t.external_id,
        title=t.title,
        source=t.source.value,
        provider=t.provider,
        model_id=t.model_id,
        system_prompt=t.system_prompt,
        temperature=t.temperature,
        max_tokens=t.max_tokens,
        use_retrieval=t.use_retrieval,
        total_runs=t.total_runs,
        total_tokens=t.total_tokens,
        total_cost_usd=t.total_cost_usd,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    limit: int = Query(50, le=200),
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Thread).where(Thread.archived.is_(False)).order_by(Thread.updated_at.desc()).limit(limit)
    if source:
        q = q.where(Thread.source == ThreadSource(source))
    return [_thread_out(t) for t in (await db.execute(q)).scalars().all()]


@router.post("/threads", response_model=ThreadOut)
async def create_thread(body: ThreadCreate, db: AsyncSession = Depends(get_db)):
    thread = await inference.create_thread(
        db,
        title=body.title,
        provider=body.provider,
        model_id=body.model_id,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        use_retrieval=body.use_retrieval,
        initial_turns=[t.model_dump() for t in body.initial_turns],
    )
    return _thread_out(thread)


@router.post("/threads/{thread_id}/turns", response_model=list[TurnOut])
async def seed_turns(thread_id: str, body: list[PromptTurn], db: AsyncSession = Depends(get_db)):
    try:
        rows = await inference.add_turns(db, thread_id, [t.model_dump() for t in body])
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return [TurnOut(id=t.id, role=t.role, content=t.content, created_at=t.created_at) for t in rows]


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Thread).options(selectinload(Thread.turns)).where(Thread.external_id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(404, "thread not found")
    base = _thread_out(thread)
    return ThreadDetail(
        **base.model_dump(),
        turns=[
            TurnOut(id=t.id, role=t.role, content=t.content, created_at=t.created_at)
            for t in thread.turns
        ],
    )


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def patch_thread(thread_id: str, body: ThreadPatch, db: AsyncSession = Depends(get_db)):
    thread = await inference.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(404, "thread not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(thread, field, value)
    await db.flush()
    return _thread_out(thread)


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    thread = await inference.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(404, "thread not found")
    await db.delete(thread)
    return {"deleted": thread_id}


@router.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, body: RunRequest):
    """Stream a real completion. Every token comes from the provider."""
    generator = inference.stream_run(
        thread_id,
        body.content,
        provider_override=body.provider,
        model_override=body.model_id,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# Runs & traces
# --------------------------------------------------------------------------


def _run_out(r: Run, thread_ext: str) -> RunOut:
    return RunOut(
        id=r.external_id,
        thread_id=thread_ext,
        provider=r.provider,
        model_id=r.model_id,
        status=r.status.value,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        cost_usd=r.cost_usd,
        latency_ms=r.latency_ms,
        ttft_ms=r.ttft_ms,
        error=r.error,
        prompt_preview=r.prompt_preview,
        output_preview=r.output_preview,
        created_at=r.created_at,
    )


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    limit: int = Query(100, le=500),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Run, Thread.external_id)
        .join(Thread, Thread.id == Run.thread_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(Run.status == RunStatus(status))
    return [_run_out(r, ext) for r, ext in (await db.execute(q)).all()]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Run, Thread.external_id)
        .options(selectinload(Run.spans))
        .join(Thread, Thread.id == Run.thread_id)
        .where(Run.external_id == run_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(404, "run not found")
    run, thread_ext = row
    base = _run_out(run, thread_ext)
    return RunDetail(
        **base.model_dump(),
        spans=[
            SpanOut(
                name=s.name,
                kind=s.kind.value,
                status=s.status,
                duration_ms=s.duration_ms,
                attributes=s.attributes or {},
            )
            for s in run.spans
        ],
    )


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


@router.get("/metrics")
async def metrics(hours: int = Query(24, le=720), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    total_runs = await db.scalar(select(func.count(Run.id)).where(Run.created_at >= since)) or 0
    failed = (
        await db.scalar(
            select(func.count(Run.id)).where(Run.created_at >= since, Run.status == RunStatus.FAILED)
        )
        or 0
    )
    tokens_in = (
        await db.scalar(
            select(func.coalesce(func.sum(Run.input_tokens), 0)).where(Run.created_at >= since)
        )
        or 0
    )
    tokens_out = (
        await db.scalar(
            select(func.coalesce(func.sum(Run.output_tokens), 0)).where(Run.created_at >= since)
        )
        or 0
    )
    cost = (
        await db.scalar(
            select(func.coalesce(func.sum(Run.cost_usd), 0.0)).where(Run.created_at >= since)
        )
        or 0.0
    )
    threads_total = await db.scalar(select(func.count(Thread.id))) or 0

    latencies = [
        row[0]
        for row in (
            await db.execute(
                select(Run.latency_ms)
                .where(Run.created_at >= since, Run.status == RunStatus.COMPLETED)
                .order_by(Run.latency_ms)
            )
        ).all()
    ]

    def pct(p: float) -> int:
        if not latencies:
            return 0
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return int(latencies[idx])

    by_model = [
        {
            "provider": row[0],
            "model_id": row[1],
            "runs": row[2],
            "tokens": int(row[3] or 0),
            "cost_usd": round(float(row[4] or 0), 6),
            "avg_latency_ms": int(row[5] or 0),
        }
        for row in (
            await db.execute(
                select(
                    Run.provider,
                    Run.model_id,
                    func.count(Run.id),
                    func.sum(Run.input_tokens + Run.output_tokens),
                    func.sum(Run.cost_usd),
                    func.avg(Run.latency_ms),
                )
                .where(Run.created_at >= since)
                .group_by(Run.provider, Run.model_id)
                .order_by(func.count(Run.id).desc())
            )
        ).all()
    ]

    return {
        "window_hours": hours,
        "runs": total_runs,
        "failed": failed,
        "success_rate": round((total_runs - failed) / total_runs, 4) if total_runs else None,
        "input_tokens": int(tokens_in),
        "output_tokens": int(tokens_out),
        "cost_usd": round(float(cost), 6),
        "threads": threads_total,
        "latency_p50_ms": pct(0.50),
        "latency_p95_ms": pct(0.95),
        "by_model": by_model,
    }


@router.get("/usage/series")
async def usage_series(
    hours: int = Query(168, le=2160),
    buckets: int = Query(24, ge=4, le=96),
    db: AsyncSession = Depends(get_db),
):
    """Bucketed run counts and token totals for the dashboard charts."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    width = timedelta(hours=hours) / buckets

    rows = (
        await db.execute(
            select(Run.created_at, Run.input_tokens, Run.output_tokens, Run.status)
            .where(Run.created_at >= since)
            .order_by(Run.created_at)
        )
    ).all()

    series = [
        {
            "t": (since + width * i).isoformat(),
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "failed": 0,
        }
        for i in range(buckets)
    ]

    for created_at, tin, tout, status in rows:
        created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        idx = int((created - since) / width)
        idx = max(0, min(buckets - 1, idx))
        series[idx]["requests"] += 1
        series[idx]["input_tokens"] += tin or 0
        series[idx]["output_tokens"] += tout or 0
        if status == RunStatus.FAILED:
            series[idx]["failed"] += 1

    return {"window_hours": hours, "buckets": buckets, "series": series}


@router.get("/activity")
async def activity(limit: int = Query(120, le=500), db: AsyncSession = Depends(get_db)):
    """Raw run timeline used by the thread visualisation. No synthetic points."""
    rows = (
        await db.execute(
            select(
                Run.external_id,
                Run.provider,
                Run.model_id,
                Run.status,
                Run.latency_ms,
                Run.input_tokens,
                Run.output_tokens,
                Run.created_at,
                Thread.external_id,
                Thread.title,
                Thread.source,
            )
            .join(Thread, Thread.id == Run.thread_id)
            .order_by(Run.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "run_id": r[0],
            "provider": r[1],
            "model_id": r[2],
            "status": r[3].value,
            "latency_ms": r[4],
            "tokens": (r[5] or 0) + (r[6] or 0),
            "created_at": r[7],
            "thread_id": r[8],
            "thread_title": r[9],
            "source": r[10].value,
        }
        for r in rows
    ]
