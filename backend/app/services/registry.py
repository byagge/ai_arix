"""Model registry: keeps the local catalogue in sync with provider APIs."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.platform_models import ModelRecord
from app.services import providers


async def sync_provider(db: AsyncSession, provider: str) -> dict:
    """Pull the live model list for one provider and upsert it."""
    discovered = await providers.discover_models(provider)
    existing = {
        r.model_id: r
        for r in (await db.execute(select(ModelRecord).where(ModelRecord.provider == provider)))
        .scalars()
        .all()
    }

    seen = {item["model_id"] for item in discovered}
    added = 0
    disabled = 0
    for item in discovered:
        record = existing.get(item["model_id"])
        if record is None:
            record = ModelRecord(provider=provider, model_id=item["model_id"])
            db.add(record)
            added += 1
        record.display_name = item.get("display_name") or item["model_id"]
        record.context_window = item.get("context_window")
        record.max_output_tokens = item.get("max_output_tokens")
        record.input_cost_per_mtok = item.get("input_cost_per_mtok", 0.0)
        record.output_cost_per_mtok = item.get("output_cost_per_mtok", 0.0)
        record.supports_streaming = item.get("supports_streaming", True)
        record.enabled = True
        record.last_checked_at = datetime.now(timezone.utc)
        record.last_status = "ok"

    # Drop stale mock / removed models (e.g. local-echo-* after switching to real OpenAI)
    official_openai = provider == "openai" and providers._openai_base_url() is None
    for mid, record in existing.items():
        if mid in seen:
            continue
        if mid.startswith("local-echo") or official_openai:
            await db.delete(record)
            disabled += 1
        else:
            record.enabled = False
            record.is_default = False
            disabled += 1

    await db.flush()
    return {"provider": provider, "discovered": len(discovered), "added": added, "removed_or_disabled": disabled}


async def sync_all(db: AsyncSession) -> list[dict]:
    results = []
    for provider, configured in providers.configured_providers().items():
        if not configured:
            results.append({"provider": provider, "skipped": "no api key"})
            continue
        try:
            results.append(await sync_provider(db, provider))
        except Exception as e:
            results.append({"provider": provider, "error": str(e)[:200]})
    await _ensure_default(db)
    return results


async def _ensure_default(db: AsyncSession) -> None:
    has_default = await db.scalar(
        select(ModelRecord.id).where(ModelRecord.is_default.is_(True), ModelRecord.enabled.is_(True))
    )
    if has_default:
        return
    first = (
        await db.execute(select(ModelRecord).where(ModelRecord.enabled.is_(True)).order_by(ModelRecord.id))
    ).scalars().first()
    if first:
        first.is_default = True
        await db.flush()


async def set_default(db: AsyncSession, record_id: int) -> ModelRecord:
    records = (await db.execute(select(ModelRecord))).scalars().all()
    target = None
    for r in records:
        r.is_default = r.id == record_id
        if r.id == record_id:
            target = r
    if target is None:
        raise ValueError("model not found")
    target.enabled = True
    await db.flush()
    return target


async def check_model(db: AsyncSession, record_id: int) -> ModelRecord:
    record = await db.get(ModelRecord, record_id)
    if record is None:
        raise ValueError("model not found")
    result = await providers.ping(record.provider, record.model_id)
    record.last_checked_at = datetime.now(timezone.utc)
    record.last_status = result["status"]
    record.last_latency_ms = result.get("latency_ms")
    record.metadata_json = {**(record.metadata_json or {}), "last_check": result}
    await db.flush()
    return record
