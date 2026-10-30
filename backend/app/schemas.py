from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str
    full_name: str


class DemoAccount(BaseModel):
    email: str
    password: str
    full_name: str
    role: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    locale: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("role", mode="before")
    @classmethod
    def coerce_role(cls, value: object) -> str:
        return str(getattr(value, "value", value))


class PushTokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    platform: str = Field(default="android", pattern="^(android|ios|web|windows)$")


class SessionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    language: str = Field(default="es", pattern="^(es|en)$")
    context: str | None = None
    subject_name: str | None = None
    subject_document: str | None = None
    location: str | None = None
    modality: str | None = Field(default="presencial")
    purpose: str | None = None
    evaluator_name: str | None = None
    evaluator_title: str | None = None

    @field_validator("modality", mode="before")
    @classmethod
    def coerce_modality(cls, value: object) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"presencial", "remoto"} else "presencial"


class SessionOut(BaseModel):
    id: str
    user_id: str
    title: str
    language: str
    context: str | None
    evaluation_code: str | None = None
    subject_name: str | None = None
    subject_document: str | None = None
    location: str | None = None
    modality: str | None = None
    purpose: str | None = None
    evaluator_name: str | None = None
    evaluator_title: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, value: object) -> str:
        return str(getattr(value, "value", value))


class AudioOut(BaseModel):
    id: str
    session_id: str
    original_name: str
    status: str
    duration_seconds: float | None
    sample_rate: int | None
    celery_task_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyzeAccepted(BaseModel):
    audio_id: str
    session_id: str
    task_id: str
    status: str
    message: str


class Finding(BaseModel):
    code: str
    category: str
    severity: str
    title: str
    detail: str
    evidence: str | None = None
    weight: float = 0.0


class ClipBoundsIn(BaseModel):
    start: float
    end: float
    answer_start: float
    answer_end: float


class ClipTextIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=2000)


class ClipChartsIn(BaseModel):
    include_vsa: bool | None = None
    include_comb: bool | None = None
    vsa_note: str | None = Field(default=None, max_length=100)
    comb_note: str | None = Field(default=None, max_length=100)


class ClipWindowOut(BaseModel):
    index: int
    window_start: float
    window_end: float
    duration: float
    samples: list[float]
    start: float
    end: float
    answer_start: float
    answer_end: float


class ReportOut(BaseModel):
    id: str
    session_id: str
    audio_record_id: str
    transcription: str | None
    language_detected: str
    stt_engine: str | None
    linguistic_score: float
    acoustic_score: float
    deception_index: float
    reliability_index: float
    findings: dict[str, Any]
    pdf_path: str | None
    json_path: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProgressStage(BaseModel):
    percent: int = 0
    status: str = "pending"
    label: str = "En espera"


class AnalysisProgress(BaseModel):
    conversion: ProgressStage
    transcription: ProgressStage
    analysis: ProgressStage


class AnalyzeStatus(BaseModel):
    audio: AudioOut
    session: SessionOut
    task_state: str | None = None
    report: ReportOut | None = None
    progress: AnalysisProgress | None = None


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    version: str
    processing_mode: str
    locale: str
    components: list[HealthComponent]


class DashboardMetrics(BaseModel):
    sessions_total: int
    analyses_completed: int
    analyses_failed: int
    analyses_in_progress: int
    avg_reliability: float
    avg_deception: float
    celery_workers: int
    celery_active_tasks: int
    celery_queued_tasks: int


class AuditOut(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
