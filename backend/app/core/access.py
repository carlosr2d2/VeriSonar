from fastapi import Depends, HTTPException, status

from app.core.security import get_current_user
from app.models import User, UserRole


def is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere rol administrador")
    return user


def require_analyst_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.ANALYST}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol analista o administrador",
        )
    return user


def can_access_owner(user: User, owner_id: str) -> bool:
    return is_admin(user) or user.id == owner_id
