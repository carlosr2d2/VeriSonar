"""esquema inicial users sessions audio_records reports audit_logs

Revision ID: 001_initial
Revises:
Create Date: 2026-09-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM("admin", "analyst", "viewer", "mobile", name="user_role", create_type=False)
session_status = postgresql.ENUM(
    "draft", "queued", "processing", "completed", "failed", name="session_status", create_type=False
)
audio_status = postgresql.ENUM(
    "uploaded",
    "queued",
    "transcribing",
    "analyzing",
    "completed",
    "failed",
    name="audio_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("admin", "analyst", "viewer", "mobile", name="user_role").create(bind, checkfirst=True)
    postgresql.ENUM("draft", "queued", "processing", "completed", "failed", name="session_status").create(
        bind, checkfirst=True
    )
    postgresql.ENUM(
        "uploaded", "queued", "transcribing", "analyzing", "completed", "failed", name="audio_status"
    ).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="es"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("push_token", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="es"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("status", session_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "audio_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("status", audio_status, nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audio_records_session_id", "audio_records", ["session_id"])
    op.create_index("ix_audio_records_celery_task_id", "audio_records", ["celery_task_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("audio_record_id", sa.String(length=36), sa.ForeignKey("audio_records.id"), nullable=False, unique=True),
        sa.Column("transcription", sa.Text(), nullable=True),
        sa.Column("language_detected", sa.String(length=8), nullable=False, server_default="es"),
        sa.Column("stt_engine", sa.String(length=64), nullable=True),
        sa.Column("linguistic_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("acoustic_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("deception_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reliability_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("json_path", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_session_id", "reports", ["session_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("reports")
    op.drop_table("audio_records")
    op.drop_table("sessions")
    op.drop_table("users")
    bind = op.get_bind()
    postgresql.ENUM(name="audio_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="session_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="user_role").drop(bind, checkfirst=True)
