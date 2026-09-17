from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Sales Agent"
    debug: bool = False
    api_secret_key: str = "dev-secret-change-me"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    log_level: str = "INFO"

    # Local-first: SQLite works without Docker/Postgres
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'ai_agent.db').as_posix()}"
    database_url_sync: str = f"sqlite:///{(DATA_DIR / 'ai_agent.db').as_posix()}"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    use_inprocess_scheduler: bool = True

    # Multi-LLM
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "models/text-embedding-004"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Point at any OpenAI-compatible endpoint (vLLM, Ollama, a gateway, ...)
    openai_base_url: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    llm_primary: str = "gemini"  # gemini | openai | anthropic
    llm_fallback_order: str = "gemini,openai,anthropic"

    # Telegram Bot API (regular bot + Business Bot)
    telegram_bot_token: str = ""
    telegram_admin_id: int = 0  # admin who gets escrow drafts / alerts
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_name: str = "ai_sales_agent"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "knowledge_base"
    use_local_rag: bool = True

    tron_api_key: str = ""
    tron_master_mnemonic: str = ""
    usdt_contract: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    tron_confirmations: int = 19

    escrow_api_url: str = ""
    escrow_api_key: str = ""
    # Never auto-create escrow deals — only draft + admin notify
    escrow_auto_create: bool = False

    followup_delays_hours: str = "2,24,72"
    max_followups: int = 20
    # Human reply timing (seconds). Override in .env for prod (e.g. 120–180).
    reply_delay_min_sec: float = 3.0
    reply_delay_max_sec: float = 8.0
    typing_delay_min: float = 1.5
    typing_delay_max: float = 18.0
    typing_chars_per_second: float = 14.0
    payment_reminder_minutes: int = 20
    telegram_admin_tag: str = "@arxixx"
    max_concurrent_dialogs: int = 50

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def followup_delays_list(self) -> list[int]:
        return [int(x.strip()) for x in self.followup_delays_hours.split(",") if x.strip()]

    @property
    def llm_fallback_list(self) -> list[str]:
        return [x.strip() for x in self.llm_fallback_order.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
