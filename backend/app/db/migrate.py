"""Add missing columns to existing SQLite DB (MVP migrations without Alembic)."""
from __future__ import annotations

from sqlalchemy import text

from app.database import engine

COLUMNS = [
    ("dialogs", "followup_mode", "VARCHAR(24) DEFAULT 'standard'"),
    ("dialogs", "custom_followup_at", "DATETIME"),
    ("dialogs", "work_status", "VARCHAR(24) DEFAULT 'lead'"),
    ("dialogs", "silent_until_completed", "BOOLEAN DEFAULT 0"),
    ("dialogs", "quoted_price_usd", "FLOAT"),
    ("dialogs", "quoted_days", "INTEGER"),
    ("dialogs", "estimated_price_usd", "FLOAT"),
    ("dialogs", "quoted_price_max_usd", "FLOAT"),
    ("dialogs", "price_approved", "BOOLEAN DEFAULT 0"),
    ("dialogs", "tz_summary", "TEXT DEFAULT ''"),
    ("dialogs", "admin_task_summary", "TEXT DEFAULT ''"),
    ("dialogs", "client_offer_pitch", "TEXT DEFAULT ''"),
    ("dialogs", "awaiting_admin_quote", "BOOLEAN DEFAULT 0"),
    ("dialogs", "pending_reply_at", "DATETIME"),
    ("dialogs", "telegram_chat_id", "INTEGER"),
    ("messages", "media_type", "VARCHAR(32)"),
    ("messages", "media_file_id", "VARCHAR(256)"),
    ("agent_settings", "reply_delay_min_sec", "FLOAT DEFAULT 3.0"),
    ("agent_settings", "reply_delay_max_sec", "FLOAT DEFAULT 8.0"),
    ("agent_settings", "force_business_reply", "BOOLEAN DEFAULT 0"),
    ("agent_settings", "global_ai_enabled", "BOOLEAN DEFAULT 1"),
]


async def migrate_sqlite() -> None:
    async with engine.begin() as conn:
        for table, col, typedef in COLUMNS:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))
            except Exception:
                pass
