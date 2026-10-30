from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.sessions import collect_dashboard
from app.core.access import require_admin
from app.core.security import get_current_user
from app.database import get_db
from app.models import AuditLog, User
from app.schemas import AuditOut, DashboardMetrics

router = APIRouter(tags=["observabilidad"])


@router.get("/dashboard", response_model=DashboardMetrics)
def dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardMetrics:
    return collect_dashboard(db, user)


@router.get("/audit", response_model=list[AuditOut])
def audit_trail(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = 100,
) -> list[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    return list(db.scalars(q).all())
