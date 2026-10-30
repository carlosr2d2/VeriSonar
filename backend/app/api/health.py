from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import settings
from app.database import get_db
from app.schemas import HealthComponent, HealthOut
from app.workers.celery_app import celery_app

router = APIRouter(tags=["salud"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    components: list[HealthComponent] = []

    try:
        db.execute(text("SELECT 1"))
        components.append(HealthComponent(name="postgres", status="ok"))
    except Exception as exc:
        components.append(HealthComponent(name="postgres", status="error", detail=str(exc)))

    try:
        pong = celery_app.backend.client.ping() if hasattr(celery_app.backend, "client") else True
        # Redis ping via broker
        from redis import Redis

        redis = Redis.from_url(settings.redis_url)
        redis.ping()
        components.append(HealthComponent(name="redis", status="ok" if pong else "degraded"))
    except Exception as exc:
        components.append(HealthComponent(name="redis", status="error", detail=str(exc)))

    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        ping = inspect.ping() or {}
        workers = len(ping)
        components.append(
            HealthComponent(
                name="celery",
                status="ok" if workers else "degraded",
                detail=f"{workers} workers",
            )
        )
    except Exception as exc:
        components.append(HealthComponent(name="celery", status="degraded", detail=str(exc)))

    overall = "ok" if all(item.status == "ok" for item in components) else "degraded"
    if any(item.status == "error" for item in components):
        overall = "error"

    return HealthOut(
        status=overall,
        version=__version__,
        processing_mode=settings.processing_mode,
        locale=settings.default_locale,
        components=components,
    )
