"""
VerdictBridge – Celery worker configuration.

Start with:
  celery -A backend.worker worker --loglevel=info --concurrency=4
"""
from celery import Celery
from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "verdictbridge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)
