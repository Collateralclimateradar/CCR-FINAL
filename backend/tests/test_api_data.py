
"""Tests for the development routes: organizations, collaterals, valuations."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401 (registers all tables)
from ccr.core.config import get_settings
from ccr.core.security import hash_password
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app, create_app
from ccr.models import Organization, User


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    test_client = TestClient(app)
    test_client.test_engine = engine
    test_client.auth_headers = {}

    yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


def make_auth_headers(client, org_id):
    """Create a real test user and return a JWT authorization header."""
    password = "Test-Password-2026!"

    with Session(client.test_engine) as db:
        organization = db.get(Organization, uuid.UUID(org_id))
        assert organization is not None

        email = f"test-{uuid.uuid4().hex}@example.com"

        user = User(
            organization_id=organization.id,
            email=email,
            full_name="Test Admin",
            role="admin",
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text

    return {
        "Authorization": f"Bearer {response.json()['access_token']}"
    }


def use_org(client, org_id):
    """Set the authenticated session for a specific organization."""
    headers = client.auth_headers[org_id]
    client.headers.update(headers)
    return headers


def make_org(client, name="Bank A"):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
    )
    assert response.status_code == 201, response.text

    org_id = response.json()["id"]
    headers = make_auth_headers(client, org_id)

    client.auth_headers[org_id] = headers
    use_org(client, org_id)

    return org_id


COLLATERAL = {
    "external_ref": "C-001",
    "property_type": "villa",
    "country_code": "AE",
    "region": "Dubai",
    "latitude": "25.204800",
    "longitude": "55.270800",
    "is_synthetic": True,
}


def make_collateral(client, org_id, headers=None, **overrides):
    """Create a collateral using the selected organization's JWT."""
    body = {**COLLATERAL, **overrides}

    request_headers = (
        headers if headers is not None else client.headers
    )

    response = client.post(
        f"/api/v1/organizations/{org_id}/collaterals",
        json=body,
        headers=request_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_and_read_organization(client):
    org_id = make_org(client)

    response = client.get(
        f"/api/v1/organizations/{org_id}"
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Bank A"


def test_duplicate_organization_name_is_rejected(client):
    make_org(client)

    response = client.post(
        "/api/v1/organizations",
        json={"name": "Bank A"},
    )

    assert response.status_code == 409


def test_unknown_organization_returns_404(client):
    response = client.get(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_create_and_list_collaterals(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    listing_response = client.get(
        f"/api/v1/organizations/{org_id}/collaterals"
    )

    assert listing_response.status_code == 200

    listing = listing_response.json()
    assert [c["id"] for c in listing] == [col_id]
    assert listing[0]["organization_id"] == org_id


def test_duplicate_ref_rejected_in_same_org_but_allowed_in_another(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")

    headers_a = use_org(client, bank_a)
    make_collateral(client, bank_a, headers=headers_a)

    duplicate = client.post(
        f"/api/v1/organizations/{bank_a}/collaterals",
        json=COLLATERAL,
        headers=headers_a,
    )

    assert duplicate.status_code == 409

    headers_b = use_org(client, bank_b)
    make_collateral(client, bank_b, headers=headers_b)


def test_one_bank_cannot_see_another_banks_collateral(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")

    headers_a = use_org(client, bank_a)
    col_id = make_collateral(
        client,
        bank_a,
        headers=headers_a,
    )

    headers_b = use_org(client, bank_b)

    listing = client.get(
        f"/api/v1/organizations/{bank_b}/collaterals",
        headers=headers_b,
    )

    assert listing.status_code == 200
    assert listing.json() == []

    detail = client.get(
        f"/api/v1/organizations/{bank_b}/collaterals/{col_id}",
        headers=headers_b,
    )

    assert detail.status_code == 404


def test_synthetic_flag_is_required(client):
    org_id = make_org(client)

    body = {
        key: value
        for key, value in COLLATERAL.items()
        if key != "is_synthetic"
    }

    response = client.post(
        f"/api/v1/organizations/{org_id}/collaterals",
        json=body,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"latitude": "123.0"},
        {"longitude": None},
        {"country_code": "ae"},
        {
            "organization_id": (
                "00000000-0000-0000-0000-000000000000"
            )
        },
    ],
)
def test_invalid_collateral_is_rejected(client, bad):
    org_id = make_org(client)

    response = client.post(
        f"/api/v1/organizations/{org_id}/collaterals",
        json={**COLLATERAL, **bad},
    )

    assert response.status_code == 422


def test_valuation_history_newest_first(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals"
        f"/{col_id}/valuations"
    )

    for amount, day in [
        ("1000000.00", "2025-01-01"),
        ("1200000.00", "2026-01-01"),
    ]:
        response = client.post(
            url,
            json={
                "value_amount": amount,
                "currency": "AED",
                "valuation_date": day,
                "is_synthetic": True,
            },
        )

        assert response.status_code == 201, response.text

    history = client.get(url)

    assert history.status_code == 200

    dates = [
        valuation["valuation_date"]
        for valuation in history.json()
    ]

    assert dates == ["2026-01-01", "2025-01-01"]


def test_negative_valuation_is_rejected(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    response = client.post(
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}/valuations",
        json={
            "value_amount": "-5",
            "currency": "AED",
            "valuation_date": "2026-01-01",
            "is_synthetic": True,
        },
    )

    assert response.status_code == 422


def test_valuation_cannot_be_added_to_another_banks_collateral(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")

    headers_a = use_org(client, bank_a)
    col_id = make_collateral(
        client,
        bank_a,
        headers=headers_a,
    )

    headers_b = use_org(client, bank_b)

    response = client.post(
        f"/api/v1/organizations/{bank_b}/collaterals/{col_id}/valuations",
        headers=headers_b,
        json={
            "value_amount": "100.00",
            "currency": "AED",
            "valuation_date": "2026-01-01",
            "is_synthetic": True,
        },
    )

    assert response.status_code == 404


def test_development_routes_are_off_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()

    try:
        production_app = create_app()
        production_client = TestClient(production_app)

        assert production_client.post(
            "/api/v1/organizations",
            json={"name": "X"},
        ).status_code == 404

        assert production_client.get(
            "/api/v1/health"
        ).status_code in (200, 503)

    finally:
        get_settings.cache_clear()


def test_archive_hides_collateral_but_preserves_valuation_history(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    base_url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )
    valuation_url = f"{base_url}/valuations"

    created = client.post(
        valuation_url,
        json={
            "value_amount": "1500000.00",
            "currency": "AED",
            "valuation_date": "2026-01-01",
            "is_synthetic": True,
        },
    )

    assert created.status_code == 201

    archived = client.delete(base_url)

    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    listing = client.get(
        f"/api/v1/organizations/{org_id}/collaterals"
    )

    assert listing.status_code == 200
    assert listing.json() == []

    included = client.get(
        f"/api/v1/organizations/{org_id}/collaterals"
        "?include_archived=true"
    )

    assert included.status_code == 200
    assert len(included.json()) == 1
    assert included.json()[0]["id"] == col_id

    assert client.get(base_url).status_code == 404

    history = client.get(
        f"{valuation_url}?include_archived=true"
    )

    assert history.status_code == 200
    assert len(history.json()) == 1


def test_archived_collateral_cannot_receive_new_valuations(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    base_url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    archived = client.delete(base_url)
    assert archived.status_code == 200

    response = client.post(
        f"{base_url}/valuations",
        json={
            "value_amount": "100.00",
            "currency": "AED",
            "valuation_date": "2026-01-01",
            "is_synthetic": True,
        },
    )

    assert response.status_code == 404


def test_archived_collateral_can_be_restored(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    base_url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    archived = client.delete(base_url)
    assert archived.status_code == 200

    restored = client.post(f"{base_url}/restore")

    assert restored.status_code == 200
    assert restored.json()["is_archived"] is False

    listing = client.get(
        f"/api/v1/organizations/{org_id}/collaterals"
    )

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [col_id]


def test_archive_endpoint_respects_organization_isolation(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")

    headers_a = use_org(client, bank_a)
    col_id = make_collateral(
        client,
        bank_a,
        headers=headers_a,
    )

    headers_b = use_org(client, bank_b)

    response = client.delete(
        f"/api/v1/organizations/{bank_b}/collaterals/{col_id}",
        headers=headers_b,
    )

    assert response.status_code == 404


def test_update_collateral_partial_fields(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    response = client.patch(
        url,
        json={"city": "Abu Dhabi"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["city"] == "Abu Dhabi"
    assert data["property_type"] == "villa"
    assert data["external_ref"] == "C-001"


def test_update_collateral_rejects_empty_payload(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    response = client.patch(url, json={})

    assert response.status_code == 422


def test_update_collateral_rejects_null_required_fields(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    for field in ("external_ref", "property_type", "is_synthetic"):
        response = client.patch(
            url,
            json={field: None},
        )

        assert response.status_code == 422


def test_update_collateral_validates_coordinate_pair(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    response = client.patch(
        url,
        json={"latitude": "24.500000"},
    )

    assert response.status_code == 200
    assert response.json()["latitude"] == "24.500000"

    response = client.patch(
        url,
        json={"latitude": None},
    )

    assert response.status_code == 422


def test_update_collateral_rejects_invalid_coordinates(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    response = client.patch(
        url,
        json={"latitude": "95.0"},
    )

    assert response.status_code == 422


def test_update_collateral_rejects_duplicate_external_ref(client):
    org_id = make_org(client)

    make_collateral(client, org_id)

    second_id = make_collateral(
        client,
        org_id,
        external_ref="C-002",
    )

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{second_id}"
    )

    response = client.patch(
        url,
        json={"external_ref": "C-001"},
    )

    assert response.status_code == 409

    unchanged = client.get(url)

    assert unchanged.status_code == 200
    assert unchanged.json()["external_ref"] == "C-002"


def test_update_collateral_cannot_cross_organizations(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")

    headers_a = use_org(client, bank_a)
    col_id = make_collateral(
        client,
        bank_a,
        headers=headers_a,
    )

    headers_b = use_org(client, bank_b)

    url = (
        f"/api/v1/organizations/{bank_b}/collaterals/{col_id}"
    )

    response = client.patch(
        url,
        headers=headers_b,
        json={"city": "Abu Dhabi"},
    )

    assert response.status_code == 404


def test_archived_collateral_cannot_be_updated(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )

    archived = client.delete(url)
    assert archived.status_code == 200

    response = client.patch(
        url,
        json={"city": "Abu Dhabi"},
    )

    assert response.status_code == 404


def test_update_collateral_does_not_modify_valuation_history(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)

    base_url = (
        f"/api/v1/organizations/{org_id}/collaterals/{col_id}"
    )
    valuation_url = f"{base_url}/valuations"

    created = client.post(
        valuation_url,
        json={
            "value_amount": "1500000.00",
            "currency": "AED",
            "valuation_date": "2026-01-01",
            "is_synthetic": True,
        },
    )

    assert created.status_code == 201

    updated = client.patch(
        base_url,
        json={"city": "Abu Dhabi"},
    )

    assert updated.status_code == 200

    history = client.get(valuation_url)

    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["value_amount"] == "1500000.00"


def test_auth_headers_create_valid_authenticated_session(client):
    org_id = make_org(client)

    headers = client.auth_headers[org_id]

    assert headers["Authorization"].startswith("Bearer ")

    response = client.get(
        "/api/v1/auth/me",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["email"].endswith("@example.com")
    assert response.json()["role"] == "admin"
