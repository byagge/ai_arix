from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.db.bot_extensions import FollowupMode, WorkStatus
from app.db.models import AgentEvent, Dialog, FunnelStage, KnowledgeDocument, Message, MessageRole, Order, PaymentStatus
from app.models.schemas import (
    AgentEventOut,
    AgentGraphOut,
    AgentSettingsOut,
    AgentSettingsUpdate,
    DashboardStats,
    DialogOut,
    DialogToggleAI,
    GraphEdge,
    GraphNode,
    KnowledgeDocOut,
    OrderOut,
    SendMessageRequest,
)
from app.services.dialog_finance import (
    dialog_finance,
    last_followup_at,
    list_dialog_ledger,
    list_dialog_orders,
    serialize_dialog_card,
    serialize_ledger,
    serialize_message,
    serialize_order,
)
from app.services.dialog_service import get_dialog_detail, get_dialogs, get_or_create_settings, resolve_chat_id
from app.rag.indexer import delete_document_vectors, index_document, save_upload
from app.telegram.client import send_telegram_message
from app.payments.escrow import list_escrow_drafts

router = APIRouter()


class FollowupPatch(BaseModel):
    followup_mode: str | None = None
    next_followup_at: datetime | None = None
    custom_followup_at: datetime | None = None
    disable: bool | None = None


class QuotePatch(BaseModel):
    quoted_price_usd: float | None = None
    quoted_price_max_usd: float | None = None
    quoted_days: int | None = None
    tz_summary: str | None = None
    admin_task_summary: str | None = None
    client_offer_pitch: str | None = None
    work_status: str | None = None
    funnel_stage: str | None = None
    price_approved: bool | None = None
    send_offer: bool | None = None


@router.get("/escrow/drafts")
async def escrow_drafts():
    return await list_escrow_drafts()


@router.get("/health-detail")
async def health_detail():
    from app.config import get_settings
    s = get_settings()
    return {
        "status": "ok",
        "llm_primary": s.llm_primary,
        "has_gemini": bool(s.google_api_key),
        "has_openai": bool(s.openai_api_key),
        "has_anthropic": bool(s.anthropic_api_key),
        "has_telegram": bool(s.telegram_bot_token),
        "admin_id": s.telegram_admin_id,
        "database": "sqlite" if "sqlite" in s.database_url else "postgres",
    }


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count(Dialog.id))) or 0
    active = await db.scalar(
        select(func.count(Dialog.id)).where(Dialog.last_message_at.isnot(None))
    ) or 0
    paid = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.CONFIRMED)
    ) or 0
    pending = await db.scalar(
        select(func.coalesce(func.sum(Order.amount_usdt), 0)).where(
            Order.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.CONFIRMING])
        )
    ) or 0
    revenue = await db.scalar(
        select(func.coalesce(func.sum(Order.amount_usdt), 0)).where(
            Order.payment_status == PaymentStatus.CONFIRMED
        )
    ) or 0
    ai_active = await db.scalar(select(func.count(Dialog.id)).where(Dialog.ai_active.is_(True))) or 0
    manual = total - ai_active
    docs = await db.scalar(select(func.count(KnowledgeDocument.id))) or 0
    return DashboardStats(
        total_dialogs=total,
        active_dialogs=active,
        paid_orders=paid,
        pending_payments=float(pending),
        total_revenue=float(revenue),
        ai_active_dialogs=ai_active,
        manual_dialogs=manual,
        knowledge_docs=docs,
    )


@router.get("/graph", response_model=AgentGraphOut)
async def agent_graph(db: AsyncSession = Depends(get_db)):
    recent = await db.execute(
        select(AgentEvent).order_by(AgentEvent.created_at.desc()).limit(20)
    )
    events = recent.scalars().all()
    active = list({e.agent_name for e in events[:5]})

    nodes = [
        GraphNode(id="telegram", label="Telegram", type="input", status="active", x=0, y=0),
        GraphNode(id="orchestrator", label="Orchestrator", type="core", status="active" if "orchestrator" in active else "idle", x=200, y=0),
        GraphNode(id="sales", label="Sales Agent", type="agent", status="active" if "sales" in active else "idle", x=400, y=-80),
        GraphNode(id="followup", label="Follow-Up", type="agent", status="active" if "followup" in active else "idle", x=400, y=0),
        GraphNode(id="payment", label="Payment", type="agent", status="active" if "payment" in active else "idle", x=400, y=80),
        GraphNode(id="rag", label="Knowledge RAG", type="data", status="idle", x=200, y=120),
        GraphNode(id="tron", label="Tron USDT", type="blockchain", status="idle", x=600, y=40),
        GraphNode(id="escrow", label="Escrow", type="blockchain", status="idle", x=600, y=-40),
    ]
    edges = [
        GraphEdge(id="e1", source="telegram", target="orchestrator", active=True),
        GraphEdge(id="e2", source="orchestrator", target="sales", active="sales" in active),
        GraphEdge(id="e3", source="orchestrator", target="followup", active="followup" in active),
        GraphEdge(id="e4", source="orchestrator", target="payment", active="payment" in active),
        GraphEdge(id="e5", source="sales", target="rag", active="sales" in active),
        GraphEdge(id="e6", source="payment", target="tron", active="payment" in active),
        GraphEdge(id="e7", source="payment", target="escrow", active="payment" in active),
    ]
    return AgentGraphOut(nodes=nodes, edges=edges, active_agents=active)


@router.get("/events", response_model=list[AgentEventOut])
async def list_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentEvent).order_by(AgentEvent.created_at.desc()).limit(limit))
    return result.scalars().all()


@router.get("/dialogs")
async def list_dialogs(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)):
    rows = await get_dialogs(db, limit, offset)
    return [
        serialize_dialog_card(
            r["dialog"],
            message_count=r["message_count"],
            preview=r["last_message_preview"],
        )
        for r in rows
    ]


@router.get("/dialogs/{dialog_id}")
async def get_dialog(dialog_id: int, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    card = serialize_dialog_card(dialog, message_count=len(dialog.messages))
    finance = await dialog_finance(db, dialog_id)
    orders = [serialize_order(o) for o in await list_dialog_orders(db, dialog_id)]
    ledger = [serialize_ledger(e) for e in await list_dialog_ledger(db, dialog_id)]
    return {
        **card,
        "last_followup_at": await last_followup_at(db, dialog_id),
        "finance": finance,
        "orders": orders,
        "ledger": ledger,
        "messages": [
            serialize_message(m)
            for m in sorted(dialog.messages, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc))
        ],
    }


@router.get("/dialogs/{dialog_id}/finance")
async def get_dialog_finance(dialog_id: int, db: AsyncSession = Depends(get_db)):
    dialog = await db.get(Dialog, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    return await dialog_finance(db, dialog_id)


@router.get("/dialogs/{dialog_id}/orders")
async def get_dialog_orders(dialog_id: int, db: AsyncSession = Depends(get_db)):
    dialog = await db.get(Dialog, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    return [serialize_order(o) for o in await list_dialog_orders(db, dialog_id)]


@router.patch("/dialogs/{dialog_id}/work-status")
async def set_work_status(
    dialog_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Admin: set client work status (lead → in_progress → completed)."""
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    status = body.get("work_status")
    if status not in {s.value for s in WorkStatus}:
        raise HTTPException(400, f"Invalid work_status: {status}")
    dialog.work_status = status
    if status == WorkStatus.COMPLETED.value:
        dialog.silent_until_completed = False
        dialog.followup_mode = FollowupMode.STANDARD.value
    elif status in (WorkStatus.IN_PROGRESS.value, WorkStatus.PAID.value):
        dialog.silent_until_completed = True
        dialog.followup_mode = FollowupMode.NONE.value
    await db.flush()
    return {"ok": True, "work_status": status}


@router.patch("/dialogs/{dialog_id}/followup")
async def patch_followup(dialog_id: int, body: FollowupPatch, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    if body.disable:
        dialog.followup_mode = FollowupMode.NONE.value
        dialog.next_followup_at = None
        dialog.custom_followup_at = None
    else:
        if body.followup_mode is not None:
            valid = {m.value for m in FollowupMode}
            if body.followup_mode not in valid:
                raise HTTPException(400, f"Invalid followup_mode: {body.followup_mode}")
            dialog.followup_mode = body.followup_mode
            if body.followup_mode == FollowupMode.NONE.value:
                dialog.next_followup_at = None
        if body.next_followup_at is not None:
            dialog.next_followup_at = body.next_followup_at
        if body.custom_followup_at is not None:
            dialog.custom_followup_at = body.custom_followup_at
            dialog.followup_mode = FollowupMode.CUSTOM.value
            dialog.next_followup_at = body.custom_followup_at
    await db.flush()
    return serialize_dialog_card(dialog, message_count=len(dialog.messages or []))


@router.patch("/dialogs/{dialog_id}/quote")
async def patch_quote(dialog_id: int, body: QuotePatch, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    data = body.model_dump(exclude_unset=True)
    if "work_status" in data and data["work_status"] is not None:
        if data["work_status"] not in {s.value for s in WorkStatus}:
            raise HTTPException(400, "Invalid work_status")
        dialog.work_status = data["work_status"]
    if "funnel_stage" in data and data["funnel_stage"] is not None:
        try:
            dialog.funnel_stage = FunnelStage(data["funnel_stage"])
        except ValueError as e:
            raise HTTPException(400, f"Invalid funnel_stage: {e}") from e
    if "quoted_price_usd" in data:
        dialog.quoted_price_usd = data["quoted_price_usd"]
    if "quoted_price_max_usd" in data:
        dialog.quoted_price_max_usd = data["quoted_price_max_usd"]
    if "quoted_days" in data:
        dialog.quoted_days = data["quoted_days"]
    if "tz_summary" in data and data["tz_summary"] is not None:
        dialog.tz_summary = data["tz_summary"]
    if "admin_task_summary" in data and data["admin_task_summary"] is not None:
        dialog.admin_task_summary = data["admin_task_summary"]
    if "client_offer_pitch" in data and data["client_offer_pitch"] is not None:
        dialog.client_offer_pitch = data["client_offer_pitch"]
    if data.get("quoted_price_usd"):
        dialog.price_approved = True
        dialog.awaiting_admin_quote = False
        if dialog.work_status == WorkStatus.AWAITING_ADMIN.value:
            dialog.work_status = WorkStatus.QUOTING.value
    if data.get("price_approved") is True:
        dialog.price_approved = True
        dialog.awaiting_admin_quote = False

    send_offer = bool(data.get("send_offer"))
    offer_text = None
    if send_offer:
        from app.services.dialog_service import resolve_chat_id, send_approved_offer
        from app.telegram.client import send_telegram_message

        try:
            offer_text = await send_approved_offer(db, dialog)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        await send_telegram_message(
            resolve_chat_id(dialog),
            offer_text,
            business_connection_id=dialog.business_connection_id,
        )

    await db.flush()
    card = serialize_dialog_card(dialog, message_count=len(dialog.messages or []))
    if offer_text:
        card["sent_offer"] = offer_text
    return card


@router.post("/dialogs/{dialog_id}/send-offer")
async def send_offer(dialog_id: int, db: AsyncSession = Depends(get_db)):
    """Admin: send approved price package to client."""
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    from app.services.dialog_service import resolve_chat_id, send_approved_offer
    from app.telegram.client import send_telegram_message

    try:
        offer_text = await send_approved_offer(db, dialog)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await send_telegram_message(
        resolve_chat_id(dialog),
        offer_text,
        business_connection_id=dialog.business_connection_id,
    )
    await db.flush()
    return {
        "ok": True,
        "offer": offer_text,
        "dialog": serialize_dialog_card(dialog, message_count=len(dialog.messages or [])),
    }


@router.patch("/dialogs/{dialog_id}/ai", response_model=DialogOut)
async def toggle_ai(dialog_id: int, body: DialogToggleAI, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    dialog.ai_active = body.ai_active
    await db.flush()
    return DialogOut(
        id=dialog.id,
        telegram_user_id=dialog.telegram_user_id,
        telegram_username=dialog.telegram_username,
        first_name=dialog.first_name,
        funnel_stage=dialog.funnel_stage,
        ai_active=dialog.ai_active,
        last_message_at=dialog.last_message_at,
        followup_count=dialog.followup_count,
    )


@router.post("/dialogs/{dialog_id}/messages")
async def send_operator_message(dialog_id: int, body: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    dialog = await get_dialog_detail(db, dialog_id)
    if not dialog:
        raise HTTPException(404, "Dialog not found")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(400, "Empty message")
    msg = Message(dialog_id=dialog.id, role=MessageRole.OPERATOR, content=content)
    db.add(msg)
    dialog.last_message_at = datetime.now(timezone.utc)
    await db.flush()
    try:
        from app.services.dialog_service import log_event

        await log_event(
            db,
            "agent_response",
            "operator",
            dialog.id,
            {"preview": content[:120]},
        )
    except Exception:
        pass
    try:
        await send_telegram_message(
            resolve_chat_id(dialog),
            content,
            business_connection_id=dialog.business_connection_id,
        )
    except Exception as e:
        raise HTTPException(502, f"Failed to send: {e}")
    return {"ok": True, "message": serialize_message(msg)}


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(dialog_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Order).order_by(Order.created_at.desc()).limit(100)
    if dialog_id is not None:
        q = select(Order).where(Order.dialog_id == dialog_id).order_by(Order.created_at.desc()).limit(100)
    result = await db.execute(q)
    return result.scalars().all()

@router.get("/knowledge", response_model=list[KnowledgeDocOut])
async def list_knowledge(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    return result.scalars().all()


@router.post("/knowledge/upload", response_model=KnowledgeDocOut)
async def upload_knowledge(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    path, ext = save_upload(file.filename or "doc.txt", content)
    doc = KnowledgeDocument(filename=file.filename or "doc", file_path=path, file_type=ext)
    db.add(doc)
    await db.flush()
    chunks = await index_document(doc.id, doc.filename, path, ext)
    doc.chunk_count = chunks
    doc.indexed = chunks > 0
    await db.flush()
    return doc


@router.post("/knowledge/{doc_id}/reindex", response_model=KnowledgeDocOut)
async def reindex_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    await delete_document_vectors(doc.id)
    chunks = await index_document(doc.id, doc.filename, doc.file_path, doc.file_type)
    doc.chunk_count = chunks
    doc.indexed = chunks > 0
    return doc


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(KnowledgeDocument, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    await delete_document_vectors(doc.id)
    await db.delete(doc)
    return {"ok": True}


@router.get("/settings", response_model=AgentSettingsOut)
async def get_settings_api(db: AsyncSession = Depends(get_db)):
    return await get_or_create_settings(db)


@router.put("/settings", response_model=AgentSettingsOut)
async def update_settings(body: AgentSettingsUpdate, db: AsyncSession = Depends(get_db)):
    settings = await get_or_create_settings(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    await db.flush()
    return settings


connections: list[WebSocket] = []
_ws_bridged = False


async def _ws_fanout(data: dict) -> None:
    dead: list[WebSocket] = []
    for ws in list(connections):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            connections.remove(ws)
        except ValueError:
            pass


def _ensure_ws_bridge() -> None:
    global _ws_bridged
    if _ws_bridged:
        return
    from app.services.event_bus import subscribe

    subscribe(_ws_fanout)
    _ws_bridged = True


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    _ensure_ws_bridge()
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)
