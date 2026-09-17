from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_sales_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "check-followups": {
            "task": "celery_app.tasks.process_followups",
            "schedule": 300.0,
        },
        "monitor-payments": {
            "task": "celery_app.tasks.monitor_payments",
            "schedule": 60.0,
        },
    },
)

celery_app.autodiscover_tasks(["celery_app"])
from celery_app import tasks  # noqa: F401, E402
