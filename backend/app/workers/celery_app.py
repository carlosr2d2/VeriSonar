from celery import Celery
from kombu import Queue

from app.config import settings

celery_app = Celery(
    "verisonar",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=86400,
    timezone="UTC",
    enable_utc=True,
    task_default_queue="audio",
    task_queues=(
        Queue("audio"),
        Queue("reports"),
        Queue("maintenance"),
    ),
    task_routes={
        "app.workers.tasks.process_audio": {"queue": "audio"},
        "app.workers.tasks.generate_report_artifacts": {"queue": "reports"},
        "app.workers.tasks.cleanup_and_normalize": {"queue": "maintenance"},
    },
    beat_schedule={
        "nightly-cleanup": {
            "task": "app.workers.tasks.cleanup_and_normalize",
            "schedule": 86400.0,
        }
    },
)
