#!/usr/bin/env python3
"""Export all ARIX dialogs + messages to JSON for offline review / training.

Runs on the Ubuntu server against the live DB. Does not mutate anything.

Usage (from repo root or backend/):

  # SQLite file (default path: <repo>/data/ai_agent.db) — no venv required
  python3 backend/tools/export_chats.py -o /tmp/arix_chats.json

  # Explicit DB path
  python3 backend/tools/export_chats.py --db /var/www/ai_arix/data/ai_agent.db -o chats.json

  # Via app settings / DATABASE_URL (needs backend deps + .env)
  cd backend && ../venv/bin/python tools/export_chats.py --via-app -o ../data/exports/chats.json

Options:
  --min-messages N   skip dialogs with fewer than N messages (default 1)
  --no-system        drop role=system messages
  --compact          only id + transcript turns (lighter for LLM work)
  --pretty           indent JSON (default on; use --no-pretty for one line)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "ai_agent.db"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    s = str(value).strip()
    return s or None


def _enum_val(value: Any) -> Any:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else value


def build_payload(
    dialogs: list[dict[str, Any]],
    *,
    source_db: str,
    compact: bool,
) -> dict[str, Any]:
    msg_total = sum(len(d.get("messages") or d.get("transcript") or []) for d in dialogs)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "ai_arix",
        "source_db": source_db,
        "dialog_count": len(dialogs),
        "message_count": msg_total,
        "format": "compact" if compact else "full",
        "dialogs": dialogs,
    }


def dialog_to_full(row: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "telegram_user_id": row.get("telegram_user_id"),
        "telegram_chat_id": row.get("telegram_chat_id"),
        "telegram_username": row.get("telegram_username"),
        "first_name": row.get("first_name"),
        "is_business": bool(row.get("is_business")),
        "funnel_stage": _enum_val(row.get("funnel_stage")),
        "work_status": row.get("work_status"),
        "ai_active": bool(row.get("ai_active")) if row.get("ai_active") is not None else None,
        "quoted_price_usd": row.get("quoted_price_usd"),
        "quoted_price_max_usd": row.get("quoted_price_max_usd"),
        "quoted_days": row.get("quoted_days"),
        "price_approved": bool(row.get("price_approved")) if row.get("price_approved") is not None else None,
        "tz_summary": row.get("tz_summary") or "",
        "admin_task_summary": row.get("admin_task_summary") or "",
        "client_offer_pitch": row.get("client_offer_pitch") or "",
        "client_profile": row.get("client_profile") if isinstance(row.get("client_profile"), dict) else {},
        "created_at": _iso(row.get("created_at")),
        "last_message_at": _iso(row.get("last_message_at")),
        "last_user_message_at": _iso(row.get("last_user_message_at")),
        "messages": messages,
    }


def dialog_to_compact(row: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    transcript = [
        {
            "role": m["role"],
            "content": m["content"],
            "at": m.get("created_at"),
            **({"agent": m["agent_name"]} if m.get("agent_name") else {}),
        }
        for m in messages
    ]
    return {
        "id": row["id"],
        "username": row.get("telegram_username"),
        "stage": _enum_val(row.get("funnel_stage")),
        "work_status": row.get("work_status"),
        "price_usd": row.get("quoted_price_usd"),
        "tz_summary": (row.get("tz_summary") or "").strip() or None,
        "transcript": transcript,
    }


def serialize_message(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "role": _enum_val(row.get("role")),
        "content": row.get("content") or "",
        "media_type": row.get("media_type"),
        "agent_name": row.get("agent_name"),
        "telegram_message_id": row.get("telegram_message_id"),
        "created_at": _iso(row.get("created_at")),
    }


# ── SQLite (stdlib, no deps) ─────────────────────────────────────────────────


def _parse_json_field(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def export_sqlite(
    db_path: Path,
    *,
    min_messages: int,
    drop_system: bool,
    compact: bool,
) -> dict[str, Any]:
    if not db_path.is_file():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        dialogs_raw = conn.execute(
            """
            SELECT *
            FROM dialogs
            ORDER BY id ASC
            """
        ).fetchall()

        out: list[dict[str, Any]] = []
        for d in dialogs_raw:
            drow = dict(d)
            drow["client_profile"] = _parse_json_field(drow.get("client_profile"))

            sql = """
                SELECT id, role, content, media_type, agent_name,
                       telegram_message_id, created_at
                FROM messages
                WHERE dialog_id = ?
            """
            params: list[Any] = [drow["id"]]
            if drop_system:
                sql += " AND role != ?"
                params.append("system")
            sql += " ORDER BY created_at ASC, id ASC"

            msgs = [serialize_message(dict(m)) for m in conn.execute(sql, params).fetchall()]
            if len(msgs) < min_messages:
                continue

            out.append(
                dialog_to_compact(drow, msgs) if compact else dialog_to_full(drow, msgs)
            )

        return build_payload(out, source_db=str(db_path.resolve()), compact=compact)
    finally:
        conn.close()


# ── SQLAlchemy / app settings (sqlite or postgres) ───────────────────────────


async def export_via_app(
    *,
    min_messages: int,
    drop_system: bool,
    compact: bool,
) -> dict[str, Any]:
    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.config import get_settings
    from app.database import async_session
    from app.db.models import Dialog, Message, MessageRole

    settings = get_settings()

    async with async_session() as db:
        result = await db.execute(
            select(Dialog)
            .options(selectinload(Dialog.messages))
            .order_by(Dialog.id.asc())
        )
        dialogs = result.scalars().unique().all()

        out: list[dict[str, Any]] = []
        for d in dialogs:
            msgs_sorted = sorted(
                d.messages,
                key=lambda m: (m.created_at or datetime.min.replace(tzinfo=timezone.utc), m.id),
            )
            if drop_system:
                msgs_sorted = [m for m in msgs_sorted if m.role != MessageRole.SYSTEM]
            if len(msgs_sorted) < min_messages:
                continue

            drow = {
                "id": d.id,
                "telegram_user_id": d.telegram_user_id,
                "telegram_chat_id": d.telegram_chat_id,
                "telegram_username": d.telegram_username,
                "first_name": d.first_name,
                "is_business": d.is_business,
                "funnel_stage": d.funnel_stage,
                "work_status": d.work_status,
                "ai_active": d.ai_active,
                "quoted_price_usd": d.quoted_price_usd,
                "quoted_price_max_usd": d.quoted_price_max_usd,
                "quoted_days": d.quoted_days,
                "price_approved": d.price_approved,
                "tz_summary": d.tz_summary,
                "admin_task_summary": d.admin_task_summary,
                "client_offer_pitch": d.client_offer_pitch,
                "client_profile": d.client_profile or {},
                "created_at": d.created_at,
                "last_message_at": d.last_message_at,
                "last_user_message_at": d.last_user_message_at,
            }
            messages = [
                serialize_message(
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "media_type": m.media_type,
                        "agent_name": m.agent_name,
                        "telegram_message_id": m.telegram_message_id,
                        "created_at": m.created_at,
                    }
                )
                for m in msgs_sorted
            ]
            out.append(
                dialog_to_compact(drow, messages) if compact else dialog_to_full(drow, messages)
            )

    return build_payload(out, source_db=settings.database_url_sync, compact=compact)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export ARIX chats to JSON")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("arix_chats_export.json"),
        help="Output JSON path (default: ./arix_chats_export.json)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"SQLite DB path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--via-app",
        action="store_true",
        help="Use app DATABASE_URL / SQLAlchemy (postgres or sqlite from .env)",
    )
    parser.add_argument("--min-messages", type=int, default=1, help="Min messages per dialog")
    parser.add_argument("--no-system", action="store_true", help="Exclude system messages")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Lighter shape: transcript turns only (good for daivinchik prompt work)",
    )
    parser.add_argument(
        "--no-pretty",
        action="store_true",
        help="Write minified JSON",
    )
    args = parser.parse_args()

    if args.via_app:
        import asyncio

        payload = asyncio.run(
            export_via_app(
                min_messages=args.min_messages,
                drop_system=args.no_system,
                compact=args.compact,
            )
        )
    else:
        db_path = args.db or DEFAULT_DB
        payload = export_sqlite(
            db_path,
            min_messages=args.min_messages,
            drop_system=args.no_system,
            compact=args.compact,
        )

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=None if args.no_pretty else 2,
            default=str,
        )
        f.write("\n")

    print(
        f"OK: {payload['dialog_count']} dialogs, "
        f"{payload['message_count']} messages → {out.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
