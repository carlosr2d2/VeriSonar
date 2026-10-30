from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import can_access_owner, require_analyst_or_admin
from app.core.audit import write_audit
from app.core.metrics import ANALYSES_TOTAL
from app.core.security import get_current_user
from app.database import get_db
from app.models import AnalysisSession, AudioRecord, AudioStatus, Report, SessionStatus, User
from app.schemas import AnalysisProgress, AnalyzeAccepted, AnalyzeStatus, AudioOut, ReportOut, SessionOut
from app.services.progress import init_progress, progress_for
from app.services.storage import save_upload, validate_audio
from app.services.vsa import allocate_evaluation_code
from app.workers.tasks import process_audio

router = APIRouter(tags=["análisis"])


def _blank(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _apply_ficha(
    session: AnalysisSession,
    *,
    title: str,
    language: str,
    context: str | None,
    subject_name: str | None,
    subject_document: str | None,
    location: str | None,
    modality: str | None,
    purpose: str | None,
    evaluator_name: str | None,
    evaluator_title: str | None,
    user: User,
    db: Session,
) -> None:
    session.title = title or session.title
    session.language = language or session.language
    if context is not None:
        session.context = _blank(context)
    if subject_name is not None:
        session.subject_name = _blank(subject_name)
    if subject_document is not None:
        session.subject_document = _blank(subject_document)
    if location is not None:
        session.location = _blank(location)
    if modality is not None:
        cleaned = (_blank(modality) or "presencial").lower()
        session.modality = cleaned if cleaned in {"presencial", "remoto"} else "presencial"
    if purpose is not None:
        session.purpose = _blank(purpose)
    session.evaluator_name = _blank(evaluator_name) or session.evaluator_name or user.full_name
    if evaluator_title is not None:
        session.evaluator_title = _blank(evaluator_title)
    if not session.evaluation_code:
        session.evaluation_code = allocate_evaluation_code(db)


@router.post("/analyze", response_model=AnalyzeAccepted)
async def analyze(
    file: UploadFile = File(...),
    title: str = Form(default="Análisis de voz"),
    language: str = Form(default="es"),
    session_id: str | None = Form(default=None),
    context: str | None = Form(default=None),
    subject_name: str | None = Form(default=None),
    subject_document: str | None = Form(default=None),
    location: str | None = Form(default=None),
    modality: str | None = Form(default="presencial"),
    purpose: str | None = Form(default=None),
    evaluator_name: str | None = Form(default=None),
    evaluator_title: str | None = Form(default=None),
    user: User = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
) -> AnalyzeAccepted:
    if language not in {"es", "en"}:
        raise HTTPException(status_code=400, detail="Idioma no soportado en esta fase")
    try:
        validate_audio(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if session_id:
        session = db.get(AnalysisSession, session_id)
        if not session or not can_access_owner(user, session.user_id):
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        _apply_ficha(
            session,
            title=title,
            language=language,
            context=context,
            subject_name=subject_name,
            subject_document=subject_document,
            location=location,
            modality=modality,
            purpose=purpose,
            evaluator_name=evaluator_name,
            evaluator_title=evaluator_title,
            user=user,
            db=db,
        )
    else:
        session = AnalysisSession(user_id=user.id, title=title, language=language)
        _apply_ficha(
            session,
            title=title,
            language=language,
            context=context,
            subject_name=subject_name,
            subject_document=subject_document,
            location=location,
            modality=modality,
            purpose=purpose,
            evaluator_name=evaluator_name,
            evaluator_title=evaluator_title,
            user=user,
            db=db,
        )
        db.add(session)
        db.flush()

    dest, stored_name = save_upload(file, session.id)
    audio = AudioRecord(
        session_id=session.id,
        filename=stored_name,
        original_name=file.filename or stored_name,
        storage_path=str(dest),
        content_type=file.content_type or "application/octet-stream",
        file_size_bytes=dest.stat().st_size,
        status=AudioStatus.QUEUED,
    )
    session.status = SessionStatus.QUEUED
    db.add(audio)
    db.flush()

    task = process_audio.delay(audio.id)
    audio.celery_task_id = task.id
    init_progress(audio.id)
    db.commit()

    ANALYSES_TOTAL.labels(status="queued", language=language).inc()
    write_audit(
        db,
        action="analysis.queued",
        resource_type="audio_record",
        resource_id=audio.id,
        payload={"task_id": task.id, "language": language},
        actor=user,
    )
    return AnalyzeAccepted(
        audio_id=audio.id,
        session_id=session.id,
        task_id=task.id,
        status=audio.status.value,
        message="Audio en cola. El worker Celery procesará la pista sin conexión a internet.",
    )


@router.get("/analyze/{audio_id}", response_model=AnalyzeStatus)
def analyze_status(
    audio_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyzeStatus:
    audio = db.get(AudioRecord, audio_id)
    if not audio:
        raise HTTPException(status_code=404, detail="Audio no encontrado")
    session = db.get(AnalysisSession, audio.session_id)
    if not session or not can_access_owner(user, session.user_id):
        raise HTTPException(status_code=404, detail="Audio no encontrado")

    report = db.scalar(select(Report).where(Report.audio_record_id == audio.id))
    task_state = None
    if audio.celery_task_id:
        try:
            from app.workers.celery_app import celery_app

            task_state = celery_app.AsyncResult(audio.celery_task_id).state
        except Exception:
            task_state = None

    return AnalyzeStatus(
        audio=AudioOut.model_validate(audio),
        session=SessionOut.model_validate(session),
        task_state=task_state,
        report=ReportOut.model_validate(report) if report else None,
        progress=AnalysisProgress.model_validate(
            progress_for(audio.id, audio.status.value, audio.error_message)
        ),
    )
