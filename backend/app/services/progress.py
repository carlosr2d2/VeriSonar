from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings

STAGES = ("conversion", "transcription", "analysis")


def progress_path(audio_id: str) -> Path:
    return Path(settings.upload_dir) / f"{audio_id}.progress.json"


def default_progress() -> dict[str, dict[str, Any]]:
    return {
        "conversion": {"percent": 0, "status": "pending", "label": "En espera"},
        "transcription": {"percent": 0, "status": "pending", "label": "En espera"},
        "analysis": {"percent": 0, "status": "pending", "label": "En espera"},
    }


def _write(audio_id: str, data: dict[str, dict[str, Any]]) -> None:
    path = progress_path(audio_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_progress(audio_id: str) -> dict[str, dict[str, Any]]:
    data = default_progress()
    path = progress_path(audio_id)
    if not path.exists():
        return data
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return data
    if not isinstance(loaded, dict):
        return data
    for stage in STAGES:
        row = loaded.get(stage) or {}
        if not isinstance(row, dict):
            continue
        current = data[stage]
        try:
            current["percent"] = max(0, min(100, int(row.get("percent") or 0)))
        except (TypeError, ValueError):
            pass
        status = str(row.get("status") or current["status"])
        if status in {"pending", "running", "done", "error"}:
            current["status"] = status
        label = row.get("label")
        if isinstance(label, str) and label.strip():
            current["label"] = label.strip()
    return data


def init_progress(audio_id: str) -> dict[str, dict[str, Any]]:
    data = default_progress()
    data["conversion"]["label"] = "En cola"
    _write(audio_id, data)
    return data


def update_stage(
    audio_id: str,
    stage: str,
    *,
    percent: int | None = None,
    status: str | None = None,
    label: str | None = None,
) -> dict[str, dict[str, Any]]:
    if stage not in STAGES:
        raise ValueError(f"Etapa desconocida: {stage}")
    data = read_progress(audio_id)
    row = data[stage]
    if percent is not None:
        row["percent"] = max(0, min(100, int(percent)))
    if status:
        row["status"] = status
        if status == "done":
            row["percent"] = 100
        elif status == "running" and row["percent"] <= 0:
            row["percent"] = 1
    if label:
        row["label"] = label
    _write(audio_id, data)
    return data


def mark_failed(audio_id: str, message: str | None = None) -> dict[str, dict[str, Any]]:
    data = read_progress(audio_id)
    for stage in STAGES:
        row = data[stage]
        if row["status"] == "running" or (row["status"] == "pending" and stage == "conversion"):
            row["status"] = "error"
            row["label"] = (message or "Error al procesar").strip()[:180]
            break
    _write(audio_id, data)
    return data


def mark_completed(audio_id: str) -> dict[str, dict[str, Any]]:
    data = read_progress(audio_id)
    labels = {
        "conversion": "Audio listo (mono 16 kHz PCM 16 bits)",
        "transcription": "Transcripción lista",
        "analysis": "Análisis VSA listo",
    }
    for stage in STAGES:
        data[stage]["status"] = "done"
        data[stage]["percent"] = 100
        data[stage]["label"] = labels[stage]
    _write(audio_id, data)
    return data


def progress_for(audio_id: str, audio_status: str, error_message: str | None = None) -> dict[str, dict[str, Any]]:
    data = read_progress(audio_id)
    status = (audio_status or "").lower()
    if status == "completed":
        data["conversion"] = {"percent": 100, "status": "done", "label": "Audio listo (mono 16 kHz PCM 16 bits)"}
        data["transcription"] = {"percent": 100, "status": "done", "label": "Transcripción lista"}
        data["analysis"] = {"percent": 100, "status": "done", "label": "Análisis VSA listo"}
        return data
    if status == "failed":
        flagged = False
        for stage in STAGES:
            row = data[stage]
            if row["status"] == "running" or (not flagged and row["status"] == "pending"):
                row["status"] = "error"
                row["label"] = (error_message or "El análisis falló")[:180]
                flagged = True
                break
        return data
    if status in {"uploaded", "queued"}:
        if data["conversion"]["status"] == "pending":
            data["conversion"]["label"] = "En cola"
        return data
    if status == "transcribing":
        if data["conversion"]["status"] == "pending":
            data["conversion"]["status"] = "running"
            data["conversion"]["percent"] = max(data["conversion"]["percent"], 8)
            data["conversion"]["label"] = "Convirtiendo a WAV mono 16 kHz"
        elif data["conversion"]["status"] == "done" and data["transcription"]["status"] == "pending":
            data["transcription"]["status"] = "running"
            data["transcription"]["percent"] = max(data["transcription"]["percent"], 5)
            data["transcription"]["label"] = "Transcribiendo"
        return data
    if status == "analyzing":
        if data["conversion"]["status"] != "done":
            data["conversion"] = {"percent": 100, "status": "done", "label": "Audio listo (mono 16 kHz PCM 16 bits)"}
        if data["transcription"]["status"] != "done":
            data["transcription"] = {"percent": 100, "status": "done", "label": "Transcripción lista"}
        if data["analysis"]["status"] == "pending":
            data["analysis"]["status"] = "running"
            data["analysis"]["percent"] = max(data["analysis"]["percent"], 8)
            data["analysis"]["label"] = "Analizando entrevista"
        return data
    return data
