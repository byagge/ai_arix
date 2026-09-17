from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.bot_admin import router as bot_admin_router
from app.api.logs_admin import router as logs_router
from app.api.platform import router as platform_router
from app.api.router import router
from app.api.telegram_admin import router as telegram_router
from app.config import get_settings
from app.database import Base, engine
from app.db import platform_models  # noqa: F401
from app.db import bot_extensions  # noqa: F401
from app.logging_setup import setup_logging
from app.services.scheduler import start_scheduler, stop_scheduler
from app.telegram.client import is_telegram_running, start_telegram_bot, stop_telegram_bot

settings = get_settings()
LOG_PATH = setup_logging()
logger = logging.getLogger("arix")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip noisy polling
        path = request.url.path
        if path in ("/health", "/api/health") or path.startswith("/uploads"):
            return await call_next(request)
        # Soft-poll detail/list still logged at debug only
        if path.startswith("/api/dialogs") and request.method == "GET":
            logger.debug("%s %s", request.method, path)
            return await call_next(request)
        logger.info("%s %s", request.method, path)
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                logger.warning("%s %s -> %s", request.method, path, response.status_code)
            return response
        except Exception:
            logger.exception("%s %s failed", request.method, path)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Arix starting debug=%s", settings.debug)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        from app.db.migrate import migrate_sqlite

        await migrate_sqlite()
        logger.info("sqlite migrate ok")
    except Exception as e:
        logger.exception("SQLite migrate: %s", e)

    try:
        from app.database import async_session
        from app.services.registry import sync_all

        async with async_session() as db:
            await sync_all(db)
            await db.commit()
    except Exception as e:
        logger.warning("Model registry sync skipped: %s", e)

    try:
        from app.rag.indexer import index_document
        from pathlib import Path as P

        sample = P(__file__).resolve().parents[1] / "sample_data" / "price_list.txt"
        if sample.exists():
            await index_document(0, "price_list.txt", str(sample), "txt")
    except Exception as e:
        logger.warning("RAG seed: %s", e)

    try:
        from app.api.router import _ensure_ws_bridge

        _ensure_ws_bridge()
    except Exception as e:
        logger.warning("WS bridge: %s", e)

    try:
        from app.services.payment_templates import seed_templates

        await seed_templates()
    except Exception as e:
        logger.warning("Payment templates seed: %s", e)

    await start_scheduler()
    try:
        from app.services.runtime_config import refresh_from_db

        await refresh_from_db()
    except Exception as e:
        logger.warning("Runtime config: %s", e)
    try:
        await start_telegram_bot()
        logger.info("Telegram bot started")
    except Exception as e:
        logger.exception("Telegram bot not started: %s", e)
    yield
    logger.info("Arix shutting down")
    await stop_scheduler()
    await stop_telegram_bot()


app = FastAPI(title="Arix Platform", version="2.0.0", lifespan=lifespan)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")
app.include_router(bot_admin_router, prefix="/api")
app.include_router(telegram_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(platform_router, prefix="/v1", tags=["platform"])

uploads = Path("uploads")
uploads.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads)), name="uploads")


@app.get("/health")
async def health():
    s = get_settings()
    llm_ok = bool(
        s.google_api_key
        or s.openai_api_key
        or s.anthropic_api_key
    )
    return {
        "status": "ok",
        "service": s.app_name,
        "debug": s.debug,
        "log_file": str(LOG_PATH),
        "telegram": {
            "token_set": bool(s.telegram_bot_token),
            "admin_set": bool(s.telegram_admin_id),
            "running": is_telegram_running(),
        },
        "llm": {
            "primary": s.llm_primary,
            "configured": llm_ok,
            "openai_endpoint": s.openai_base_url or "api.openai.com",
            "has_gemini": bool(s.google_api_key),
            "has_openai": bool(s.openai_api_key),
            "has_anthropic": bool(s.anthropic_api_key),
        },
        "reply_delay_sec": [s.reply_delay_min_sec, s.reply_delay_max_sec],
    }
