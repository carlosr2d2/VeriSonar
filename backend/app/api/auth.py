from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import write_audit
from app.core.security import create_access_token, get_current_user, verify_password
from app.database import get_db
from app.models import User
from app.schemas import DemoAccount, PushTokenIn, Token, UserOut
from app.seed import seed_catalog
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["autenticación"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == form.username))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o clave incorrectos")
    write_audit(db, action="auth.login", resource_type="user", resource_id=user.id, actor=user)
    return Token(
        access_token=create_access_token(user.id, user.role.value),
        role=user.role.value,
        email=user.email,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/demo-accounts", response_model=list[DemoAccount])
def demo_accounts() -> list[DemoAccount]:
    if not settings.app_debug:
        raise HTTPException(status_code=404, detail="No disponible")
    return [DemoAccount.model_validate(item) for item in seed_catalog()]


@router.post("/push-token", response_model=UserOut)
def register_push_token(
    body: PushTokenIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    user.push_token = body.token
    db.commit()
    db.refresh(user)
    write_audit(
        db,
        action="push.register",
        resource_type="user",
        resource_id=user.id,
        payload={"platform": body.platform},
        actor=user,
    )
    return user
