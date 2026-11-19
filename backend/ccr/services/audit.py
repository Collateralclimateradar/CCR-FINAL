
"""Helpers for recording audit events in the current database transaction."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ccr.models import AuditLog


def record_audit_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit event without committing the transaction.

    The caller must commit or roll back the business operation and audit
    event together. Only pass explicitly selected, non-sensitive fields
    in before_data and after_data.
    """

    event = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        before_data=before_data,
        after_data=after_data,
    )

    db.add(event)
    return event
