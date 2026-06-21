"""Celery application for durable document parsing and indexing jobs."""

from celery import Celery

from app.rag.config import get_rag_settings


settings = get_rag_settings()
celery_app = Celery(
    "deepsearch_rag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.rag.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,
    timezone="Asia/Shanghai",
)

