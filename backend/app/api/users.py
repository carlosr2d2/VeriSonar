from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import require_admin
from app.database import get_db
from app.models import User
from app.schemas import UserOut

router = APIRouter(prefix="/users", tags=["usuarios"])


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.role, User.full_name)).all())
