
"""Integration tests for authenticated climate location screening."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.api.v1.climate_location_screening import (
    get_climate_data_provider,
)
from ccr.core.security import hash_password
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import AuditLog, Collateral, Organization, User
from ccr.services.climate_data_provider import (
    ClimateHazard,
    ClimateHazardResult,
    HazardLevel,
)


class FakeClimateProvider:
    """Deterministic provider used by API integration tests."""

    name = "test-climate-provider"

    def __init__(self):
        self.calls = []

    def assess_location(self, *, latitude, longitude, hazards):
        self.calls.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "hazards": hazards,
            }
        )
        return [
            ClimateHazardResult(
                source=self.name,
                hazard=ClimateHazard.FLOOD,
                level=HazardLevel.HIGH,
                retrieved_at=datetime(
                    2026, 1, 15, tzinfo=timezone.utc
                ),
                latitude=latitude,
                longitude=longitude,
                raw_category="High",
                reference_url="https://example.com/climate-source",
            )
        ]


@pytest.fixture
def climate_location_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    provider = FakeClimateProvider()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_climate_data_provider] = (
        lambda: provider
    )

    client = TestClient(app)
    client.test_engine = engine
    client.test_provider = provider

    yield client

    app.dependency_overrides.clear()
    engine.dispose()


def create_bank(client, name="Climate Location Test Bank"):
    with Session(client.test_engine) as db:
        organization = Organization(name=name)
        db.add(organization)
        db.commit()
        db.refresh(organization)
        return str(organization.id)


def create_user(client, organization_id):
    password = "Test-Password-2026!"
    email = f"location-{uuid.uuid4().hex}@example.com"

    with Session(client.test_engine) as db:
        user = User(
            organization_id=uuid.UUID(organization_id),
            email=email,
            full_name="Climate Location Test User",
            role="admin",
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


def create_collateral(client, organization_id):
    with Session(client.test_engine) as db:
        collateral = Collateral(
            organization_id=uuid.UUID(organization_id),
            external_ref=f"LOCATION-{uuid.uuid4().hex[:12]}",
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


def screening_url(organization_id, collateral_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        f"/collaterals/{collateral_id}"
        "/climate-location-screening"
    )


def test_climate_location_screening_requires_authentication(
    climate_location_client,
):
    organization_id = create_bank(climate_location_client)
    collateral_id = create_collateral(
        climate_location_client,
        organization_id,
    )

    response = climate_location_client.post(
        screening_url(organization_id, collateral_id),
        json={"hazards": ["flood"]},
    )

    assert response.status_code == 401
    assert climate_location_client.test_provider.calls == []


def test_user_cannot_screen_another_banks_collateral(
    climate_location_client,
):
    bank_a = create_bank(
        climate_location_client,
        "Climate Location Bank A",
    )
    bank_b = create_bank(
        climate_location_client,
        "Climate Location Bank B",
    )

    headers_a = create_user(climate_location_client, bank_a)
    collateral_b = create_collateral(
        climate_location_client,
        bank_b,
    )

    response = climate_location_client.post(
        screening_url(bank_b, collateral_b),
        headers=headers_a,
        json={"hazards": ["flood"]},
    )

    assert response.status_code == 404
    assert climate_location_client.test_provider.calls == []

    with Session(climate_location_client.test_engine) as db:
        events = db.scalars(
            select(AuditLog).where(
                AuditLog.action
                == "collateral.climate_location_screened"
            )
        ).all()

        assert events == []


def test_authenticated_user_can_screen_own_collateral_and_audit_is_recorded(
    climate_location_client,
):
    organization_id = create_bank(climate_location_client)
    headers = create_user(
        climate_location_client,
        organization_id,
    )
    collateral_id = create_collateral(
        climate_location_client,
        organization_id,
    )

    response = climate_location_client.post(
        screening_url(organization_id, collateral_id),
        headers=headers,
        json={"hazards": ["flood"]},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["collateral_id"] == collateral_id
    assert data["provider"] == "test-climate-provider"
    assert len(data["results"]) == 1
    assert data["results"][0]["hazard"] == "flood"
    assert data["results"][0]["level"] == "high"
    assert data["results"][0]["source"] == "test-climate-provider"

    assert climate_location_client.test_provider.calls == [
        {
            "latitude": 25.2048,
            "longitude": 55.2708,
            "hazards": (ClimateHazard.FLOOD,),
        }
    ]

    with Session(climate_location_client.test_engine) as db:
        events = db.scalars(
            select(AuditLog).where(
                AuditLog.organization_id
                == uuid.UUID(organization_id),
                AuditLog.action
                == "collateral.climate_location_screened",
                AuditLog.entity_id == collateral_id,
            )
        ).all()

        assert len(events) == 1
        assert events[0].after_data["provider"] == (
            "test-climate-provider"
        )
        assert events[0].after_data["result_count"] == 1
        assert events[0].after_data["hazards_requested"] == [
            "flood"
        ]


def test_unknown_collateral_returns_404(
    climate_location_client,
):
    organization_id = create_bank(climate_location_client)
    headers = create_user(
        climate_location_client,
        organization_id,
    )

    response = climate_location_client.post(
        screening_url(organization_id, str(uuid.uuid4())),
        headers=headers,
        json={"hazards": ["flood"]},
    )

    assert response.status_code == 404
    assert climate_location_client.test_provider.calls == []


def test_invalid_hazard_request_is_rejected(
    climate_location_client,
):
    organization_id = create_bank(climate_location_client)
    headers = create_user(
        climate_location_client,
        organization_id,
    )
    collateral_id = create_collateral(
        climate_location_client,
        organization_id,
    )

    response = climate_location_client.post(
        screening_url(organization_id, collateral_id),
        headers=headers,
        json={"hazards": ["earthquake"]},
    )

    assert response.status_code == 422
    assert climate_location_client.test_provider.calls == []
