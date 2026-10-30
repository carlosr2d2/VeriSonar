import copy
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.core.access import can_access_owner, is_admin
from app.core.audit import write_audit
from app.core.security import get_current_user
from app.database import get_db
from app.models import AnalysisSession, AudioRecord, Report, User
from app.schemas import ClipBoundsIn, ClipChartsIn, ClipTextIn, ClipWindowOut, ReportOut
from app.services.interview import (
    WINDOW_PAD,
    _load_source_wav,
    apply_clip_chart_inclusion,
    apply_clip_text,
    apply_manual_clip,
    build_clip_window,
    clip_comb_stale,
    ensure_clip_combs,
    write_clip_window_wav,
)
from app.services.reports import write_json_report, write_pdf_report
from app.services.vsa import flagged_findings

router = APIRouter(prefix="/reports", tags=["reportes"])


@router.get("", response_model=list[ReportOut])
def list_reports(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Report]:
    q = select(Report).join(AnalysisSession, Report.session_id == AnalysisSession.id).order_by(Report.created_at.desc())
    if not is_admin(user):
        q = q.where(AnalysisSession.user_id == user.id)
    return list(db.scalars(q).all())


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    report = _owned_report(db, user, report_id)
    interview = (report.findings or {}).get("interview") or {}
    exchanges = interview.get("exchanges") or []
    if exchanges and any(clip_comb_stale(item) for item in exchanges):
        try:
            wav = _source_wav(db, report)
            findings = copy.deepcopy(report.findings or {})
            if ensure_clip_combs(wav, report.audio_record_id, findings.get("interview") or {}):
                report.findings = findings
                flag_modified(report, "findings")
                db.commit()
                db.refresh(report)
        except Exception:
            pass
    return report


@router.get("/{report_id}/pdf")
def download_pdf(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    if not report.pdf_path or not Path(report.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF no generado")
    return FileResponse(
        report.pdf_path,
        media_type="application/pdf",
        filename=f"verisonar-{report.id}.pdf",
    )


@router.get("/{report_id}/json")
def download_json(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    if not report.json_path or not Path(report.json_path).exists():
        raise HTTPException(status_code=404, detail="JSON no generado")
    return FileResponse(
        report.json_path,
        media_type="application/json",
        filename=f"verisonar-{report.id}.json",
    )


def _owned_report(db: Session, user: User, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    session = db.get(AnalysisSession, report.session_id)
    if not session or not can_access_owner(user, session.user_id):
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    return report


def _clip_stem(clip_index: int) -> str:
    if clip_index < 1 or clip_index > 80:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    return f"{clip_index:02d}"


@router.get("/{report_id}/audio")
def download_audio(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    wav = Path(settings.upload_dir) / f"{report.audio_record_id}.wav"
    if not wav.exists():
        audio = db.get(AudioRecord, report.audio_record_id)
        if audio and Path(audio.storage_path).exists():
            wav = Path(audio.storage_path)
        else:
            raise HTTPException(status_code=404, detail="Audio no encontrado")
    return FileResponse(wav, media_type="audio/wav", filename=f"verisonar-{report.audio_record_id}.wav")


@router.get("/{report_id}/waveform")
def download_waveform(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    png = Path(settings.upload_dir) / report.audio_record_id / "waveform.png"
    if not png.exists():
        raise HTTPException(status_code=404, detail="Forma de onda no generada")
    return FileResponse(png, media_type="image/png", filename=f"verisonar-{report.id}-onda.png")


@router.get("/{report_id}/clips/{clip_index}/audio")
def download_clip_audio(
    report_id: str,
    clip_index: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    wav = Path(settings.upload_dir) / report.audio_record_id / "clips" / f"{_clip_stem(clip_index)}.wav"
    if not wav.exists():
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    return FileResponse(wav, media_type="audio/wav", filename=f"verisonar-clip-{clip_index:02d}.wav")


@router.get("/{report_id}/clips/{clip_index}/waveform")
def download_clip_waveform(
    report_id: str,
    clip_index: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    png = Path(settings.upload_dir) / report.audio_record_id / "clips" / f"{_clip_stem(clip_index)}.png"
    if not png.exists():
        raise HTTPException(status_code=404, detail="Forma de onda del clip no generada")
    return FileResponse(png, media_type="image/png", filename=f"verisonar-clip-{clip_index:02d}.png")


def _source_wav(db: Session, report: Report) -> Path:
    wav = Path(settings.upload_dir) / f"{report.audio_record_id}.wav"
    if wav.exists():
        return wav
    audio = db.get(AudioRecord, report.audio_record_id)
    if audio and audio.storage_path and Path(audio.storage_path).exists():
        return Path(audio.storage_path)
    raise HTTPException(status_code=404, detail="Audio no encontrado")


def _clip_row(report: Report, clip_index: int) -> dict:
    interview = (report.findings or {}).get("interview") or {}
    for item in interview.get("exchanges") or []:
        if int(item.get("index") or 0) == int(clip_index):
            return item
    raise HTTPException(status_code=404, detail="Clip no encontrado")


@router.get("/{report_id}/clips/{clip_index}/window", response_model=ClipWindowOut)
def clip_edit_window(
    report_id: str,
    clip_index: int,
    pad: float = Query(default=WINDOW_PAD, ge=0.4, le=8.0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClipWindowOut:
    report = _owned_report(db, user, report_id)
    row = _clip_row(report, clip_index)
    y, sr, _duration = _load_source(db, report)
    window = build_clip_window(
        y,
        sr,
        float(row.get("start") or 0),
        float(row.get("end") or 0),
        row.get("answer_start"),
        row.get("answer_end"),
        pad=pad,
    )
    return ClipWindowOut(index=clip_index, **window)


@router.get("/{report_id}/clips/{clip_index}/window-audio")
def clip_edit_window_audio(
    report_id: str,
    clip_index: int,
    pad: float = Query(default=WINDOW_PAD, ge=0.4, le=8.0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    report = _owned_report(db, user, report_id)
    row = _clip_row(report, clip_index)
    y, sr, _duration = _load_source(db, report)
    window = build_clip_window(
        y,
        sr,
        float(row.get("start") or 0),
        float(row.get("end") or 0),
        row.get("answer_start"),
        row.get("answer_end"),
        pad=pad,
    )
    dest = Path(settings.upload_dir) / report.audio_record_id / "clips" / f"{_clip_stem(clip_index)}-window.wav"
    write_clip_window_wav(y, sr, window["window_start"], window["window_end"], dest)
    return FileResponse(dest, media_type="audio/wav", filename=f"verisonar-clip-{clip_index:02d}-ventana.wav")


@router.patch("/{report_id}/clips/{clip_index}", response_model=ReportOut)
def adjust_clip_bounds(
    report_id: str,
    clip_index: int,
    body: ClipBoundsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    report = _owned_report(db, user, report_id)
    wav = _source_wav(db, report)
    findings = copy.deepcopy(report.findings or {})
    interview = findings.get("interview") or {}
    try:
        apply_manual_clip(
            wav,
            report.audio_record_id,
            interview,
            clip_index,
            body.start,
            body.end,
            body.answer_start,
            body.answer_end,
            language=report.language_detected or "es",
            enable_praat=settings.enable_praat,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    findings["interview"] = interview
    vsa = interview.get("vsa") or {}
    findings["vsa"] = vsa
    other = [item for item in (findings.get("findings") or []) if not str(item.get("code") or "").startswith("VSA_ITEM_")]
    findings["findings"] = other + flagged_findings(vsa)
    report.findings = findings
    flag_modified(report, "findings")
    json_path = write_json_report(report.id, findings)
    pdf_path = write_pdf_report(report.id, findings)
    report.json_path = str(json_path)
    report.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(report)
    write_audit(
        db,
        action="clip.bounds_adjusted",
        resource_type="report",
        resource_id=report.id,
        payload={
            "clip_index": clip_index,
            "start": body.start,
            "end": body.end,
            "answer_start": body.answer_start,
            "answer_end": body.answer_end,
        },
        actor=user,
    )
    return report


@router.patch("/{report_id}/clips/{clip_index}/charts", response_model=ReportOut)
def adjust_clip_charts(
    report_id: str,
    clip_index: int,
    body: ClipChartsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    report = _owned_report(db, user, report_id)
    findings = copy.deepcopy(report.findings or {})
    interview = findings.get("interview") or {}
    try:
        apply_clip_chart_inclusion(
            interview,
            clip_index,
            include_vsa=body.include_vsa,
            include_comb=body.include_comb,
            vsa_note=body.vsa_note,
            comb_note=body.comb_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    findings["interview"] = interview
    report.findings = findings
    flag_modified(report, "findings")
    json_path = write_json_report(report.id, findings)
    pdf_path = write_pdf_report(report.id, findings)
    report.json_path = str(json_path)
    report.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(report)
    write_audit(
        db,
        action="clip.charts_adjusted",
        resource_type="report",
        resource_id=report.id,
        payload={
            "clip_index": clip_index,
            "include_vsa": body.include_vsa,
            "include_comb": body.include_comb,
            "vsa_note": body.vsa_note,
            "comb_note": body.comb_note,
        },
        actor=user,
    )
    return report


@router.patch("/{report_id}/clips/{clip_index}/text", response_model=ReportOut)
def adjust_clip_text(
    report_id: str,
    clip_index: int,
    body: ClipTextIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Report:
    report = _owned_report(db, user, report_id)
    findings = copy.deepcopy(report.findings or {})
    interview = findings.get("interview") or {}
    try:
        apply_clip_text(
            interview,
            clip_index,
            body.question,
            body.answer,
            language=report.language_detected or "es",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    findings["interview"] = interview
    vsa = interview.get("vsa") or {}
    findings["vsa"] = vsa
    other = [item for item in (findings.get("findings") or []) if not str(item.get("code") or "").startswith("VSA_ITEM_")]
    findings["findings"] = other + flagged_findings(vsa)
    report.findings = findings
    flag_modified(report, "findings")
    json_path = write_json_report(report.id, findings)
    pdf_path = write_pdf_report(report.id, findings)
    report.json_path = str(json_path)
    report.pdf_path = str(pdf_path)
    db.commit()
    db.refresh(report)
    write_audit(
        db,
        action="clip.text_adjusted",
        resource_type="report",
        resource_id=report.id,
        payload={"clip_index": clip_index, "question": body.question, "answer": body.answer},
        actor=user,
    )
    return report


def _load_source(db: Session, report: Report):
    return _load_source_wav(_source_wav(db, report))
