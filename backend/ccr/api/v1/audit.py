
"""Organization-scoped, read-only audit log endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ccr.api.auth_deps import require_roles
from ccr.api.deps import get_authorized_organization_or_404
from ccr.db.session import get_db
from ccr.models import AuditLog, Organization, User, UserRole

router = APIRouter(
    prefix="/organizations/{organization_id}/audit-logs",
    tags=["audit logs"],
)

READ_ROLES = (
    UserRole.ADMIN,
    UserRole.ANALYST,
    UserRole.VIEWER,
)

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "authorization",
}


def _sanitize_data(value: Any) -> Any:
    """Remove sensitive keys from audit JSON before returning it."""
    if isinstance(value, dict):
        return {
            key: _sanitize_data(item)
            for key, item in value.items()
            if key.lower() not in SENSITIVE_KEYS
        }

    if isinstance(value, list):
        return [_sanitize_data(item) for item in value]

    return value


def _serialize_audit_log(event: AuditLog) -> dict:
    """Convert an audit event into a safe API response."""
    return {
        "id": str(event.id),
        "organization_id": str(event.organization_id),
        "actor_user_id": (
            str(event.actor_user_id)
            if event.actor_user_id is not None
            else None
        ),
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "before_data": _sanitize_data(event.before_data),
        "after_data": _sanitize_data(event.after_data),
        "created_at": event.created_at,
    }


@router.get("")
def list_audit_logs(
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    user: User = Depends(require_roles(*READ_ROLES)),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None, max_length=100),
    entity_type: str | None = Query(None, max_length=50),
):
    """Return audit events belonging only to the caller's organization."""

    stmt = select(AuditLog).where(
        AuditLog.organization_id == org.id
    )

    if action:
        stmt = stmt.where(AuditLog.action == action)

    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    stmt = (
        stmt.order_by(
            AuditLog.created_at.desc(),
            AuditLog.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    events = db.scalars(stmt).all()

    return [_serialize_audit_log(event) for event in events]
