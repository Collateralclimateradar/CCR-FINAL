"""Tests for the development routes: organizations, collaterals, valuations."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401  (registers all tables)
from ccr.core.config import get_settings
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app, create_app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_org(client, name="Bank A"):
    response = client.post("/api/v1/organizations", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


COLLATERAL = {
    "external_ref": "C-001",
    "property_type": "villa",
    "country_code": "AE",
    "region": "Dubai",
    "latitude": "25.204800",
    "longitude": "55.270800",
    "is_synthetic": True,
}


def make_collateral(client, org_id, **overrides):
    body = {**COLLATERAL, **overrides}
    response = client.post(f"/api/v1/organizations/{org_id}/collaterals", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_and_read_organization(client):
    org_id = make_org(client)
    response = client.get(f"/api/v1/organizations/{org_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Bank A"


def test_duplicate_organization_name_is_rejected(client):
    make_org(client)
    response = client.post("/api/v1/organizations", json={"name": "Bank A"})
    assert response.status_code == 409


def test_unknown_organization_returns_404(client):
    response = client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_create_and_list_collaterals(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)
    listing = client.get(f"/api/v1/organizations/{org_id}/collaterals").json()
    assert [c["id"] for c in listing] == [col_id]
    assert listing[0]["organization_id"] == org_id


def test_duplicate_ref_rejected_in_same_org_but_allowed_in_another(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")
    make_collateral(client, bank_a)
    duplicate = client.post(f"/api/v1/organizations/{bank_a}/collaterals", json=COLLATERAL)
    assert duplicate.status_code == 409
    make_collateral(client, bank_b)  # same ref, different bank: allowed


def test_one_bank_cannot_see_another_banks_collateral(client):
    bank_a = make_org(client, "Bank A")
    bank_b = make_org(client, "Bank B")
    col_id = make_collateral(client, bank_a)
    assert client.get(f"/api/v1/organizations/{bank_b}/collaterals").json() == []
    assert client.get(f"/api/v1/organizations/{bank_b}/collaterals/{col_id}").status_code == 404


def test_synthetic_flag_is_required(client):
    org_id = make_org(client)
    body = {k: v for k, v in COLLATERAL.items() if k != "is_synthetic"}
    response = client.post(f"/api/v1/organizations/{org_id}/collaterals", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"latitude": "123.0"},
        {"longitude": None},  # latitude without longitude
        {"country_code": "ae"},
        {"organization_id": "00000000-0000-0000-0000-000000000000"},  # not accepted
    ],
)
def test_invalid_collateral_is_rejected(client, bad):
    org_id = make_org(client)
    response = client.post(
        f"/api/v1/organizations/{org_id}/collaterals", json={**COLLATERAL, **bad}
    )
    assert response.status_code == 422


def test_valuation_history_newest_first(client):
    org_id = make_org(client)
    col_id = make_collateral(client, org_id)
    url = f"/api/v1/organizations/{org_id}/collaterals/{col_id}/valuations"
    for amount, day in [("1000000.00", "2025-01-01"), ("1200000.00", "2026-01-01")]:
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
    dates = [v["valuation_date"] for v in client.get(url).json()]
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
    col_id = make_collateral(client, bank_a)
    response = client.post(
        f"/api/v1/organizations/{bank_b}/collaterals/{col_id}/valuations",
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
        assert production_client.post("/api/v1/organizations", json={"name": "X"}).status_code == 404
        assert production_client.get("/api/v1/health").status_code in (200, 503)
    finally:
        get_settings.cache_clear()
