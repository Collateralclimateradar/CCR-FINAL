
"""Tests for organization-scoped audit log API."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.core.security import hash_password
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import AuditLog, Organization, User


@pytest.fixture
def audit_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    client.test_engine = engine

    yield client

    app.dependency_overrides.clear()
    engine.dispose()


def create_bank(client, name):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_user_and_login(client, organization_id, role="admin"):
    password = "Test-Password-2026!"
    email = f"audit-{uuid.uuid4().hex}@example.com"

    with Session(client.test_engine) as db:
        user = User(
            organization_id=uuid.UUID(organization_id),
            email=email,
            full_name="Audit API Test User",
            role=role,
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 200, response.text

    return {
        "Authorization": (
            f"Bearer {response.json()['access_token']}"
        )
    }


def create_event(
    client,
    organization_id,
    *,
    action="collateral.created",
    entity_type="collateral",
    entity_id=None,
    after_data=None,
):
    event = AuditLog(
        organization_id=uuid.UUID(organization_id),
        actor_user_id=None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id or str(uuid.uuid4()),
        before_data=None,
        after_data=after_data,
    )

    with Session(client.test_engine) as db:
        db.add(event)
        db.commit()
        db.refresh(event)
        return str(event.id)


def test_audit_api_requires_authentication(audit_client):
    organization_id = create_bank(
        audit_client,
        "Audit Authentication Bank",
    )

    response = audit_client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs"
    )

    assert response.status_code == 401


def test_audit_api_returns_only_current_organization_events(
    audit_client,
):
    bank_a = create_bank(audit_client, "Audit Bank A")
    bank_b = create_bank(audit_client, "Audit Bank B")

    headers_a = create_user_and_login(
        audit_client,
        bank_a,
    )
    headers_b = create_user_and_login(
        audit_client,
        bank_b,
    )

    event_a = create_event(
        audit_client,
        bank_a,
        entity_id="BANK-A-EVENT",
    )
    create_event(
        audit_client,
        bank_b,
        entity_id="BANK-B-EVENT",
    )

    response = audit_client.get(
        f"/api/v1/organizations/{bank_a}/audit-logs",
        headers=headers_a,
    )

    assert response.status_code == 200
    records = response.json()

    assert len(records) == 1
    assert records[0]["id"] == event_a
    assert records[0]["entity_id"] == "BANK-A-EVENT"
    assert records[0]["organization_id"] == bank_a

    cross_bank = audit_client.get(
        f"/api/v1/organizations/{bank_a}/audit-logs",
        headers=headers_b,
    )

    assert cross_bank.status_code == 404


def test_audit_api_supports_pagination_and_filters(audit_client):
    organization_id = create_bank(
        audit_client,
        "Audit Filter Bank",
    )
    headers = create_user_and_login(
        audit_client,
        organization_id,
    )

    create_event(
        audit_client,
        organization_id,
        action="collateral.created",
        entity_type="collateral",
        entity_id="COL-1",
    )
    create_event(
        audit_client,
        organization_id,
        action="valuation.created",
        entity_type="valuation",
        entity_id="VAL-1",
    )
    create_event(
        audit_client,
        organization_id,
        action="collateral.archived",
        entity_type="collateral",
        entity_id="COL-2",
    )

    base_url = (
        f"/api/v1/organizations/{organization_id}/audit-logs"
    )

    filtered = audit_client.get(
        base_url,
        headers=headers,
        params={"entity_type": "collateral"},
    )

    assert filtered.status_code == 200
    assert len(filtered.json()) == 2
    assert all(
        item["entity_type"] == "collateral"
        for item in filtered.json()
    )

    action_filtered = audit_client.get(
        base_url,
        headers=headers,
        params={"action": "valuation.created"},
    )

    assert action_filtered.status_code == 200
    assert len(action_filtered.json()) == 1
    assert action_filtered.json()[0]["entity_id"] == "VAL-1"

    first_page = audit_client.get(
        base_url,
        headers=headers,
        params={"limit": 1, "offset": 0},
    )
    second_page = audit_client.get(
        base_url,
        headers=headers,
        params={"limit": 1, "offset": 1},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 1
    assert len(second_page.json()) == 1
    assert (
        first_page.json()[0]["id"]
        != second_page.json()[0]["id"]
    )


def test_audit_api_sanitizes_sensitive_data(audit_client):
    organization_id = create_bank(
        audit_client,
        "Audit Sanitization Bank",
    )
    headers = create_user_and_login(
        audit_client,
        organization_id,
    )

    create_event(
        audit_client,
        organization_id,
        after_data={
            "external_ref": "SAFE-001",
            "password": "must-not-be-returned",
            "nested": {
                "access_token": "must-not-be-returned",
                "city": "Dubai",
            },
        },
    )

    response = audit_client.get(
        f"/api/v1/organizations/{organization_id}/audit-logs",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()[0]["after_data"]

    assert data["external_ref"] == "SAFE-001"
    assert "password" not in data
    assert "access_token" not in data["nested"]
    assert data["nested"]["city"] == "Dubai"


def test_audit_api_rejects_invalid_pagination(audit_client):
    organization_id = create_bank(
        audit_client,
        "Audit Pagination Bank",
    )
    headers = create_user_and_login(
        audit_client,
        organization_id,
    )

    base_url = (
        f"/api/v1/organizations/{organization_id}/audit-logs"
    )

    assert audit_client.get(
        base_url,
        headers=headers,
        params={"limit": 0},
    ).status_code == 422

    assert audit_client.get(
        base_url,
        headers=headers,
        params={"limit": 501},
    ).status_code == 422

    assert audit_client.get(
        base_url,
        headers=headers,
        params={"offset": -1},
    ).status_code == 422
