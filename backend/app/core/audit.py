from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    payload: dict | None = None,
    actor: User | None = None,
) -> None:
    log = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload or {},
    )
    db.add(log)
    db.commit()
