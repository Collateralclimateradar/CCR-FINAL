
"""Tests for the audit event recording service."""

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.db.base import Base
from ccr.models import AuditLog, Organization, User, UserRole
from ccr.services.audit import record_audit_event


def test_record_audit_event_adds_event_to_current_transaction():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as db:
            organization = Organization(name="Audit Test Bank")
            db.add(organization)
            db.flush()

            user = User(
                organization_id=organization.id,
                email=f"audit-{uuid.uuid4().hex}@example.com",
                full_name="Audit Test Admin",
                role=UserRole.ADMIN,
                is_active=True,
                password_hash="test-password-hash",
            )
            db.add(user)
            db.flush()

            entity_id = uuid.uuid4()

            event = record_audit_event(
                db,
                organization_id=organization.id,
                actor_user_id=user.id,
                action="collateral.created",
                entity_type="collateral",
                entity_id=entity_id,
                after_data={
                    "external_ref": "AUDIT-001",
                    "property_type": "villa",
                },
            )

            assert event in db.new
            assert event.organization_id == organization.id
            assert event.actor_user_id == user.id
            assert event.action == "collateral.created"
            assert event.entity_type == "collateral"
            assert event.entity_id == str(entity_id)
            assert event.before_data is None
            assert event.after_data == {
                "external_ref": "AUDIT-001",
                "property_type": "villa",
            }

            db.commit()

            saved_event = db.scalars(
                select(AuditLog).where(
                    AuditLog.id == event.id
                )
            ).one()

            assert saved_event.action == "collateral.created"
            assert saved_event.entity_id == str(entity_id)

    finally:
        engine.dispose()
