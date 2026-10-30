from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.core.audit import write_audit
from app.core.logging import get_logger
from app.core.metrics import ANALYSES_TOTAL, ANALYSIS_DURATION, DECEPTION_SCORE, RELIABILITY_SCORE
from app.database import SessionLocal
from app.models import AnalysisSession, AudioRecord, AudioStatus, Report, SessionStatus, User
from app.services.acoustic import extract_acoustic_features, normalize_to_wav
from app.services.deception import analyze_signals
from app.services.interview import build_interview_view
from app.services.praat_acoustic import extract_praat_features, merge_acoustic_features
from app.services.progress import init_progress, mark_completed, mark_failed, update_stage
from app.services.reports import write_json_report, write_pdf_report
from app.services.vsa import allocate_evaluation_code, attach_vsa_scores, exam_from_session, flagged_findings
from app.services.push import notify_push
from app.services.stt import transcribe_offline

logger = get_logger(__name__)


def process_audio_record(audio_id: str) -> str:
    started = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        audio = db.get(AudioRecord, audio_id)
        if not audio:
            raise ValueError(f"Audio {audio_id} no existe")
        session = db.get(AnalysisSession, audio.session_id)
        init_progress(audio.id)
        audio.status = AudioStatus.TRANSCRIBING
        if session:
            session.status = SessionStatus.PROCESSING
        db.commit()

        wav_path = Path(settings.upload_dir) / f"{audio.id}.wav"
        update_stage(audio.id, "conversion", status="running", percent=1, label="Convirtiendo a WAV mono 16 kHz")
        normalize_to_wav(
            audio.storage_path,
            wav_path,
            on_progress=lambda pct: update_stage(
                audio.id, "conversion", percent=pct, status="running", label="Convirtiendo a WAV mono 16 kHz"
            ),
        )
        import soundfile as sf

        wav_info = sf.info(str(wav_path))
        audio.duration_seconds = float(wav_info.duration)
        audio.sample_rate = int(wav_info.samplerate)
        audio.channels = int(wav_info.channels)
        update_stage(
            audio.id,
            "conversion",
            status="done",
            label="Audio listo (mono 16 kHz PCM 16 bits)",
        )
        db.commit()

        language = session.language if session else "es"
        update_stage(audio.id, "transcription", status="running", percent=1, label="Cargando modelo de transcripción")
        stt = transcribe_offline(
            wav_path,
            language=language,
            on_progress=lambda pct, lbl=None: update_stage(
                audio.id,
                "transcription",
                percent=pct,
                status="running",
                label=lbl or "Transcribiendo",
            ),
        )
        update_stage(audio.id, "transcription", status="done", label="Transcripción lista")

        audio.status = AudioStatus.ANALYZING
        db.commit()
        update_stage(audio.id, "analysis", status="running", percent=8, label="Extrayendo acústica")
        acoustic = extract_acoustic_features(wav_path)
        if settings.enable_praat:
            update_stage(audio.id, "analysis", percent=22, status="running", label="Análisis Praat")
            acoustic = merge_acoustic_features(acoustic, extract_praat_features(wav_path))
        if not audio.duration_seconds:
            audio.duration_seconds = acoustic.get("duration_seconds")
        if not audio.sample_rate:
            audio.sample_rate = acoustic.get("sample_rate")
        if not audio.channels:
            audio.channels = acoustic.get("channels")
        db.commit()

        interview: dict = {}
        try:
            update_stage(audio.id, "analysis", percent=40, status="running", label="Segmentando entrevista")
            interview = build_interview_view(wav_path, stt, audio.id)
        except Exception as exc:
            logger.warning("interview_view_failed", audio_id=audio.id, error=str(exc))

        if interview.get("exchanges"):
            try:
                update_stage(audio.id, "analysis", percent=62, status="running", label="Puntaje VSA por respuesta")
                interview = attach_vsa_scores(
                    interview,
                    wav_path,
                    language=language,
                    enable_praat=settings.enable_praat,
                )
            except Exception as exc:
                logger.warning("vsa_scoring_failed", audio_id=audio.id, error=str(exc))

        owner = db.get(User, session.user_id) if session else None
        if session and not session.evaluation_code:
            session.evaluation_code = allocate_evaluation_code(db)

        update_stage(audio.id, "analysis", percent=80, status="running", label="Combinando señales")
        nlp_text = (interview.get("answers_text") or stt.text or "").strip()
        result = analyze_signals(nlp_text or stt.text, language, acoustic, stt.engine)
        if acoustic.get("praat"):
            result["method"] = "hybrid-lexicon-praat-v1"
            result["acoustic_engine"] = "praat+librosa"
        else:
            result["acoustic_engine"] = acoustic.get("acoustic_engine") or "librosa"
        display_text = interview.get("transcript_dialogo") or stt.text
        result["transcription"] = display_text
        result["interview"] = interview
        result["audio_id"] = audio.id
        result["session_id"] = audio.session_id
        result["original_name"] = audio.original_name
        result["exam"] = exam_from_session(session, owner)
        vsa = interview.get("vsa")
        if vsa:
            result["vsa"] = vsa
            result["method"] = "vsa-control-baseline-v1"
            result["findings"] = list(result.get("findings") or []) + flagged_findings(vsa)
            flagged = vsa.get("flagged_count") or 0
            if flagged:
                result["summary"] = (
                    f"{result.get('summary') or ''} "
                    f"VSA: {flagged} ítem(s) sobre la línea base {vsa.get('baseline'):.2f}."
                ).strip()

        report = Report(
            session_id=audio.session_id,
            audio_record_id=audio.id,
            transcription=display_text or None,
            language_detected=stt.language or language,
            stt_engine=stt.engine,
            linguistic_score=result["linguistic_score"],
            acoustic_score=result["acoustic_score"],
            deception_index=result["deception_index"],
            reliability_index=result["reliability_index"],
            findings=result,
        )
        db.add(report)
        db.flush()

        update_stage(audio.id, "analysis", percent=90, status="running", label="Generando informe")
        json_path = write_json_report(report.id, result)
        pdf_path = write_pdf_report(report.id, result)
        report.json_path = str(json_path)
        report.pdf_path = str(pdf_path)

        audio.status = AudioStatus.COMPLETED
        if session:
            session.status = SessionStatus.COMPLETED
        mark_completed(audio.id)
        db.commit()

        ANALYSES_TOTAL.labels(status="completed", language=language).inc()
        DECEPTION_SCORE.observe(result["deception_index"])
        RELIABILITY_SCORE.observe(result["reliability_index"])
        ANALYSIS_DURATION.observe((datetime.now(timezone.utc) - started).total_seconds())

        write_audit(
            db,
            action="analysis.completed",
            resource_type="report",
            resource_id=report.id,
            payload={"audio_id": audio.id, "deception_index": result["deception_index"]},
        )
        if session:
            owner = db.get(User, session.user_id)
            if owner:
                notify_push(
                    owner.push_token,
                    "VeriSonar",
                    "El análisis de voz está listo",
                    {"report_id": report.id, "audio_id": audio.id},
                )
        logger.info("analysis_completed", audio_id=audio.id, report_id=report.id)
        return report.id
    except Exception as exc:
        db.rollback()
        audio = db.get(AudioRecord, audio_id)
        if audio:
            audio.status = AudioStatus.FAILED
            audio.error_message = str(exc)
            mark_failed(audio.id, str(exc))
            session = db.get(AnalysisSession, audio.session_id)
            if session:
                session.status = SessionStatus.FAILED
            db.commit()
        ANALYSES_TOTAL.labels(status="failed", language="es").inc()
        logger.exception("analysis_failed", audio_id=audio_id)
        raise
    finally:
        db.close()


def cleanup_old_files(days: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    db = SessionLocal()
    try:
        rows = db.scalars(select(AudioRecord).where(AudioRecord.created_at < cutoff)).all()
        for audio in rows:
            path = Path(audio.storage_path)
            wav = Path(settings.upload_dir) / f"{audio.id}.wav"
            prog = Path(settings.upload_dir) / f"{audio.id}.progress.json"
            for candidate in (path, wav, prog):
                if candidate.exists():
                    candidate.unlink()
                    removed += 1
        write_audit(db, action="maintenance.cleanup", resource_type="storage", payload={"removed": removed})
        return {"removed": removed}
    finally:
        db.close()


def normalize_pending_metadata() -> dict:
    db = SessionLocal()
    updated = 0
    try:
        rows = db.scalars(select(AudioRecord).where(AudioRecord.file_size_bytes.is_(None))).all()
        for audio in rows:
            path = Path(audio.storage_path)
            if path.exists():
                audio.file_size_bytes = path.stat().st_size
                updated += 1
        db.commit()
        return {"updated": updated}
    finally:
        db.close()
