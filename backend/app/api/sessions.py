from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access import can_access_owner, is_admin, require_analyst_or_admin
from app.core.security import get_current_user
from app.database import get_db
from app.models import AnalysisSession, AudioRecord, AudioStatus, Report, User
from app.schemas import DashboardMetrics, SessionCreate, SessionOut
from app.services.vsa import allocate_evaluation_code
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/sessions", tags=["sesiones"])


@router.post("", response_model=SessionOut)
def create_session(
    body: SessionCreate,
    user: User = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
) -> AnalysisSession:
    session = AnalysisSession(
        user_id=user.id,
        title=body.title,
        language=body.language,
        context=body.context,
        subject_name=body.subject_name,
        subject_document=body.subject_document,
        location=body.location,
        modality=body.modality or "presencial",
        purpose=body.purpose,
        evaluator_name=body.evaluator_name or user.full_name,
        evaluator_title=body.evaluator_title,
        evaluation_code=allocate_evaluation_code(db),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisSession]:
    q = select(AnalysisSession).order_by(AnalysisSession.created_at.desc())
    if not is_admin(user):
        q = q.where(AnalysisSession.user_id == user.id)
    return list(db.scalars(q).all())


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisSession:
    session = db.get(AnalysisSession, session_id)
    if not session or not can_access_owner(user, session.user_id):
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


def collect_dashboard(db: Session, user: User | None = None) -> DashboardMetrics:
    scoped = user is not None and not is_admin(user)

    sessions_q = select(func.count()).select_from(AnalysisSession)
    if scoped:
        sessions_q = sessions_q.where(AnalysisSession.user_id == user.id)

    def audio_count(*status_filter):
        q = select(func.count()).select_from(AudioRecord)
        if scoped:
            q = q.join(AnalysisSession, AudioRecord.session_id == AnalysisSession.id).where(
                AnalysisSession.user_id == user.id
            )
        for item in status_filter:
            q = q.where(item)
        return db.scalar(q) or 0

    def report_avg(column):
        q = select(func.avg(column))
        if scoped:
            q = q.join(AnalysisSession, Report.session_id == AnalysisSession.id).where(AnalysisSession.user_id == user.id)
        return db.scalar(q) or 0.0

    sessions_total = db.scalar(sessions_q) or 0
    completed = audio_count(AudioRecord.status == AudioStatus.COMPLETED)
    failed = audio_count(AudioRecord.status == AudioStatus.FAILED)
    in_progress = audio_count(
        AudioRecord.status.in_([AudioStatus.QUEUED, AudioStatus.TRANSCRIBING, AudioStatus.ANALYZING])
    )
    avg_rel = report_avg(Report.reliability_index)
    avg_dec = report_avg(Report.deception_index)

    workers = 0
    active = 0
    queued = 0
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        ping = inspect.ping() or {}
        workers = len(ping)
        active_map = inspect.active() or {}
        active = sum(len(v) for v in active_map.values())
        reserved = inspect.reserved() or {}
        queued = sum(len(v) for v in reserved.values())
        from redis import Redis
        from app.config import settings

        redis = Redis.from_url(settings.celery_broker_url)
        for queue in ("audio", "reports", "maintenance"):
            queued += int(redis.llen(queue) or 0)
    except Exception:
        pass

    return DashboardMetrics(
        sessions_total=int(sessions_total),
        analyses_completed=int(completed),
        analyses_failed=int(failed),
        analyses_in_progress=int(in_progress),
        avg_reliability=round(float(avg_rel), 4),
        avg_deception=round(float(avg_dec), 4),
        celery_workers=workers,
        celery_active_tasks=active,
        celery_queued_tasks=queued,
    )
