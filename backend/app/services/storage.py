from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings

ALLOWED_AUDIO = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/webm",
    "audio/mp4",
    "audio/x-m4a",
    "audio/flac",
    "audio/amr",
    "audio/amr-wb",
    "audio/3gpp",
    "video/webm",
}

ALLOWED_EXT = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac", ".mp4", ".amr", ".3gp"}


def ensure_dirs() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.report_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.model_dir).mkdir(parents=True, exist_ok=True)


def validate_audio(file: UploadFile) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise ValueError(f"Formato no soportado: {suffix or 'desconocido'}")


def save_upload(file: UploadFile, session_id: str) -> tuple[Path, str]:
    ensure_dirs()
    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    stored_name = f"{session_id}_{uuid4().hex}{suffix}"
    dest = Path(settings.upload_dir) / stored_name
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return dest, stored_name
