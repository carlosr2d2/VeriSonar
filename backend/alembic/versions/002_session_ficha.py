"""ficha del evaluado y número de evaluación VSA

Revision ID: 002_session_ficha
Revises: 001_initial
Create Date: 2026-09-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_session_ficha"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("evaluation_code", sa.String(length=32), nullable=True))
    op.add_column("sessions", sa.Column("subject_name", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("subject_document", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("modality", sa.String(length=32), nullable=True))
    op.add_column("sessions", sa.Column("purpose", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("evaluator_name", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("evaluator_title", sa.String(length=255), nullable=True))
    op.create_index("ix_sessions_evaluation_code", "sessions", ["evaluation_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sessions_evaluation_code", table_name="sessions")
    op.drop_column("sessions", "evaluator_title")
    op.drop_column("sessions", "evaluator_name")
    op.drop_column("sessions", "purpose")
    op.drop_column("sessions", "modality")
    op.drop_column("sessions", "location")
    op.drop_column("sessions", "subject_document")
    op.drop_column("sessions", "subject_name")
    op.drop_column("sessions", "evaluation_code")
