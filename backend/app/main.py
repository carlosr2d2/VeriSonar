from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from app import __version__
from app.api import analyze, auth, health, ops, reports, sessions, users, ws
from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import User, UserRole
from app.seed import seed_catalog
from app.services.storage import ensure_dirs

configure_logging()
logger = get_logger(__name__)


def seed_users() -> None:
    db = SessionLocal()
    created = 0
    updated = 0
    try:
        for spec in seed_catalog():
            exists = db.scalar(select(User).where(User.email == spec["email"]))
            desired_role = UserRole(spec["role"])
            if exists:
                if exists.full_name != spec["full_name"] or exists.role != desired_role:
                    exists.full_name = spec["full_name"]
                    exists.role = desired_role
                    updated += 1
                continue
            db.add(
                User(
                    email=spec["email"],
                    hashed_password=hash_password(spec["password"]),
                    full_name=spec["full_name"],
                    role=desired_role,
                    locale=settings.default_locale,
                )
            )
            created += 1
        if created or updated:
            db.commit()
            logger.info("seed_users_applied", created=created, updated=updated)
        else:
            db.rollback()
    except Exception as exc:
        logger.warning("seed_users_skipped", error=str(exc))
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    seed_users()
    logger.info(
        "verisonar_ready",
        mode=settings.processing_mode,
        locale=settings.default_locale,
        version=__version__,
    )
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="VeriSonar API",
        description=(
            "Plataforma latinoamericana de análisis de voz y pistas de confiabilidad. "
            "Fase 1: procesamiento offline (Vosk/Whisper + léxico ES-LATAM + acústica). "
            "Fase 2: streaming WebSocket/WebRTC y despliegue Kubernetes."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "salud", "description": "Liveness y dependencias"},
            {"name": "análisis", "description": "Carga de audio y resultados"},
            {"name": "sesiones", "description": "Expedientes de entrevista"},
            {"name": "reportes", "description": "PDF/JSON de auditoría"},
            {"name": "autenticación", "description": "JWT y tokens push móviles"},
            {"name": "usuarios", "description": "Directorio (solo administrador)"},
            {"name": "tiempo-real", "description": "WebSockets fase 2"},
            {"name": "móvil", "description": "Contrato estable para React Native"},
        ],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(sessions.router)
    api.include_router(analyze.router)
    api.include_router(reports.router)
    api.include_router(ops.router)
    api.include_router(users.router)
    application.include_router(health.router)
    application.include_router(health.router, prefix="/api/v1")
    application.include_router(api)
    application.include_router(ws.router)
    application.include_router(ws.router, prefix="/api/v1")

    mobile = APIRouter(prefix="/api/mobile/v1", tags=["móvil"])
    mobile.include_router(auth.router)
    mobile.include_router(analyze.router)
    mobile.include_router(reports.router)
    application.include_router(mobile)

    if settings.prometheus_enabled:
        Instrumentator().instrument(application).expose(application, endpoint="/metrics", include_in_schema=False)

    return application


app = create_app()
