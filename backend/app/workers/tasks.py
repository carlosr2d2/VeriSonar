from app.core.logging import configure_logging, get_logger
from app.services.pipeline import cleanup_old_files, normalize_pending_metadata, process_audio_record
from app.workers.celery_app import celery_app

configure_logging()
logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.process_audio", bind=True, max_retries=2)
def process_audio(self, audio_id: str) -> dict:
    logger.info("task_process_audio", audio_id=audio_id, retries=self.request.retries)
    try:
        report_id = process_audio_record(audio_id)
        generate_report_artifacts.delay(report_id)
        return {"audio_id": audio_id, "report_id": report_id, "status": "completed"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=15) from exc


@celery_app.task(name="app.workers.tasks.generate_report_artifacts")
def generate_report_artifacts(report_id: str) -> dict:
    """Los artefactos PDF/JSON se generan en el pipeline; esta tarea queda para reintentos."""
    logger.info("task_report_artifacts", report_id=report_id)
    return {"report_id": report_id, "status": "ready"}


@celery_app.task(name="app.workers.tasks.cleanup_and_normalize")
def cleanup_and_normalize(days: int = 30) -> dict:
    cleaned = cleanup_old_files(days=days)
    normalized = normalize_pending_metadata()
    return {**cleaned, **normalized}
