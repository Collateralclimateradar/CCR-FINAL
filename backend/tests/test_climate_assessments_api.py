
"""Integration tests for organization-scoped climate assessment API."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.core.security import hash_password
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import (
    AuditLog,
    ClimateRiskAssessment,
    Collateral,
    Organization,
    User,
)


@pytest.fixture
def climate_client():
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


def create_test_bank(client, name="Climate Test Bank"):
    with Session(client.test_engine) as db:
        organization = Organization(name=name)
        db.add(organization)
        db.commit()
        db.refresh(organization)
        return str(organization.id)


def create_test_user(
    client,
    organization_id,
    *,
    role="admin",
):
    password = "Test-Password-2026!"
    email = f"climate-{uuid.uuid4().hex}@example.com"

    with Session(client.test_engine) as db:
        user = User(
            organization_id=uuid.UUID(organization_id),
            email=email,
            full_name="Climate API Test User",
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


def create_test_collateral(client, organization_id):
    with Session(client.test_engine) as db:
        collateral = Collateral(
            organization_id=uuid.UUID(organization_id),
            external_ref=f"CLIMATE-{uuid.uuid4().hex[:12]}",
            property_type="villa",
            country_code="AE",
            region="Dubai",
            city="Dubai",
            latitude=Decimal("25.204800"),
            longitude=Decimal("55.270800"),
            is_synthetic=False,
        )
        db.add(collateral)
        db.commit()
        db.refresh(collateral)
        return str(collateral.id)


def assessment_payload(collateral_id, **overrides):
    payload = {
        "collateral_id": collateral_id,
        "hazard_type": "flood",
        "risk_score": "80.00",
        "assessment_date": "2026-01-15",
        "source": "test-provider",
        "model_version": "1.0",
    }
    payload.update(overrides)
    return payload


def assessment_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/climate-assessments"
    )


def test_climate_assessment_requires_authentication(
    climate_client,
):
    organization_id = create_test_bank(climate_client)

    response = climate_client.post(
        assessment_url(organization_id),
        json=assessment_payload(str(uuid.uuid4())),
    )

    assert response.status_code == 401


def test_admin_can_create_climate_assessment(climate_client):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
        role="admin",
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(collateral_id),
    )

    assert response.status_code == 201, response.text

    data = response.json()
    assert data["organization_id"] == organization_id
    assert data["collateral_id"] == collateral_id
    assert data["hazard_type"] == "flood"
    assert data["risk_level"] == "very_high"
    assert Decimal(data["risk_score"]) == Decimal("80.00")
    assert data["source"] == "test-provider"
    assert data["model_version"] == "1.0"
    assert data["is_synthetic"] is False

    with Session(climate_client.test_engine) as db:
        assessment = db.get(
            ClimateRiskAssessment,
            uuid.UUID(data["id"]),
        )
        assert assessment is not None

        audit_events = db.scalars(
            select(AuditLog).where(
                AuditLog.organization_id
                == uuid.UUID(organization_id),
                AuditLog.action == "climate_assessment.created",
                AuditLog.entity_id == data["id"],
            )
        ).all()

        assert len(audit_events) == 1
        assert audit_events[0].after_data["hazard_type"] == "flood"
        assert audit_events[0].after_data["risk_level"] == "very_high"


def test_analyst_can_create_climate_assessment(climate_client):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
        role="analyst",
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(
            collateral_id,
            hazard_type="coastal",
            risk_score="60.00",
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["hazard_type"] == "coastal"
    assert response.json()["risk_level"] == "high"


def test_viewer_cannot_create_climate_assessment(climate_client):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
        role="viewer",
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(collateral_id),
    )

    assert response.status_code == 403

    with Session(climate_client.test_engine) as db:
        assessments = db.scalars(
            select(ClimateRiskAssessment)
        ).all()
        assert assessments == []


def test_user_cannot_create_assessment_for_another_bank(
    climate_client,
):
    bank_a = create_test_bank(
        climate_client,
        "Climate Bank A",
    )
    bank_b = create_test_bank(
        climate_client,
        "Climate Bank B",
    )

    headers_a = create_test_user(
        climate_client,
        bank_a,
    )
    collateral_b = create_test_collateral(
        climate_client,
        bank_b,
    )

    response = climate_client.post(
        assessment_url(bank_b),
        headers=headers_a,
        json=assessment_payload(collateral_b),
    )

    assert response.status_code == 404

    with Session(climate_client.test_engine) as db:
        assessments = db.scalars(
            select(ClimateRiskAssessment)
        ).all()
        assert assessments == []


def test_assessment_rejects_collateral_from_unknown_bank(
    climate_client,
):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(str(uuid.uuid4())),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Collateral not found."


@pytest.mark.parametrize(
    "overrides",
    [
        {"hazard_type": "earthquake"},
        {"risk_score": "-1"},
        {"risk_score": "100.01"},
        {"assessment_date": "not-a-date"},
        {"model_version": ""},
        {"unexpected_field": "not-allowed"},
    ],
)
def test_assessment_rejects_invalid_payload(
    climate_client,
    overrides,
):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(
            collateral_id,
            **overrides,
        ),
    )

    assert response.status_code == 422


def test_duplicate_assessment_returns_conflict(climate_client):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    payload = assessment_payload(collateral_id)

    first = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=payload,
    )
    assert first.status_code == 201, first.text

    second = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=payload,
    )

    assert second.status_code == 409

    with Session(climate_client.test_engine) as db:
        assessments = db.scalars(
            select(ClimateRiskAssessment).where(
                ClimateRiskAssessment.organization_id
                == uuid.UUID(organization_id),
                ClimateRiskAssessment.collateral_id
                == uuid.UUID(collateral_id),
            )
        ).all()

        assert len(assessments) == 1


def test_synthetic_status_is_inherited_from_collateral(
    climate_client,
):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    with Session(climate_client.test_engine) as db:
        collateral = db.get(
            Collateral,
            uuid.UUID(collateral_id),
        )
        collateral.is_synthetic = True
        db.commit()

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(collateral_id),
    )

    assert response.status_code == 201, response.text
    assert response.json()["is_synthetic"] is True


def test_assessment_uses_requested_date_and_model_version(
    climate_client,
):
    organization_id = create_test_bank(climate_client)
    headers = create_test_user(
        climate_client,
        organization_id,
    )
    collateral_id = create_test_collateral(
        climate_client,
        organization_id,
    )

    response = climate_client.post(
        assessment_url(organization_id),
        headers=headers,
        json=assessment_payload(
            collateral_id,
            hazard_type="extreme_heat",
            risk_score="40.00",
            assessment_date="2026-02-01",
            model_version="2.0",
        ),
    )

    assert response.status_code == 201, response.text

    data = response.json()
    assert data["hazard_type"] == "extreme_heat"
    assert data["risk_level"] == "moderate"
    assert data["assessment_date"] == date(2026, 2, 1).isoformat()
    assert data["model_version"] == "2.0"
